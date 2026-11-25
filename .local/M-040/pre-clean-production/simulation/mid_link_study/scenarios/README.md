# Five-node assumed link scenarios

These files are **software simulation inputs**, not RF measurements. The node
letters are simulation identifiers. They do not open or bind physical devices.

Import `IDS`, `load(id)` and `state_at(scenario, time_s)` from `scenarios.py`.
The state contains active nodes and directed edges. Each edge separates
`capacity_payload_bps` (application-payload service budget) from `pdr`
(conditional success probability per attempt). `expected_payload_bps` is their
product, not a calibrated capacity estimate. Unlisted edges have both zero.
Segments override the base state during `[start_s,end_s)` and interpolate PDR
linearly. Offline nodes have all incident edges set to zero.

Every scenario lasts 60 simulated seconds. A and B each generate 2 packets/s,
32 bytes/packet, at times 0, 0.5, ..., 59.5. Use paired seeds 11, 23, 37, 53, 71
for 3 scenarios x 2 strategies x 5 seeds = 30 runs and 7,200 planned packets.
The packet engine declares its observation/detection/configuration delays,
queueing, capacity contention and retransmission assumptions separately.

The initial reference chain is A-C-D-B. A-E-D-B remains an alternative with
half the branch capacity. The solver is free to choose its own valid weights;
these named paths are witnesses, not a prescribed solution.

| Input | Change | Endpoint path existence |
|---|---|---|
| `gradual_link.json` | AC/CA PDR drops 1 to 0 from t=20 to 35; stays 0 until 45; rises to 1 at 50 | Alternate path always exists |
| `relay_exit.json` | C offline in [20,40) | Alternate path always exists |
| `partition_restore.json` | DB/BD absent in [20,40), isolating B | No endpoint path during [20,40) |

The independent evaluation truth includes directed BFS path witnesses at source
generation slots and around every change boundary. It tests positive-probability
connectivity only: a path can exist yet be unable to meet a requested rate or
deadline. Do not feed the truth report to a strategy as an immediate observation.

Recheck the inputs and write new truth evidence without replacing any history:

```powershell
& '.local/espnow/E1-015/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe' simulation/mid_link_study/scenarios/scenarios.py --output simulation/outputs/H-008/<new-run-id>
```

`--write-inputs` is for first construction only; it exclusively creates the three
JSON inputs and refuses to overwrite them. Initial evidence is in
`simulation/outputs/H-008/20261107-01-scenario-truth/`. The engine, independent
packet analysis and presentation are owned by E1-019, E2-019 and D-018.
