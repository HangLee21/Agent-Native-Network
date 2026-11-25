"""SimPy task-level prototype. Units and all uncalibrated assumptions are explicit."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
import simpy


@dataclass(frozen=True)
class Config:
    budget_s: float = 120.0
    speed_cells_s: float = 1.0
    sensing_s: float = 4.0
    decision_s: float = 0.25
    noise_std: float = 0.01
    prior_block: int = 3
    prior_noise_std: float = 0.02

    def __post_init__(self):
        if min(self.budget_s, self.speed_cells_s, self.sensing_s, self.decision_s) <= 0:
            raise ValueError("Budget, speed, sensing and decision time must be positive.")
        if self.prior_block < 1 or min(self.noise_std, self.prior_noise_std) < 0:
            raise ValueError("Invalid prior block or noise.")


@dataclass(frozen=True)
class Link:
    name: str
    bitrate_bps: float
    latency_s: float
    period_s: float = 0.0
    contact_s: float = 0.0

    def __post_init__(self):
        if min(self.bitrate_bps, self.latency_s, self.period_s, self.contact_s) < 0:
            raise ValueError("Link parameters must be nonnegative.")
        if self.period_s and not 0 < self.contact_s <= self.period_s:
            raise ValueError("Periodic contact must be positive and <= period.")


LINKS = {
    "ideal": Link("ideal", float("inf"), 0),
    "good": Link("good", 1_000_000, 0.02),
    "intermittent": Link("intermittent", 9_600, 0.2, 30, 10),
    "stress": Link("stress", 512, 1, 60, 5),
    "disconnected": Link("disconnected", 0, 0),
}


class World:
    """Only the environment observes fine spectra; policies receive prior copies."""

    def __init__(self, cube: np.ndarray, cfg: Config, seed: int, provenance: dict):
        cube = np.asarray(cube, dtype=float)
        if cube.ndim != 3 or min(cube.shape[:2]) < 4 or cube.shape[2] < 3:
            raise ValueError("Expected finite H x W x B cube, H,W>=4 and B>=3.")
        if not np.isfinite(cube).all() or cube.min() < 0 or cube.max() > 1:
            raise ValueError("Input must be preprocessed to finite reflectance in [0,1].")
        self._truth = cube.reshape(-1, cube.shape[-1]).copy()
        self.shape = cube.shape
        self.cfg, self.seed, self.provenance = cfg, seed, provenance
        yy, xx = np.indices(cube.shape[:2])
        self.xy = np.column_stack([xx.ravel(), yy.ravel()]).astype(float)
        # Fixed holdout locations never available for in-situ sampling.
        self.holdout = ((xx + 2 * yy) % 4 == 0).ravel()
        prior = np.empty_like(cube)
        block = cfg.prior_block
        for y in range(0, cube.shape[0], block):
            for x in range(0, cube.shape[1], block):
                tile = cube[y:y + block, x:x + block]
                prior[y:y + block, x:x + block] = tile.mean(axis=(0, 1))
        rng = np.random.default_rng(np.random.SeedSequence([seed, 101]))
        self.prior = np.clip(
            prior + rng.normal(0, cfg.prior_noise_std, cube.shape), 0, 1
        ).reshape(self._truth.shape)

    def measure(self, node: int, site: int) -> np.ndarray:
        # Common random numbers: identical node/site has identical measurement
        # in all policies, independent of execution order and network events.
        rng = np.random.default_rng(np.random.SeedSequence([self.seed, node, site, 202]))
        return np.clip(
            self._truth[site] + rng.normal(0, self.cfg.noise_std, self.shape[2]), 0, 1
        ).astype(np.float32)

    def evaluate(self, observations: list[Observation]) -> dict:
        """Fixed residual interpolator; all policies receive terminal union."""
        prediction = self.prior.copy()
        if observations:
            sites = np.array([o.site for o in observations])
            spectra = np.stack([o.spectrum for o in observations])
            # Similar coarse spectra share a correction; bandwidth fixed ex ante.
            distance2 = np.mean(
                (self.prior[:, None, :] - self.prior[sites][None, :, :]) ** 2, axis=2
            )
            weights = np.exp(-distance2 / (2 * 0.08**2))
            residuals = spectra - self.prior[sites]
            prediction += (weights @ residuals) / (0.5 + weights.sum(axis=1, keepdims=True))
        prediction = np.clip(prediction, 0, 1)
        error = prediction[self.holdout] - self._truth[self.holdout]
        prior_error = self.prior[self.holdout] - self._truth[self.holdout]
        return {
            "heldout_rmse": float(np.sqrt(np.mean(error**2))),
            "prior_rmse": float(np.sqrt(np.mean(prior_error**2))),
            "evaluation_pixels": int(self.holdout.sum()),
        }


def synthetic_world(seed: int, cfg: Config, size: int = 12, bands: int = 16) -> World:
    """Smooth synthetic mixtures, deliberately not named real minerals."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 303]))
    y, x = np.mgrid[0:1:complex(size), 0:1:complex(size)]
    wavelength = np.linspace(0, 1, bands)
    spectra, fields = [], []
    for _ in range(5):
        spectrum = np.full(bands, rng.uniform(0.3, 0.7))
        for _ in range(3):
            center, width = rng.uniform(0, 1), rng.uniform(0.03, 0.15)
            spectrum -= rng.uniform(0.04, 0.15) * np.exp(
                -((wavelength - center) / width) ** 2
            )
        spectra.append(np.clip(spectrum, 0.02, 0.95))
        cx, cy = rng.uniform(0, 1, 2)
        scale = rng.uniform(0.12, 0.4)
        fields.append(0.02 + np.exp(-((x - cx)**2 + (y - cy)**2) / scale**2))
    weights = np.stack(fields, axis=-1)
    weights /= weights.sum(axis=-1, keepdims=True)
    cube = weights @ np.array(spectra)
    return World(cube, cfg, seed, {
        "kind": "synthetic", "generator": "smooth-mixtures-v1",
        "warning": "Not geological observations or calibrated wireless evidence.",
    })


