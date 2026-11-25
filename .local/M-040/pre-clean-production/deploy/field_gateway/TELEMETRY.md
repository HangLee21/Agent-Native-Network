# Read-only telemetry path for the live controller

The existing PC service on 8791 owns UDP8793. H's controller on 8794 should read that service; this adapter opens no second UDP owner or HTTP service. The separate 8790 observation gateway has its own State and is not automatically fed by 8791.

Read the current data once:

```powershell
python -X utf8 -m tools.field_gateway.read_observations --port 8791 --output simulation/outputs/E2-030/operator-read-01.json
```

Use a new output file. The command performs only HTTP GETs and reads retained records. It does not issue board maintenance, change H's control file, send business, start a host agent, configure RF or update either map. It works with the existing E2-029 PC process and needs no restart.

H can reuse the same reader in its controller:

```python
from tools.field_gateway.read_observations import ObservationReader

reader = ObservationReader(8791)
batch = reader.read()
```

Keep one reader to advance its event cursor. It clears its caches when the PC instance changes and rejects a snapshot that spans two PC instances. Its cache retains at most 256 native RAM records, 32 status samples and 32 report log entries. All underlying event history gaps remain explicit. This reader does not acquire new samples; H's existing maintenance path remains responsible for that.

## Existing fields available without a firmware change

| HTTP data | Meaning | Limit |
|---|---|---|
| `/api/pc/status` → `entries[]` | Actual entry MAC/boot, IP address and independent PC lease | An IP registration gives no ESP-NOW edge or RSSI |
| `/api/pc/events?after=...` → `kind=wireless_status`, then `item.raw.raw` | Original maintenance response | The two `raw` levels are part of the existing event envelope |
| Native `event=field_status` | `agent_running`, five source/relay/destination counters, record cursor and overwrite count | This firmware response has no neighbor table, last-hop RSSI or GPS |
| Native `event=record` | Observer `entry_id/entry_boot`, original `origin/origin_boot/seq/dst`, `kind`, `payload_hex`, `record_cursor`, `at_ms`, segment | Source identity is not the previous RF hop; RAM history can be overwritten |
| `/api/v1/state` on 8791 | State accepted from native `event=report` | Admission and PC inbox messages do not add map nodes |

The reader exports these as `entries`, `native_status`, `records`, `native_reports` and the untouched `map_state`. It never turns an entry registration or endpoint source/destination pair into a radio edge. `rf_rows_available:false` means the native status response lacks RF rows. Missing position remains null.

`records[].at_ms` is observer-board uptime within `observer_boot`. `observed_at` is the PC's readback reception time. Where the native response includes `entry_uptime_ms`, the reader derives an age lower bound from that same board boot, then adds elapsed PC time since readback. It does not subtract different machines' monotonic clocks. A newly read old RAM packet remains an old packet. FG02 bytes are labelled `payload_scope:FG02_envelope` rather than plain application text.

## Report and State boundary

On the standard observation gateway, `POST /api/v1/reports` accepts M-030 reports. On the PC terminal, the same POST is deliberately unsupported (404); `GET /api/v1/state` there reads the native-report State. These are separate services and State instances. Sending an inbox message or posting to another port cannot populate the PC's topology State.

Native reports pass through schema/entry verification, event deduplication, `normalize_report`, then `map.accept`. Valid native reports create nodes even with `position:null`. Partial RF rows retain `peer → observer` direction and their source. Unknown transport age leaves freshness unknown and cannot prove a live mutual edge.

E2-030 adds diagnostic fields for a future coordinated reload of the PC process:

| Field | Stage |
|---|---|
| `wireless.counters.received_datagrams` | UDP datagrams received by this process |
| `wireless.decoded_event_types.report` | Decoded report messages, including replays, before entry/session admission |
| `wireless.counters.reports_normalized` | Reports reaching successful normalization after duplicate filtering |
| `wireless.counters.report_normalization_rejected` | Native report normalization failure |
| `telemetry.map_outcomes` | Accepted, duplicate, out-of-order, retired-session or rejected State outcomes |
| `telemetry.recent_rejections` | Last 16 `map.accept` errors with stage and reason |
| `wireless.event_cursors` | Poll cursor and pending-gap count for each entry boot |

The already running process will not gain these fields from an on-disk edit. `batch.pc_diagnostics:null` means that instrumentation is not loaded. E2 did not restart it. H can continue using the existing event stream and the passive reader immediately.

The PC cursor fix lets a known duplicate advance the poll cursor after an explicitly reported retention gap. Its application callback still runs only once. It does not release the firmware's retained slots or repair a report that was never transmitted.

## Recorded live diagnosis

`simulation/outputs/E2-030/20261109-01-live-read/` captured one approximately 160 ms window. PC session 785675158 had five active entries and 2142 retained `pc_received` events. Its complete, untruncated event history contained no `wireless_report` and no rejected datagram event. Both 8790 and 8791 State responses had zero nodes and edges.

The formal package image SHA256 is `9ace23872877e579bc4b9484c388f784cacca40388040decf6f9f523c3c15580`. Its source files match the package manifest. In that source, a full 16-event ring causes a report to return before UDP transmission, and poll does not release slots. This explains how business can continue while fresh reports disappear. E2 did not trace the running board through that return branch. H's saved configuration and matching script show five successful 30-second report configurations; the current old `field_status` cannot read that configuration back.

`20261109-03-passive-read/observations.json` recovered five native status samples and 256 bounded RAM records from the existing PC API, with zero new report samples. Those status samples had no RF rows. They can support a board/agent list; they cannot supply measured RF edges. E1-028 owns the report producer fix and any candidate firmware. The new parser/cursor/HTTP tests are synthetic, and neither they nor this passive reader are an RF measurement.
