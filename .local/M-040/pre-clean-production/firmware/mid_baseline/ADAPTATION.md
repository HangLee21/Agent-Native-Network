# MID adaptation audit

Fixed candidate source: danmox/miod d4ba825cb2068301f7811e522c4cc44092796e1e. Private task-local source only, no author code republished. D-015 determines license and TRO correspondence; until then all results say candidate-source adaptation.

| Behavior | Author evidence | This checkpoint |
|---|---|---|
| SOCP | socp/src/socp/rr_socp.py: solve_socp/cone_constraints; server invokes RobustRoutingSolver | Independent matrix-input formulation, destination skipped, sqrt(variance), nonnegative common slack, incoming/outgoing availability; no SDP/motion |
| Channel input | channel_model.py PathLossModel.predict; explicit N0,n,L0,a,b; launch b differs from default | Input predicted mean/variance matrices or Nx2 positions plus all explicit N0,n,L0,a,b; no default physical calibration or online learner |
| Table | network_planner.py update_routes emits executor/src/dst/gateways, threshold >0.01 | Same threshold, preserve all indices; quantize normalized weights to u16 |
| Same-source two destinations | main_srv.py global_rt_update_thread indexes update[node][src], overwriting destination | Fix: key full (src,dst) per executor, explicit two-flow bound; record difference |
| Sampling | main_cli.py rt_update_thread, main_srv.py local_rt_update_thread: coin uniform(0,sum(weights)), cumulative loop with no break | One weighted gateway every500ms, break after first match; source behavior logged separately |
| Linux commands | route del then route add, errors hidden, later matched add attempts can fail with EEXIST | Host probe models first-success semantics, not verified Linux execution. No claim that the final loop gateway is actual installed route. ESP executor checks concrete adapter results in next phase |
| Propagation | main_srv.py periodic broadcast [HOST,seq,table]; main_cli.py status_receive_update_thread dedup+rebroadcast | Bounded single-frame ESP-NOW flood, same original identity; configured publisher boot adds explicit restart boundary; TTL8 replaces IP TTL |
| Transport | Linux IP/UDP/Wi-Fi ad-hoc | ESP-NOW MAC datagrams, raw payload<=160, no IP/TCP equivalence, encryption/authentication absent; bench isolation required |

## OLED reuse decisions

Direct reuse after H-005 freeze: H-00421 SSD1306 driver, GPIO18/17/21/36, PRG0 page-only control, 50ms I2C timeouts, low-priority renderer, length1 overwrite queue, MAC A/? identity. Existing evidence is H's first-board confirmation, not MID evidence.

Must adjust through H-owned module: mode MID, command help matching eventual MID parser, destination/current selected gateway, config accepted, submitted/link callback/local-destination RX/drop counters. Source has no end-to-end ACK; show unconfirmed even after link success. E1 supplies actual event snapshots without changing H's module.

Checkpoint1 deferred linkage pending H. Stage2 consumes H FREEZE SHA256 `2d72ee784757d881a6b77108bf886e5e6e0591934c94693d5baee0330e4da9aa`, links unchanged production sources and contributes their hashes to the new MID build_id. No headless image is released. Mobility/SDP, original six-node experiments, calibrated radio rates and physical performance remain outside this stage.

## Actual compatibility finding

The unmodified candidate rr_socp.py solve_socp fails on installed CVXPY1.7.4 at `cp.sum(routing_sum_mat, 2)` (2D matrix, axis2 invalid). Preserve the failure in author-comparison.json. Our formulation explicitly constrains column and row sums <=1; no private author-file patch was applied. The independent solution satisfies all four author cone coefficient residuals at tolerance1e-6, but this does not establish original-solver execution equivalence. Historical CVXPY environment and intended availability axes require D/E2/C review before final baseline freeze.

Stage2 decision: D SOURCE_AUDIT SHA256 `f67765d0be9ed576f97413a38ac4f27a627388da5131ea08ec1f0bc7eb92fdb5` and M-018-stage2 confirm paper's incoming/outgoing sums correspond to axis0/axis1 on the aggregated NxN matrix. This explicit repair is approved for local candidate adaptation, retaining historical-environment uncertainty. D/E2/C review of final artifacts still applies; unknown final experiment commit is not a dependency to compile.

Radio adapter bounds: 16 input copies/16 TX entries, exactly one outstanding send, MAC-linked callback, local1000ms queue/callback timeout. Input overflow or missing callback stops radio and requires reset before restart. These are finite ESP execution/protection constraints, not new end-to-end delivery timers or retries. ESP-NOW link-layer callbacks may fail even when some receivers got data, especially broadcast. Only validated unique destination-local RX maps to H RX_DEST. Actual OLED hardware initialization remains H's driver with no edits, including fault isolation and page-only PRG. A/B labels are supplied externally from verified actual MACs; frozen fallback registry unchanged.