def load_world(path: Path, cfg: Config, seed: int) -> World:
    """External NPZ must include a cube and auditable provenance, no pickle."""
    with np.load(path, allow_pickle=False) as data:
        cube = data["cube"]
        provenance = json.loads(str(data["provenance"].item()))
    for key in ("source_url", "license_or_access_terms", "preprocessing", "kind"):
        if not provenance.get(key):
            raise ValueError(f"Missing provenance field: {key}")
    provenance["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return World(cube, cfg, seed, provenance)


@dataclass(frozen=True)
class Observation:
    oid: int
    producer: int
    site: int
    generated_s: float
    spectrum: np.ndarray

    def encode(self) -> bytes:
        # Explicit compact application payload, not claimed on-air bytes.
        return struct.pack("<IIIdI", self.oid, self.producer, self.site,
                           self.generated_s, len(self.spectrum)) + self.spectrum.astype("<f4").tobytes()

    @staticmethod
    def decode(payload: bytes) -> Observation:
        oid, node, site, time, bands = struct.unpack("<IIIdI", payload[:24])
        spectrum = np.frombuffer(payload[24:], dtype="<f4").copy()
        if len(spectrum) != bands:
            raise ValueError("Malformed observation payload.")
        return Observation(oid, node, site, time, spectrum)


class Policy:
    """Greedy spectral novelty per action cost; a fixed heuristic, not P31 replication."""

    def __init__(self, prior, xy, candidates, cfg):
        self.prior, self.xy = prior.copy(), xy.copy()
        self.candidates, self.cfg = np.array(candidates), cfg
        self.library = [prior.mean(axis=0).copy()]
        self.seen = set()

    def observe(self, observation: Observation):
        if observation.oid not in self.seen:
            self.library.append(observation.spectrum.copy())
            self.seen.add(observation.oid)

    def choose(self, position, visited, remaining):
        candidates = self.candidates[~np.isin(self.candidates, list(visited))]
        if not len(candidates):
            return None
        travel = np.linalg.norm(self.xy[candidates] - position, axis=1) / self.cfg.speed_cells_s
        cost = travel + self.cfg.sensing_s + self.cfg.decision_s
        feasible = cost <= remaining + 1e-9
        candidates, cost = candidates[feasible], cost[feasible]
        if not len(candidates):
            return None
        library = np.asarray(self.library)
        novelty = np.min(np.mean(
            (self.prior[candidates, None, :] - library[None, :, :])**2, axis=2
        ), axis=1)
        return int(candidates[np.argmax((novelty + 1e-6) / cost)])


class Network:
    """Shared FIFO byte server with reliable resumable transfer across contacts.

    No MAC, packet losses, ACKs, routing, motion-based contact or radio propagation.
    Receiver knowledge is updated only through decoded delivered payloads.
    """

    def __init__(self, env, link, log):
        self.env, self.link, self.log = env, link, log
        self.channel = simpy.Resource(env, capacity=1)
        self.enqueued_bytes = 0
        self.served_bits = 0.0
        self.delivered = 0
        self.queued = 0
        self.delays = []
        self.active_service = None

    def served_at(self, time_s):
        partial = 0.0
        if self.active_service is not None:
            start, duration, bits = self.active_service
            partial = bits * min(max(time_s - start, 0) / duration, 1)
        return self.served_bits + partial

    def send(self, observation, receiver):
        payload = observation.encode()
        self.enqueued_bytes += len(payload)
        self.queued += 1
        self.log("enqueue", observation.producer, oid=observation.oid,
                 receiver=receiver.node, payload_bytes=len(payload))
        self.env.process(self._transfer(payload, receiver))

    def _transfer(self, payload, receiver):
        observation = Observation.decode(payload)
        if self.link.bitrate_bps == 0:
            return
        with self.channel.request() as request:
            yield request
            self.log("service_start", observation.producer, oid=observation.oid)
            remaining = len(payload) * 8.0
            while remaining > 1e-8:
                if self.link.period_s:
                    phase = self.env.now % self.link.period_s
                    if phase >= self.link.contact_s - 1e-9:
                        yield self.env.timeout(self.link.period_s - phase)
                        continue
                    window = self.link.contact_s - phase
                else:
                    window = float("inf")
                duration = min(remaining / self.link.bitrate_bps, window)
                sent = remaining if np.isinf(self.link.bitrate_bps) else duration * self.link.bitrate_bps
                self.active_service = (self.env.now, duration, sent) if duration else None
                yield self.env.timeout(duration)
                remaining -= sent
                self.served_bits += sent
                self.active_service = None
            # Propagation doesn't hold the byte server.
        yield self.env.timeout(self.link.latency_s)
        self.delivered += 1
        self.queued -= 1
        self.delays.append(self.env.now - observation.generated_s)
        self.log("deliver", receiver.node, oid=observation.oid,
                 producer=observation.producer)
        receiver.receive(observation)


class Robot:
    def __init__(self, node, env, cfg, policy, start, measure, log, mode, plan):
        self.node, self.env, self.cfg = node, env, cfg
        self.policy, self.position = policy, np.array(start, dtype=float)
        self.measure, self.log, self.mode, self.plan = measure, log, mode, list(plan)
        self.visited, self.pending, self.observations = set(), [], []
        self.path = [self.position.tolist()]
        self.distance = 0.0
        self.decisions = []
        self.peer, self.network = None, None

    def receive(self, observation):
        self.pending.append(observation)

    def run(self):
        while True:
            # A decision uses only information delivered before decision start.
            for obs in self.pending:
                self.policy.observe(obs)
                self.log("consume", self.node, oid=obs.oid)
            self.pending.clear()
            remaining = self.cfg.budget_s - self.env.now
            target = self.plan.pop(0) if self.mode == "static" and self.plan else None
            if self.mode != "static":
                target = self.policy.choose(self.position, self.visited, remaining)
            if target is None:
                return
            distance = float(np.linalg.norm(self.policy.xy[target] - self.position))
            cost = self.cfg.decision_s + distance / self.cfg.speed_cells_s + self.cfg.sensing_s
            if cost > remaining + 1e-9:
                return
            self.decisions.append((float(self.env.now), target))
            self.log("decision", self.node, site=target, known_ids=sorted(self.policy.seen))
            yield self.env.timeout(self.cfg.decision_s)
            yield self.env.timeout(distance / self.cfg.speed_cells_s)
            self.distance += distance
            self.position = self.policy.xy[target].copy()
            self.path.append(self.position.tolist())
            self.log("arrive", self.node, site=target)
            yield self.env.timeout(self.cfg.sensing_s)
            observation = Observation(
                self.node * 1_000_000 + len(self.observations), self.node, target,
                float(self.env.now), self.measure(self.node, target)
            )
            self.observations.append(observation)
            self.visited.add(target)
            self.policy.observe(observation)
            self.log("sample", self.node, site=target, oid=observation.oid)
            if self.network is not None:
                self.network.send(observation, self.peer)


def static_plans(prior, xy, regions, starts, cfg):
    """Joint offline planning with prior proxy measurements and disjoint regions."""
    planners = [Policy(prior, xy, region, cfg) for region in regions]
    positions = [np.array(p, dtype=float) for p in starts]
    budgets, plans, visited = [cfg.budget_s] * 2, [[], []], [set(), set()]
    active = [True, True]
    while any(active):
        for node in range(2):
            if not active[node]:
                continue
            site = planners[node].choose(positions[node], visited[node], budgets[node])
            if site is None:
                active[node] = False
                continue
            cost = (np.linalg.norm(xy[site] - positions[node]) / cfg.speed_cells_s
                    + cfg.sensing_s + cfg.decision_s)
            budgets[node] -= cost
            positions[node] = xy[site]
            visited[node].add(site)
            plans[node].append(site)
            # Plans use only initial remote observations, never fine truth.
            for planner in planners:
                planner.library.append(prior[site].copy())
    return plans


def run_episode(world: World, mode: str, link: Link | None = None, trace=False):
    if mode not in ("static", "local", "shared"):
        raise ValueError(mode)
    if (mode == "shared") != (link is not None):
        raise ValueError("Only shared mode accepts and requires a link.")
    env, events = simpy.Environment(), []

    def log(event, node, **fields):
        if trace:
            events.append({"time_s": float(env.now), "event": event, "node": node, **fields})

    cfg, xy, prior = world.cfg, world.xy, world.prior
    width, height = world.shape[1], world.shape[0]
    left = xy[:, 0] < width / 2
    regions = [np.flatnonzero(~world.holdout & left), np.flatnonzero(~world.holdout & ~left)]
    starts = [(0, (height - 1) / 2), (width - 1, (height - 1) / 2)]
    plans = static_plans(prior, xy, regions, starts, cfg) if mode == "static" else [[], []]
    robots = [Robot(i, env, cfg, Policy(prior, xy, regions[i], cfg), starts[i],
                    world.measure, log, mode, plans[i]) for i in range(2)]
    network = Network(env, link, log) if link is not None else None
    for i, robot in enumerate(robots):
        robot.peer, robot.network = robots[1 - i], network
        env.process(robot.run())
    # Process events exactly at the deadline, but never flush network afterwards.
    while env.peek() <= cfg.budget_s:
        env.step()
    union = [obs for robot in robots for obs in robot.observations]
    result = {
        "mode": mode, "link": link.name if link else "none", "seed": world.seed,
        **world.evaluate(union),
        "samples": len(union),
        "unique_sites": len({o.site for o in union}),
        "distance_cells": sum(r.distance for r in robots),
        "enqueued_payload_bytes": network.enqueued_bytes if network else 0,
        "served_payload_bits": network.served_at(cfg.budget_s) if network else 0,
        "delivered_messages": network.delivered if network else 0,
        "undelivered_messages": network.queued if network else 0,
        "mean_delivery_delay_s": float(np.mean(network.delays)) if network and network.delays else None,
        "config": asdict(cfg), "provenance": world.provenance,
        "paths": [r.path for r in robots],
        "decisions": [r.decisions for r in robots],
    }
    return result, events
