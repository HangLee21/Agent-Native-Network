# ANN ESP-NOW protocol prototype

E1-014, 2026-11-03. A portable C99 core, executable five-node host event harness, and ESP-IDF v5.5.1 adapter for the pending five ESP32-S3 boards. Host checks pass; ESP target compilation and all hardware/RF measurements remain unperformed. See [validation](VALIDATION.md) and [frozen interface](INTERFACE.md).

## Host reproduction

From repository root, with existing CMake/Ninja/GCC and Python (no package installation):

```powershell
.\.venv\Scripts\python.exe -X utf8 -B firmware/agent_native/run_host_checks.py --output simulation/outputs/E1-014/<new-empty-run-id>
```

The runner enforces new output paths, per-command120s/cumulative600s budgets, cumulative output100MiB, logs failed commands, and snapshots source plus the live task card. It never opens serial ports, downloads a model, runs ns-3, or installs anything. A protection timeout stops that run; do not restart automatically. The currently frozen executable is `simulation/outputs/E1-014/20261103-05-frozen/build/ann_host.exe`; all earlier runs remain evidence, including the first build failure.

Manual builds use `cmake -S firmware/agent_native -B <empty-build-dir> -G Ninja`, `cmake --build <build-dir>`, then `ann_host --scenario all`. Independent E2 tests may compile the same `src/ann.c`/`src/ann_console.c` and headers. The host harness uses declared chain adjacency and synthetic delivery/loss events; nodes only receive packets and local outcomes, never the graph. This checks executable protocol transitions, not RF behavior or network performance.

`ann_host --console` reads JSON lines and uses a **synthetic** clock advancing10ms per input line. It has no live serial/RF transport. It is for parser/idle/interlock testing, not a real-time bench replacement. `golden/serial-v1.jsonl` contains verbatim synthetic examples from the recorded harness; `golden/provenance.json` gives source line numbers and hashes. Never import these as hardware measurements.

## ESP-IDF project

Source is in `idf/`. The candidate SDK is **v5.5.1**. Official API references are [ESP-NOW](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/network/esp_now.html) and [tagged example](https://github.com/espressif/esp-idf/blob/v5.5.1/examples/wifi/espnow/main/espnow_example_main.c). The adapter uses this version's send callback `(const esp_now_send_info_t*, esp_now_send_status_t)` and receive callback `(const esp_now_recv_info_t*, const uint8_t*, int)`, queues callback data, and calls the core only from one owner task. Nothing was copied from another protocol implementation; this is a new prototype using those public APIs.

No idf.py/SDK was found in the execution environment; no SDK installation or target build was attempted. After a separately authorized toolchain preparation, the intended build-only command is `idf.py -C firmware/agent_native/idf -B <new-build-dir> build`. CMake fixes the target to esp32s3 and rejects another explicit target. This command is documented, **not reported as tested**. There is no flash/erase command here, nor automatic NVS erase in firmware. Build ID is derived at CMake configuration from core/header/adapter source hashes; board remains unverified.

UART0 console115200/8N1 is the candidate interface. USB-UART routing/native USB, board pinout, actual EoRa identity, channel/regulatory settings, flash layout, memory fit, and boot behavior need arrival validation by H under its own card; no LoRa pin/radio driver is assumed. Main task stack is explicitly12KiB for bounded JSON parsing and adapter buffers. Radio stays off until validated armed start/bench. Each board must be explicitly armed and started as a receiver/relay; a source-only bench cannot wake idle relays. H owns physical binding and armed run policy; core arm is an interlock, not authentication.

## Implemented and bounded

- One-hop HELLO discovery; flood RREQ with recorded path, bounded TTL, loop rejection and duplicate suppression; reverse RREP and source-route DATA/ACK/error.
- Finite source discovery and DATA retries; lost ACK causes same-identity DATA retry, receiver re-ACKs without redelivery within its window. Link callback success never confirms endpoint delivery.
- Per-origin/boot64-sequence receive window;100 consecutive transactions below pending capacity are tested. Ancient out-of-window sequences reject without ACK; live streams are not evicted. Boot changes isolate identities; retained state is RAM-only.
- Latest state per(origin,boot,key); older seq does not overwrite, local expiry removes the value. Best-effort cancellation of outstanding transactions and cancellation tombstones; no remote rollback or exactly-once guarantee across reboot/window expiration.
- Fixed-capacity queues/tables and explicit overflow counters/rejections; no fragmentation, dynamic source routing optimization, encryption/key provisioning, durable commits, measured RF retry counts or airtime estimator.

When an ESP send callback is missing or callbacks overflow, the adapter stops the local protocol. If stopped while a callback is unresolved, radio starts lock until reboot to avoid attributing a late callback to another transmission. No automatic recovery loop. Target behavior remains untested until compilation and hardware checks.
