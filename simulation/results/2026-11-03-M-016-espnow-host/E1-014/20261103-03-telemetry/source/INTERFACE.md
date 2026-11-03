# ANN v1 public interface checkpoint

2026-11-03; E1-014. Header/API checkpoint for H/E2 through M; implementation follows in the same directory. No board/target/RF validation yet. ESP-IDF candidate is exactly v5.5.1.

## Host CLI

Build: `cmake -S firmware/agent_native -B <new-build-dir> -G Ninja`, then `cmake --build <build-dir>`.
`ann_host --scenario <chain|ack_loss|state|expiry|cancel|error|reboot|bounds|wire|serial|all>` prints JSON test evidence and exits nonzero on assertion failure. This is synthetic event delivery, not RF or a performance simulation.
`ann_host --console` accepts newline-delimited commands below on stdin, emits replies/events on stdout, and runs no RF. EOF stops. External E2 tests may instead compile `src/ann.c` and `src/ann_console.c` against `include/ann.h` directly. All clocks are caller-supplied monotonic milliseconds; a reset requires a new boot ID and node initialization.

## Serial v1

115200, 8N1, UTF-8 JSON lines, request <=512 bytes excluding newline. Only flat JSON objects (strings, nonnegative integer values and booleans) are supported; nested objects/arrays, duplicate keys, invalid escapes, malformed/trailing JSON and unknown commands are errors. Nonce is required, 1..48 ASCII characters `[A-Za-z0-9_.:-]`; run_id uses the same alphabet. No shell execution. All replies carry `schema=ann.serial.v1`, `event`, `nonce`; errors carry `error` and `ok=false`.

`{"cmd":"info","nonce":"probe123"}` replies info with firmware=ann-espnow, protocol=1, node_id as lower-case 6-byte colon MAC, boot_id, build_id, chip, board=unverified, mode=idle/active. info/stats never start Wi-Fi or generate packets. Firmware boots idle. Host chip=host-synthetic, never esp32s3.

`{"cmd":"stats","nonce":"s"}` replies counters; RF retries, airtime and hardware measurements are null. `{"cmd":"stop","nonce":"s"}` stops bench/protocol, clears queued radio traffic and disarms. Source cancellations already in flight are best effort, not remotely atomic.

Explicit arming: `{"cmd":"arm","nonce":"a","node_id":"aa:bb:cc:dd:ee:ff","run_id":"r1","duration_ms":60000}` requires this exact node ID, duration 1..60000 ms. This is an operator interlock, not cryptographic authentication; the host must already have bound the physical board using H's configuration. Arming itself emits no radio traffic. `{"cmd":"start","nonce":"x","run_id":"r1"}` starts discovery only while armed for r1.

`{"cmd":"bench","nonce":"b","run_id":"r1","dst":"aa:bb:cc:dd:ee:01","count":10,"interval_ms":100,"frame_bytes":128,"echo":true}` requires armed matching run_id, count 1..1000, interval_ms>=1, span `(count-1)*interval_ms <=60000` and within remaining arm time, dst!=self. Frame bytes 112..250, or 120..250 for echo. `frame_bytes` is the **entire protocol datagram**, not payload or PHY frame; control/ACK frames may be smaller. Bench starts the protocol explicitly; after at most 60s it stops/disarms. No auto-run on boot. An error does not enable radio. No serial commands for flashing/erasing/installing.

Events generated/tx_submit/tx_result/rx/echo/stats use schema, run_id (null outside bench), node_id, boot_id, origin_id, seq, t_us, frame_bytes, payload_bytes; applicable status fields distinguish accepted-for-send, link callback, unique receive, duplicate, endpoint confirmation. tx_result success is **only a link callback**, never end-to-end PDR. All unobserved RF measurements stay null. Core event API also reports delivered/confirmed/expired/cancelled/rejected/duplicate; adapter maps them to JSON. UART/IDF startup logs may coexist; parse schema-marked JSON only. Events have nonce=null; command replies echo nonce.

## Wire v1 and core boundaries

All integers little endian, explicit serialization; never transmit C struct memory. Bytes 0..1 magic 0x41,0x4e; 2 version; 3 type; 4 flags; 5 TTL; 6 route length; 7 current route index; 8..15 origin; 16..23 final destination; 24..27 origin boot; 28..31 source seq; 32..35 remaining_ms; 36..39 state key; 40..41 payload length; 42 kind; 43 reserved=0; 44..107 eight uint64 route entries; 108..111 CRC32 (IEEE, CRC field zeroed); payload starts 112. Node IDs are lower 48 bits of MAC, 0 is broadcast sentinel only. Max path 8, frame 250, payload 138, tables 16, pending source transactions 8, outgoing/events 32. Live dedup entries are not silently evicted to admit more deliveries. Full tables/queues yield explicit rejection/counters, no unbounded allocation.

Types 1..7 HELLO/RREQ/RREP/DATA/ACK/ERROR/CANCEL; kinds transaction/state/echo. RREQ flood appends local ID, rejects loops and consumes TTL; RREP reverses the recorded path. DATA follows that path, endpoint ACK returns on its reverse. Each local pending transaction uses at most 3 discoveries and 3 DATA attempts, retry interval 500ms, source lifetime <=60000ms. Same origin+boot+seq is idempotent; duplicate DATA re-ACKs without redelivery. ERROR from failed DATA link invalidates source route and permits bounded rediscovery. No free global topology. No fragmentation, no encryption/key provisioning, no guaranteed order across independent random boot IDs; latest state ordering is scoped to (origin,boot,key), with seq monotonic within a boot. A reboot needs new boot identity, not seq reset under the same boot.

Expiry is a hard local source deadline; nodes subtract local queue residence from remaining_ms. Unmeasured on-air/clock uncertainty prevents a strict global deadline guarantee; TTL and local remaining budgets still bound forwarding. No exactly-once claim across receiver reboot or dedup expiration. CANCEL is best effort for outstanding transactions, carries a destination tombstone; it does not retract already delivered effects, nor promise remote deletion during a partition. Core delivery marks protocol reception, not application side-effect commit. State values expire locally and older seq for the same boot/key does not overwrite newer state. Hardware absence never substitutes synthetic outcomes for measured PDR/range/RTT.
