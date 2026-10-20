"""Real airborne data proxy: test spectral observation value BEFORE networking.

Fixed sample-count budgets, no paths, no Agent, no original-paper reproduction.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import loadmat
from scipy.optimize import nnls

from simulation.fetch_cuprite import COMMIT, FILES

BUDGETS = (0, 4, 8, 16, 32)
PATCHES = {"development": (0, 0), "A": (0, 100), "B": (90, 0), "C": (170, 100)}


def prepare(path):
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != FILES["Datasets/Cuprite/Cuprite_data_R188.mat"]:
        raise ValueError("This experiment is preregistered to the pinned Cuprite file.")
    data = loadmat(path)
    raw = data["Y"].astype(float)
    bands = data["SlectBands"].ravel()
    # Do not reinterpret unsigned negatives without calibration metadata.
    # Only original band index 3 contains >10000 values, separated from rest.
    bad = np.any(raw > 10000, axis=1)
    if bands[bad].tolist() != [3]:
        raise ValueError("Unexpected QC mask; review before rerunning.")
    good = raw[~bad].T
    norms = np.linalg.norm(good, axis=1)
    if np.any(norms == 0) or not np.isfinite(good).all():
        raise ValueError("Invalid spectrum.")
    normalized = good / norms[:, None]
    h, w = int(data["nRow"].item()), int(data["nCol"].item())
    cube = normalized.reshape(h, w, -1, order="F")
    # Nine artificial broad channels, NOT ASTER response functions.
    groups = np.array_split(np.arange(cube.shape[-1]), 9)
    response = np.zeros((cube.shape[-1], 9))
    for i, group in enumerate(groups):
        response[group, i] = 1 / len(group)
    return cube, response, {
        "sha256": hashlib.sha256(content).hexdigest(),
        "actual_shape": [h, w, len(bands)],
        "readme_shape_discrepancy": "README says 250x191; MAT nCol=190, Y has 47500 pixels.",
        "dropped_original_band_ids": bands[bad].astype(int).tolist(),
        "abnormal_entries": int(np.sum(raw > 10000)),
        "kept_original_band_ids": bands[~bad].astype(int).tolist(),
        "normalization": "Per-pixel L2 norm over remaining 187 channels; no reflectance scaling claimed.",
        "reshape": "MATLAB column-major convention; georeferencing and orientation not independently verified.",
        "response": response.tolist(),
    }


def select_diverse(features, initial, count):
    """Farthest-first coverage in observed feature space, no high spectra access."""
    distance = ((features[:, None, :] - initial[None, :, :])**2).sum(axis=2).min(axis=1)
    selected = []
    for _ in range(count):
        idx = int(np.argmax(distance))
        selected.append(idx)
        new_distance = ((features - features[idx])**2).sum(axis=1)
        distance = np.minimum(distance, new_distance)
        distance[selected] = -np.inf
    return np.array(selected)


def reconstruct(remote, library, response):
    """Nonnegative linear mixing fitted ONLY to remote channels, not test spectra."""
    design = (library @ response).T
    prediction = np.empty((len(remote), library.shape[1]))
    for i, observation in enumerate(remote):
        coefficients, _ = nnls(design, observation, maxiter=1000)
        prediction[i] = coefficients @ library
    return prediction


def rmse(predicted, truth):
    return float(np.sqrt(np.mean((predicted - truth)**2)))


def patch_data(cube, origin):
    y, x = origin
    patch = cube[y:y+80, x:x+80]
    yy, xx = np.indices((80, 80))
    # Candidate and evaluation sets fixed and disjoint for every seed/policy.
    candidate_mask = (yy % 5 == 2) & (xx % 5 == 2)
    available_eval = np.flatnonzero(~candidate_mask.ravel())
    eval_ids = np.random.default_rng(912).choice(available_eval, 256, replace=False)
    xy = np.column_stack([xx[candidate_mask], yy[candidate_mask]])
    return patch[candidate_mask], patch.reshape(-1, patch.shape[-1])[eval_ids], xy


def run(path, output, seeds=12):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output folder.")
    output.mkdir(parents=True, exist_ok=True)
    cube, response, qc = prepare(path)
    dev, _, _ = patch_data(cube, PATCHES["development"])
    dev_remote = dev @ response
    # Initial calibration library is disjoint from ALL evaluation patches.
    initial_indices = select_diverse(dev_remote, dev_remote.mean(axis=0, keepdims=True), 4)
    initial_library = dev[initial_indices]
    rows = []
    for patch_id, origin in PATCHES.items():
        if patch_id == "development":
            continue
        candidates, evaluation, xy = patch_data(cube, origin)
        remote, test_remote = candidates @ response, evaluation @ response
        baseline = rmse(reconstruct(test_remote, initial_library, response), evaluation)
        for seed in range(seeds):
            rng = np.random.default_rng(seed)
            noise = rng.normal(0, 0.002, candidates.shape)
            policies = {
                "random": rng.permutation(len(candidates))[:32],
                "spatial_coverage": select_diverse(xy.astype(float), np.array([[39.5, 39.5]]), 32),
                "spectral_coverage": select_diverse(remote, initial_library @ response, 32),
            }
            for policy, indices in policies.items():
                for quality in ("noiseless_proxy", "noisy_proxy", "remote_only_control"):
                    for count in BUDGETS:
                        picked = indices[:count]
                        if quality == "remote_only_control":
                            # Same number of library columns, no new high-band information.
                            added = reconstruct(remote[picked], initial_library, response)
                        else:
                            added = candidates[picked].copy()
                            if quality == "noisy_proxy":
                                added = np.maximum(added + noise[picked], 0)
                        library = np.vstack([initial_library, added])
                        error = rmse(reconstruct(test_remote, library, response), evaluation)
                        rows.append({
                            "patch": patch_id, "seed": seed, "policy": policy,
                            "quality": quality, "extra_samples": count,
                            "heldout_normalized_rmse": error, "baseline_rmse": baseline,
                            "relative_reduction_pct": (baseline-error) / baseline * 100,
                            "sample_ids": picked.tolist(),
                        })
        print(f"Completed patch {patch_id}", flush=True)
    (output/"episodes.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    fields = list(rows[0])[:-1]
    with (output/"metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for patch in ("A", "B", "C"):
        for policy in ("random", "spatial_coverage", "spectral_coverage"):
            for quality in ("noiseless_proxy", "noisy_proxy", "remote_only_control"):
                for count in BUDGETS:
                    selected = [r for r in rows if (r["patch"],r["policy"],r["quality"],r["extra_samples"])
                                == (patch,policy,quality,count)]
                    summary.append({
                        "patch": patch,"policy": policy,"quality": quality,"extra_samples": count,
                        "mean_rmse": float(np.mean([r["heldout_normalized_rmse"] for r in selected])),
                        "min_rmse": min(r["heldout_normalized_rmse"] for r in selected),
                        "max_rmse": max(r["heldout_normalized_rmse"] for r in selected),
                        "mean_reduction_pct": float(np.mean([r["relative_reduction_pct"] for r in selected])),
                    })
    with (output/"summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(summary[0]))
        writer.writeheader();writer.writerows(summary)
    metadata = {
        "data_kind": "author_distributed_airborne_benchmark_with_synthetic_remote_channels",
        "author_commit": COMMIT,"data_paper": "https://doi.org/10.1186/s40323-025-00313-6",
        "access_terms": "Author repository GPL-3.0; README permits research/education subject to original data terms. Raw data not redistributed here.",
        "qc": qc,"patches": PATCHES,"patch_size":80,"evaluation_pixels_per_patch":256,
        "initial_library_size":4,"initial_dev_candidate_ids":initial_indices.tolist(),
        "budgets":BUDGETS,"seeds":list(range(seeds)),
        "noise_std_on_unit_spectrum":0.002,"measurement_budget_only":True,
        "test_high_spectra_used_only_for_scoring":True,
        "python":platform.python_version(),
        "packages":{n:importlib.metadata.version(n) for n in ("numpy","scipy","matplotlib")},
        "source_sha256":{str(p).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [Path("simulation/validate_observation.py"),Path("simulation/fetch_cuprite.py")]},
        "limitations":["No actual ground measurements or ASTER pairing.",
                       "No wavelength calibration, mineral labels, abundance truth or georeferencing.",
                       "No traversal-time budget or network. Not a P31 reproduction.",
                       "Deterministic noiseless policies repeat across seeds; seeds are not independent sites."],
    }
    (output/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    fig, axes=plt.subplots(1,3,figsize=(13,4),layout="constrained")
    for ax, patch in zip(axes,("A","B","C")):
        for policy in ("random","spatial_coverage","spectral_coverage"):
            for quality,style in (("noisy_proxy","-"),("remote_only_control","--")):
                subset=[r for r in summary if (r["patch"],r["policy"],r["quality"])==(patch,policy,quality)]
                ax.plot(BUDGETS,[r["mean_rmse"] for r in subset],style,
                        label=f"{policy} / {'proxy' if style=='-' else 'control'}")
        ax.set_title(f"Patch {patch}");ax.set_xlabel("Additional measurement count")
        ax.set_ylabel("Held-out unit-spectrum RMSE");ax.grid(alpha=.2)
    axes[-1].legend(fontsize=7)
    fig.suptitle("Cuprite airborne proxy | artificial 9-channel prior | NOT a network experiment")
    fig.savefig(output/"observation_value.png",dpi=160);plt.close(fig)
    return rows


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("data/cuprite/Cuprite_data_R188.mat"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seeds",type=int,default=12)
    args=parser.parse_args()
    if args.seeds<1:parser.error("seeds must be positive")
    run(args.data,args.output,args.seeds)
