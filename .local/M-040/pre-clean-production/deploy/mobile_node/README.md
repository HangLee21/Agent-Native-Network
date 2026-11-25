# Mobile node on a Raspberry Pi

Run one local edge service for the car's ESP32, then start this node against its loopback port. The node uses that service's business and observation APIs. The edge service keeps exclusive ownership of the serial port. Use Python 3.10 or newer; the node itself uses the standard library. The serial owner needs its existing pyserial dependency and saved board configuration. The Ubuntu edge setup is described in `deploy/ubuntu/README.md`.

From the repository root, start telemetry and random traffic together:

```sh
sh deploy/mobile_node/node.sh --edge-port 8780 --state .local/mid/E2-028/car-A --label A --gateway http://127.0.0.1:8790 --agent --dest 90:da:72:48:a4:e0 --seed 11
```

On a Pi, replace the gateway base URL with the laptop's reachable LAN address. Its default port is 8790. Omitting `--gateway` keeps local observation logs and the bounded report queue. Stop with Ctrl+C or SIGTERM. `--duration 30` gives a finite run. Startup prints the local edge URL and log directory. A node started without `--agent` only observes and supplies position.

Start business traffic independently, including a parallel receiver:

```sh
sh deploy/mobile_node/agent.sh --edge-port 8780 --state .local/mid/E2-028/agent-A --dest 90:da:72:48:a4:e0 --interval-min 2 --interval-max 5 --min-bytes 0 --max-bytes 160 --seed 11
```

Windows equivalents are `deploy\mobile_node\node.cmd` and `agent.cmd`, with the same arguments. The underlying entry points are `python -m tools.mobile_node node` and `python -m tools.mobile_node agent`. Each has `--help`.

Only start one position-producing node for each edge service. A separate agent may run beside it. Repeat `--dest MAC` to supply candidate destinations; omit it to read the local board's observed neighbor IDs each round. Self is always excluded. Observed candidates may be unreachable; route selection and forwarding remain on the boards. A missing candidate or temporary route failure leaves the agent running. An unknown send outcome is recorded once, and the agent creates a new request for its next round.

## Random streams and providers

Every business round draws another interval, destination, English message and byte length. Intervals use seconds, and the inclusive payload range must fit 0–160 bytes. ASCII makes the character count equal to the byte count. Short messages can end partway through a word; zero bytes gives an empty message. Default intervals are 2–5 seconds and lengths are 32–120 bytes. The default seed is 1, salted with the local node MAC, so different cars use independent streams. Repeating a seed, node identity and candidate sequence reproduces the draws; timing also depends on API availability.

Fake GPS uses WGS84 coordinates around a fictional campus, default center 30.0/120.0 and size 600 by 400 metres. Each node has a MAC-salted independent start and heading. The trajectory moves continuously and reflects at the rectangle boundary. Configure `--center-lat`, `--center-lon`, `--width-m`, `--height-m`, `--speed-mps`, `--seed` and `--sample-s`. Default speed is 1.4 m/s and sampling is once per second. These coordinates are marked `simulated`; they generate no RF measurements.

