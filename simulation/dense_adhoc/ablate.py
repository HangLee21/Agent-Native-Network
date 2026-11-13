"""Cumulative ablation: start from the baseline policy and switch on one dense-adhoc
change at a time, keeping earlier changes, so each step's contribution is attributable.
"""
import json
import sys

sys.path.insert(0, r"D:\Multi-Agent Network\simulation\dense_adhoc")
import sim as S

STEPS = [
    ("0-base", dict()),
    ("1-nolock-q64", dict(lock_on_overflow=False, input_queue=64)),
    ("2-tables32", dict(nd_peers=32, sr_peers=32, sr_routes=32, sr_seen=128, sr_pending=16)),
    ("3-no-ack", dict(ack="mutual")),
    ("4-adaptive-hello", dict(hello_max=8000)),
    ("5-no-warm", dict(warm=False)),
    ("6-ring-origin-dedupe", dict(rreq="ring", rreq_dedupe="origin", rreq_rate_ms=500)),
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    out = sys.argv[3] if len(sys.argv) > 3 else "ablation.json"
    rows, cum = [], {}
    for label, delta in STEPS:
        cum.update(delta)
        cfg = dict(S.BASE)
        cfg.update(cum)
        same = all(cfg.get(k) == v for k, v in S.DENSE.items())
        for s in range(seeds):
            r = S.measure(n, cfg, 1000 + s, 1_000_000)
            r["policy"] = label
            r["equals_dense"] = same
            rows.append(r)
            print(label, json.dumps({k: r[k] for k in
                                     ("alive", "nodes_locked", "control_per_s", "steady_ack_s",
                                      "frames_dropped", "route_ok_ratio",
                                      "rreq_frames_per_discovery", "max_queue",
                                      "convergence_ms")}), flush=True)
    json.dump(rows, open(out, "w"), indent=2)
    print("wrote", out)


if __name__ == "__main__":
    main()
