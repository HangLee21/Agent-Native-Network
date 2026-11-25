# Custom link settings (H-009)

Import `get_defaults`, `normalize_settings`, `compile_scenario`, `state_at`,
`catalog` and `SettingsError` from
`simulation.mid_link_study.scenarios.custom`.

The shared schema is `mid.console.settings.v1`. `catalog()` returns the five
Chinese-named presets, complete defaults, field labels and numeric limits.
`get_defaults()` always returns a fresh normal preset; it never starts a job.
It restores all 20 directed edge rows, not just the currently selected pair.

Settings have `preset`, `duration_s` (10..120, default 60), `seed` (positive
integer), `fault_start_s` and `fault_end_s` (default 20 and 40), `offline_nodes`
(C/D/E only) and `links`. Each link row has:

| Field | Meaning |
|---|---|
| `src`, `dst` | Two distinct letters A..E; direction is explicit |
| `connected` | Whether the edge is present in the baseline topology for this run |
| `fail` | Disable the connected edge during the intervention window |
| `delay_ms` | One-way propagation during the window, 0..2000 milliseconds |
| `success_pct` | Per-attempt single-hop success during the window, 0..100 percent |
| `capacity_kbps` | Payload service budget during the window, 0.256..64 kbit/s |

The window is half open `[fault_start_s,fault_end_s)`. All three numeric
overrides and temporary failures restore their baseline values after it ends:
10 ms propagation, 100% success, and the reference branch capacity. The normal
preset makes no intervention. `connected=false` is the explicit whole-run
topology switch. All edges disconnected is valid and must yield a no-path
result rather than crash an initial-solver assertion.

UI edits apply to both directions by writing two rows. A one-way edit never
silently modifies its reverse. Partial settings and sparse link overrides are
accepted; normalization expands them into a complete canonical set of 20 rows.
Duplicate directed rows, unknown fields, non-finite values, invalid ranges and
failure on a disconnected baseline edge raise `SettingsError`. `as_dict()` gives
a field and a concise Chinese message suitable for the form.

`compile_scenario` produces a fresh scenario with a canonical settings hash,
the exact normalized snapshot, and segments. `state_at` returns each edge's
`delay_ms` and `propagation_delay_s`; a runner must use this custom accessor to
retain delay overrides. Serialization delay is additional. Propagation applies
to data and control. The runner declares when it samples an in-flight delay,
as well as queueing, capacity contention, observation and control assumptions.
The MID rate/probability objective does not become a delay-minimizing objective.

Software-only settings evidence and an actual two-link example are in
`simulation/outputs/H-009/20261107-01-settings/`. AC/CA fail during [20,40), while
CD/DC use 750 ms, 75% success and 4.096 kbit/s in that same window. Boundary
snapshots confirm that all parameters restore at exactly t=40. This is not a
packet-engine or browser test; those belong to E1-020/E2-020/D-019.

Finite reproduction to a fresh directory:

```powershell
& '.local/espnow/E1-015/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe' simulation/mid_link_console/settings/check_settings.py --output simulation/outputs/H-009/<new-run-id>
```

Historical M-021 inputs and results remain separate. This module never opens a
serial port, writes hardware, starts a server or invokes a solver.
