# H-011 measured baseline

Import `simulation.mid_link_console.settings.measured`. Its schema is
`mid.measured.settings.v1`; API: `get_snapshot()`, `get_defaults('measured')`,
`normalize_settings`, `compile_scenario`, `state_at`, `preview`, `catalog`,
`settings_hash`. Defaults are A to C, unlimited hops, one direction, 60 simulated
seconds, no faults. A fresh reset restores all 20 directed rows.

`measured_snapshot.json` derives from H-006's final complete L01..L10 link
captures: 10 packets/s, 32 payload bytes, 10 seconds and 100 accepted/submitted
packets in each direction. All 20 directions recorded 100 unique endpoint
deliveries. Each edge stores its own counts, ten one-second windows, observed
service (2560 payload bit/s), variance, source paths/hashes and row indices.
Directions are never averaged together or mirrored. Coinciding values in this
particular capture do not establish physical reciprocity.

Per-run UTC start times come from the original hardware-run ledgers. They range
from 2026-11-07T02:17:28.624900+00:00 to 02:21:28.143999+00:00 (10:17..10:21
Beijing time). This is a range of *run starts*, not the end of sampling.
Individual directional intervals are preserved as host monotonic nanoseconds;
there is no UTC/monotonic anchor, so exact directional UTC and capture-end UTC
remain null. The later 02:24 processing-manifest timestamps are not used as
measurement times. Snapshot generation time is separate.

`snapshot.edges[].measured.one_way_delay_ms` is null. `defaults.delay_ms=10` is an
explicit editable simulation assumption. No cross-board clock subtraction is
used. `capacity_kbps=2.56` maps the *observed injected-load service* to an editable
simulation service budget; it is not measured saturated radio capacity.
Likewise the historical delivery fraction is not a guaranteed or calibrated
per-attempt RF probability. The mapping to the simulator's success model is
explicit in `parameter_provenance`. Suggested UI labels: historical delivery
fraction, observed payload service, model propagation delay, simulation budget.

Each source edge has `measured`, `defaults`, `capture`, `sources`, and
`parameter_provenance`. Return the snapshot with the default form so the same
page can show provenance without claiming a new measurement. Editing changes
the draft only, never this file or raw captures. `snapshot_id` binds a draft to
this frozen baseline; a mismatch is rejected with a reset instruction.

The input link fields retain M-022/023 semantics: `connected=false` disables a
logical edge for the whole run; `fail`, success/rate/delay overrides apply only
in `[fault_start_s,fault_end_s)`; outside it each direction restores its measured
baseline (plus the explicitly modeled delay). `compile_scenario` replaces the
legacy hardcoded 8.192/4.096 kbit/s base values with the snapshot. Runners must
consume this compiled scenario and accessor, not silently recompile with the
old routing defaults. E1 owns worker dispatch. Algorithms selected for physical
hardware remain subject to the existing 8766 capabilities; this snapshot does
not grant remote control of actual RF probability/delay.

Evidence: H-011/20261108-01-snapshot and 02-settings under simulation/outputs.
Twelve finite checks plus five invalid inputs passed, including complete reset,
two independent directed edits, exact restoration and a **synthetic** asymmetric
fixture. That fixture is not hardware data. H opened no ports, ran no solver,
and did not trigger new RF or packet simulation.
