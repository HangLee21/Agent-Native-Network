"""Synthetic mobility replay + LET shadow evaluation.

Two things this tool deliberately does not do: it never claims synthetic data is a
measurement, and it never feeds the firmware's router. It produces (a) a reproducible
trajectory log and (b) an honest score for the geometric LET prediction against the
ground-truth moment a link actually leaves range.

Usage
  python -m tools.mid_baseline.mobility.let_shadow simulate --scenario S2 --seed 1 \
      --duration 60 --out out/shadow.jsonl
  python -m tools.mid_baseline.mobility.let_shadow eval --log out/shadow.jsonl
"""
import argparse
import json
import math
import random
from pathlib import Path

RANGE_MM = 120_000          # same default as mobility.h
SIGMA_K = 2.0
LET_CAP_MS = 3_600_000


def relative(a, b):
    r = [b["p"][i] - a["p"][i] for i in range(3)]
    u = [b["v"][i] - a["v"][i] for i in range(3)]
    return r, u


def let_ms(r, u, range_mm=RANGE_MM):
    """Exit time of |r + u t| = R, in ms. None means 'no finite prediction'."""
    d2 = sum(x * x for x in r)
    if d2 >= range_mm * range_mm:
        return 0
    speed2 = sum(x * x for x in u)
    if speed2 < 1.0:
        return None
    dot = sum(r[i] * u[i] for i in range(3))
    b, a, c = 2.0 * dot, speed2, d2 - range_mm * range_mm
    disc = b * b - 4.0 * a * c
    if disc < 0:
        return None
    t = (-b + math.sqrt(disc)) / (2.0 * a)
    ms = t * 1000.0
    return None if ms <= 0 or ms > LET_CAP_MS else ms


def scenario(name, seed):
    """Return (duration_ms, step_ms, states) with states a function of t."""
    rnd = random.Random(seed)
    if name == "S1":        # steady formation, co-moving
        return 60_000, 100, lambda t: [
            dict(id="A", p=[0.0, 0.0, 50_000], v=[15_000.0, 0.0, 0.0]),
            dict(id="B", p=[0.0, 60_000.0, 50_000], v=[15_000.0, 0.0, 0.0]),
        ], rnd
    if name == "S2":        # head-on crossing, 50 m/s relative
        return 60_000, 100, lambda t: [
            dict(id="A", p=[-150_000.0 + 25_000.0 * t, 0.0, 50_000], v=[25_000.0, 0.0, 0.0]),
            dict(id="B", p=[+150_000.0 - 25_000.0 * t, 20_000.0, 50_000], v=[-25_000.0, 0.0, 0.0]),
        ], rnd
    if name == "S3":        # split: B turns away after 10 s
        def s3(t):
            T = min(t, 10.0)
            turn = max(0.0, t - 10.0)
            return [
                dict(id="A", p=[15_000.0 * t, 0.0, 50_000], v=[15_000.0, 0.0, 0.0]),
                dict(id="B", p=[15_000.0 * T, 60_000.0 + 15_000.0 * turn, 50_000],
                     v=[0.0 if turn > 0 else 15_000.0, 15_000.0 if turn > 0 else 0.0, 0.0]),
            ]
        return 60_000, 100, s3, rnd
    if name == "S6":        # sudden stop of B at 12 s (no geometric warning expected)
        def s6(t):
            T = min(t, 12.0)
            return [
                dict(id="A", p=[15_000.0 * t, 0.0, 50_000], v=[15_000.0, 0.0, 0.0]),
                dict(id="B", p=[15_000.0 * T + 40_000.0, 30_000.0, 50_000],
                     v=[15_000.0 if t < 12 else 0.0, 0.0, 0.0]),
            ]
        return 60_000, 100, s6, rnd
    raise SystemExit("unknown scenario " + name)