For a local gpsd provider, use `--gps gpsd --gpsd-host 127.0.0.1 --gpsd-port 2947`. The adapter reads the [gpsd JSON WATCH/TPV protocol](https://gpsd.gitlab.io/gpsd/gpsd_json.html). A fix needs mode 2 or 3, coordinates and UTC sample time. No fix stays unknown. Stored sample time controls age even when gpsd stops updating. This reader has been exercised with a local protocol fixture; a physical receiver remains untested.

For an external function, use `--gps external --gps-function your_module:get_fix`. The callable takes no arguments and returns `None` or a dictionary with `lat`, `lon`, `sampled_at` (UTC Unix seconds), optional `accuracy_m`, and optional `valid`. External fixes are labelled `external` in reports. The E1 board wire uses `gnss` for this declared external provider; this declaration does not independently verify a GNSS device. Keep the function bounded so shutdown can complete. `--gps none` supplies unknown position. There is no automatic fallback to fake GPS.

`--max-age-s` defaults to 15. Stale fixes remain marked stale in observations; board injection clears validity. The E1 board also enforces its own 30-second expiry. `--no-position-injection` keeps GPS in reports when using old firmware. An explicit unsupported response disables injection for that process without stopping business traffic.

The Python continuous entry point is the same one used by the CLI:

```python
import threading
from tools.mobile_node.edge import MobileEdge
from tools.mobile_node.traffic import Journal, fake_agent_function, generate_payload

stop = threading.Event()  # another thread may call stop.set()
log = Journal('agent-example.jsonl')  # new file, never truncates an old log
try:
    fake_agent_function(MobileEdge(8780), log, stop=stop, seed=11,
                        interval_min=2, interval_max=5,
                        min_bytes=0, max_bytes=160,
                        dest=['90:da:72:48:a4:e0'])
finally:
    log.close()
```

This call runs until `stop.set()` or Ctrl+C, and joins its receiver before returning. `generate_payload(random.Random(seed), min_bytes, max_bytes)` only generates one payload. `fake_GPS_function(seed=11)` returns a callable position provider; calling it samples the current point on its trajectory. Provider functions are in `tools/mobile_node/providers.py`.

## Reports, local APIs and evidence

The node posts M-030 v1 reports to `/api/v1/reports`, normally every 10 seconds (`--report-s`). Received business events and neighbor changes can request an earlier report, limited to once per second. Position, event polling and gateway upload use separate workers. Stopping the observation gateway leaves local board traffic running.

The persistent `reports.sqlite3` queue holds at most 120 reports (`--queue-limit`). Overflow drops the oldest snapshot and increments `dropped_reports`. Events awaiting a snapshot are bounded to 512, with an explicit loss count; each report carries at most 128. Reconnection sends retained reports in order with their original session/sequence and current `report_age_ms`. Cached position/RSSI ages are not reset. Reusing a state directory reopens that queue and creates a new journal. Board reboot starts a new report session; business identity remains origin/boot/seq/destination.

The report's `boot_id` belongs to the observing board. A business event has flat `origin`, `boot`, `seq`, `dst`, plus `packet`, `observer_id`, `event_id`, its original serial `raw` event and stage. Source `tx_queued`, `tx_submit` and link callbacks stay destination-unconfirmed. Only local destination `rx_local` becomes `received`/`destination_received`; `rx_relay` is separate. Control events and board control/telemetry counters are kept separately. Logs preserve payload hex and original packet identity.

New local owner endpoints are `GET /api/edge/telemetry` and `POST /api/edge/position`. The latter accepts exactly E1-026 `position_set` fields: `position_boot`, `position_seq`, `source`, `fix`, `age_ms`, `lat`, `lon`, `accuracy_m`. It forwards one validated native command. Read queries do not start RF or configure routes. `MobileEdge.set_position()` assigns an independent provider epoch and increasing sequence. No location is saved in board NVS.

Neighbors combine native one-hop state with explicit `telemetry.rf_neighbors`. `bidirectional` maps to v1 `confirmed`. RSSI direction is physical peer to reporting receiver. Missing RF values stay null with source `unavailable`. Synthetic fixtures explicitly use `simulated`. Peer position announcements are passed through as `peer_positions`; they do not create confirmed radio edges.

Run the finite integration suite into a new output directory:

```sh
python -m tools.mobile_node.check_mobile --output simulation/outputs/E2-028/operator-check
```

On Linux with pyserial, add `--pty`. The suite uses synthetic boards, real loopback HTTP, the actual H gateway, CLI subprocesses, an outage/reconnection, a board restart, GPS fixtures, continuous API stop and seed checks. It does not open physical serial ports. Actual Windows and Ubuntu-container results, commands and manifests are under `simulation/outputs/E2-028/`; physical Pi/USB, real GNSS and RF acceptance remain with H/C/M.
