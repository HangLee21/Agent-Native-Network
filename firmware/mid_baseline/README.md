# MID candidate ESP-NOW adaptation

This delivers the Planner, bridge, wire/core and ESP32-S3 adapter in idf/, linked to H's frozen mid_display. D-015 and M-018-stage2 authorize the explicit candidate-source repairs; original TRO experiment version and whole-repo license remain unknown. Existing ANN+OLED source/packages are preserved. Only a package with a successful target-build manifest may be flashed by H after E2/C readiness checks.

Read INTERFACE.md and ADAPTATION.md before consuming FREEZE.json. Test identities `02:00:00:00:00:01` etc. are synthetic and must never be substituted for real board bindings.

## Executable host entry points

From repository root, using the isolated E1-016 environment:

```powershell
& '.local/mid/E1-016/venv/Scripts/python.exe' tools/mid_baseline/planner/planner.py simulation/outputs/E1-016/20261106-01-candidate-check/problem.json --output <new-solution.json>
```

Planner input: explicit ordered node MACs, flows `{src,dst,rate,qos}`, NxN nonnegative model mean/variance matrices and channel_provenance. Alternatively supply `positions` (Nx2) and `channel_parameters` containing all five explicit `N0,n,L0,a,b` values, with provenance. Rates are model units; they are not measured ESP-NOW throughput/PDR. No physical-model defaults, automatic calibration, ROS dependency, SDP or motion. Solver is CLARABEL; status must be optimal before packaging. The solution contains both raw routing variables and a NetworkUpdate-like `update` object. The bridge consumes that object as a standalone JSON file, not the surrounding solution wrapper.

```powershell
& '.local/mid/E1-016/venv/Scripts/python.exe' tools/mid_baseline/bridge/bridge.py simulation/outputs/E1-016/20261106-01-candidate-check/network_update.json --publisher 02:00:00:00:00:01 --boot 17 --seq 2 --nonce sample --output <new-command.json>
```

Both entries require new output filenames and refuse overwrite. bridge.py generates an offline JSON config command. publish.py is a separate H-operated bounded serial publisher: explicit --port/--publisher/--boot/--first-seq/--count(1..60)/--output, one new publication per second. It checks the entry's actual info identity/boot and active state before publishing, closes the port on exit, never auto-starts/stops nodes or flashes. H owns final scenario stop. E1 has not executed this hardware path. Source code compiling does not prove physical display or radio performance.

## Hardware commands for H

Read info on A/B to verify the new build and labels. All examples require a newline:

```json
{"schema":"mid.serial.v1","cmd":"info","nonce":"identify-A"}
{"schema":"mid.serial.v1","cmd":"stats","nonce":"stats-A"}
{"schema":"mid.serial.v1","cmd":"stop","nonce":"stop-A"}
```

Then start both peers with `publisher` equal to A MAC90:da:72:48:a4:f8 and `publisher_boot` equal to A's current numeric boot_id from info. Use `cmd:start` and a unique nonce on each. B's own identity is MAC90:da:72:48:a5:cc. Pack the explicit A/B NetworkUpdate with A's boot and a fresh increasing config seq. Feed the resulting config command only to A; control broadcast updates B. Wait for config_applied and route_selected on the appropriate nodes before data. `cmd:send` requires `dst` and `payload_hex`; e.g. A sends `dst:"90:da:72:48:a5:cc",payload_hex:"6869"`. Read B's rx_local with original source/boot/seq; source link_ok remains destination unconfirmed. Two-board success is single-link functionality, not multihop/coverage benefit.

The same image supports A/B labels and unknown C–E. All are peers; reverse flow must be in the configured table for B to originate a reply. There is no echo/ACK auto-response. Radio remains off at boot. MID mode uses separate CLI and never invokes ANN routes. Do not use old ANN arm/bench commands. On callback timeout or input overflow reset is needed after recording failure; no automatic retry/reset. Inspect stopping and radio fields after stop before considering it fully quiescent.

## C execution core

`mid.h`/`mid.c` are platform independent C99. Decode full frame before calling mid_config/mid_data. A single adapter task owns mid_node; callbacks enqueue bounded copies. mid_init takes actual self MAC and explicit publisher MAC/boot. mid_tick requires an unbiased uniform draw in [0,65534] per flow, supplied at each500ms period (adapter must use rejection sampling, not biased `%65535`). Select a gateway once per period; retain it for every packet in the period. Upon new config invalidate old choices until next eligible tick. On control acceptance, adapter rebroadcasts only if remaining TTL>1. On data result1, send to returned next MAC with TTL decremented; result2 emits destination-local receive; negative errors cannot be counted as delivery. No retransmission or ACK is added.

The core's64-entry data dedup cache is bounded. Consumers must not infer unlimited exactly-once delivery. A new run requires explicit binding; seq does not wrap. Publisher/boot checks are isolation guards, not cryptographic authentication.

## Validation and handoff

Host outputs01/02 preserve the original checkpoint, including the unmodified author solver failure. Target build/inspection outputs are separate later run IDs, with final package path/hash in the live E1-016 card and FREEZE.json. No E1 ports, flash, board startup or RF tests. E2/C independently review the final exact hashes, then H owns identity/backup checks and physical deployment. No software preview or I2C frame ACK is a user pixel observation.