def simulate(args):
    duration_ms, step_ms, states_at, rnd = scenario(args.scenario, args.seed)
    out = []
    t = 0
    while t <= duration_ms:
        a, b = states_at(t / 1000.0)
        r, u = relative(a, b)
        dist = math.sqrt(sum(x * x for x in r))
        truth_break = dist >= RANGE_MM
        # measured state = true state + declared error
        def noisy(node):
            acc, vacc = 8_000, 800
            return dict(p=[node["p"][i] + rnd.gauss(0, acc) for i in range(3)],
                        v=[node["v"][i] + rnd.gauss(0, vacc) for i in range(3)],
                        accuracy_mm=acc, velocity_accuracy_mm_s=vacc)
        na, nb = noisy(a), noisy(b)
        rn, un = relative(na, nb)
        let = let_ms(rn, un)
        speed = math.sqrt(sum(x * x for x in un))
        if let is None:
            low = high = None
            conf = 500
        else:
            sigma_r = math.sqrt(na["accuracy_mm"] ** 2 + nb["accuracy_mm"] ** 2)
            sigma_v = math.sqrt(na["velocity_accuracy_mm_s"] ** 2 + nb["velocity_accuracy_mm_s"] ** 2)
            sigma_t = (sigma_r / speed if speed > 1 else 0) + (let / 1000.0) * (sigma_v / speed if speed > 1 else 0)
            band = SIGMA_K * sigma_t * 1000.0
            low = max(0.0, let - band)
            high = min(LET_CAP_MS, let + band)
            conf = int(max(0, min(1000, 1000 * (1 - band / (let + 1.0)))))
        risk = "GOOD"
        if conf < 300:
            risk = "INCONCLUSIVE"
        elif low is not None:
            risk = "AT_RISK" if low <= 3000 else "DEGRADING" if low <= 8000 else "GOOD"
        out.append(dict(
            t_ms=t, scenario=args.scenario, seed=args.seed, data_kind="synthetic",
            distance_mm=round(dist, 1), closing_mm_s=round(-sum(r[i] * u[i] for i in range(3)) / max(dist, 1), 1),
            let_ms=None if let is None else round(let, 1),
            let_low_ms=None if low is None else round(low, 1),
            let_high_ms=None if high is None else round(high, 1),
            confidence=conf, risk=risk, truth_out_of_range=truth_break))
        t += step_ms
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in out:
            fh.write(json.dumps(row) + "\n")
    print(json.dumps(dict(status="ok", scenario=args.scenario, rows=len(out), output=str(path),
                          data_kind="synthetic", never_a_measurement=True)))


def evaluate(args):
    rows = [json.loads(line) for line in Path(args.log).read_text(encoding="utf-8").splitlines() if line.strip()]
    breaks, prev = [], None
    for row in rows:
        if prev is not None and row["truth_out_of_range"] and not prev["truth_out_of_range"]:
            breaks.append(row["t_ms"])
        prev = row
    # a prediction "covers" a break when its conservative window reaches it
    detected = {b: None for b in breaks}
    false_alarms, warnings = 0, 0
    for row in rows:
        if row["let_low_ms"] is None:
            continue
        lo = row["t_ms"] + row["let_low_ms"]
        hi = row["t_ms"] + row["let_high_ms"]
        near = [b for b in breaks if lo <= b <= hi]
        if near:
            warnings += 1
            for b in near:
                if detected[b] is None or row["t_ms"] < detected[b]:
                    detected[b] = row["t_ms"]
        elif row["risk"] in ("DEGRADING", "AT_RISK"):
            false_alarms += 1
    lead = [b - t for b, t in ((b, detected[b]) for b in breaks) if t is not None]
    # Error is only meaningful for predictions whose conservative window actually reaches
    # the break; a row 40 s before a turn cannot be scored against it.
    err = []
    for row in rows:
        if row["let_ms"] is None or row["truth_out_of_range"] or row["confidence"] < 300:
            continue
        lo = row["t_ms"] + row["let_low_ms"]
        hi = row["t_ms"] + row["let_high_ms"]
        for b in breaks:
            if lo <= b <= hi:
                err.append(abs(row["t_ms"] + row["let_ms"] - b) / 1000.0)
                break
    summary = dict(
        scenario=args.log, data_kind="synthetic",
        breaks=len(breaks),
        detected=sum(1 for b in breaks if detected[b] is not None),
        recall=round(sum(1 for b in breaks if detected[b] is not None) / len(breaks), 3) if breaks else None,
        warning_rows=warnings,
        false_alarm_rows=false_alarms,
        precision=round(warnings / (warnings + false_alarms), 3) if (warnings + false_alarms) else None,
        mean_lead_s=round(sum(lead) / len(lead) / 1000.0, 2) if lead else None,
        min_lead_s=round(min(lead) / 1000.0, 2) if lead else None,
        mean_abs_error_s=round(sum(err) / len(err), 2) if err else None,
        note="geometric truth only; no RF measurement is modelled or claimed")
    print(json.dumps(summary, indent=1))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate")
    s.add_argument("--scenario", default="S2", choices=["S1", "S2", "S3", "S6"])
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--duration", type=int, default=60)
    s.add_argument("--out", required=True)
    e = sub.add_parser("eval")
    e.add_argument("--log", required=True)
    a = p.parse_args()
    (simulate if a.cmd == "simulate" else evaluate)(a)


if __name__ == "__main__":
    main()
