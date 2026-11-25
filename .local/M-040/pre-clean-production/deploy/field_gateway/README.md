# PC wireless terminal

Run this program on the laptop that hosts the boards' 2.4 GHz Wi-Fi network. It uses UDP/IPv4 and the E1 `field.ip.v2` contract in `firmware/mid_baseline/field_agent/GATEWAY.md`. It opens no serial device. All boards run the same firmware and can become independent wireless entries. Normal operation needs no entry MAC or IP list.

The laptop's ordinary Wi-Fi/IP exchanges application messages with an entry board. ESP-NOW source routing remains on the boards. Wi-Fi and ESP-NOW must use the same channel; see the [Espressif coexistence requirement](https://docs.espressif.com/projects/esp-faq/en/latest/application-solution/esp-now.html). H owns the actual hotspot/channel, device configuration and RF validation. Hotspot credentials stay in local configuration and never belong in this program's logs or repository.

From the repository root, start a PC identity matching the boards' `pc_id`:

```powershell
python -X utf8 -m tools.field_gateway serve --state .local/mid/E2-029/pc-1 --pc-id 1 --http-port 8791 --udp-port 8793
```

Open [the PC field map](http://127.0.0.1:8791/). The HTTP service binds loopback. UDP binds `0.0.0.0:8793`; `--udp-host` can bind the actual hotspot-side address. Board UDP listeners default to 8792 and their configured PC address/port must point here. The board announces `register`; PC sends `lease`, then `hello`, and activates that entry only after reading the matching PC session and a positive remaining lease from the board. Each registration expires independently. Default PC lease is 10 seconds, with board renewals every 3 seconds. Status includes native IP availability, channel pinning and event overflow counters.

Use `deploy\field_gateway\START_PC.cmd` or `sh deploy/field_gateway/start_pc.sh` with the same arguments. The standard library is sufficient on Python 3.10+. Ctrl+C, SIGTERM, `--duration 120`, or creating the path passed to `--stop-file` stops the PC process. The state directory preserves the PC ID, transaction ledger and inbox. A new process uses a new `pc_session`; existing unknown sends are never automatically replayed. An identity mismatch rejects startup.

`--offline` opens the empty UI and local API without a UDP socket. No boards, routes or GPS are generated. `--entry IPv4:8792` and `--broadcast <hotspot-subnet-broadcast>` are optional discovery/debug aids; normal entry registration needs neither. A fixed entry list never replaces the dynamic selector. An unavailable port fails startup without replacing the service already there. Existing 8790/8780 services remain separate.

## Commands for H's finite switching run

Wait up to 30 seconds for at least two actual entries:

```powershell
python -X utf8 -m tools.field_gateway await-entries --count 2 --timeout 30
python -X utf8 -m tools.field_gateway status
```

In another terminal, capture 90 seconds of entry state, native events and actual PC inbox records. This command sends no business messages:

```powershell
python -X utf8 -m tools.field_gateway.capture --output simulation/outputs/E2-029/operator-capture-01 --duration 90
```

H should use a new directory in H's task scope for an actual hardware capture. `summary.json` lists simultaneous entries and their changes. `observations.jsonl` preserves each request/receipt event and PC destination record on the PC's clock. Physical power, disconnected USB cables, Wi-Fi reachability and the fault mechanism need H's separate evidence.

The following example addresses C's registered physical MAC; replace it with the actual remote destination under test. Send once and wait at most 10 seconds for the destination-board receipt:

```powershell
python -X utf8 -m tools.field_gateway send --dst 90:da:72:48:a4:e0 --text "PC to remote before entry loss" --request-id field-before-down-001 --wait 10
python -X utf8 -m tools.field_gateway recv --after 0 --wait 30
```

`recv` shows only bytes that actually arrived at the PC. The remote board's own agent must generate the reverse message. A PC downlink receipt never fills this inbox. Keep the returned inbox cursor and use it as `--after` when waiting for a new reverse packet.

Record the selected entry in the send record. H then removes that entry's PC connection while retaining its ESP-NOW function and the other entry's PC connection. Use a different request ID and new message for the next attempt:

```powershell
python -X utf8 -m tools.field_gateway send --dst 90:da:72:48:a4:e0 --text "PC to remote after entry loss" --request-id field-after-down-002 --wait 10
python -X utf8 -m tools.field_gateway recv --after 1 --wait 30
python -X utf8 -m tools.field_gateway watch --duration 30 --interval 0.5
```

`--after 1` is illustrative; use the actual last cursor. If the remote-to-PC direction used another entry, test that entry separately. Before claiming a radio multi-hop result, H must show that the remote board lacked a direct IP registration and record its actual ESP-NOW adjacency. `entry.transport` distinguishes `wifi_ip` from `wifi_ip_then_espnow`, and `entry.path` is board-supplied selection evidence, not proof of every actual hop. After all PC entries are removed, the independent board agents continue; this PC tool cannot prove their delivery while disconnected.

Finite waits exit 2 on timeout and print `observation_timeout:true`; they never cancel or resend the packet. HTTP errors print their JSON reason and exit 2. A delivery-unknown request ID is immutable. Repeating it returns its original record, even after reconnect or PC restart. Use new IDs for new measured messages. Startup status is not a hardware acceptance result.

## Selection and evidence

A destination with a current direct registration uses IP to that board. Otherwise PC queries the live entries with `op:route`. Each board computes its own path. The selector excludes expired proofs, then compares hop count, complete actual-MAC path bytes and entry MAC. It waits at most the configured route-query deadline, collecting up to 200 ms after a usable answer while preserving the proof's lifetime. The actual E1 adapter currently advertises 1000 ms route proofs. Before sending, PC rechecks the selected entry boot, lease and proof expiry. New messages can use another entry; unknown old messages are not blindly moved.

Cross-network application payloads are 0–128 original bytes, checked before submission. Normal board-to-board traffic remains 160 bytes. FG02 reserves its own header/receipt space. CLI `--text` uses UTF-8 byte length; `--payload-hex` preserves arbitrary bytes. No data is truncated. The stable PC logical ID is separate from entry MAC; the reserved PC service MAC is `02:ff:` followed by four big-endian ID bytes. The reserved address is a service identity, not a physical board.

The local API is documented in `tools/field_gateway/API.md`. It exposes entry admission, destination-board receipt and actual PC receipt separately. The durable inbox deduplicates logical source/boot/transaction across entries; raw radio identity and actual forwarding entry remain in the retained record. Request history is capped at 4096 and then refuses new IDs; inbox retention is 1024 with explicit eviction counts. Native entry events retain only 16 records, so `oldest_cursor`, `event_overflow`, gaps and cache limits remain visible. Polls replay IP records and never retransmit RF business.

The field map reuses D's current assets and H's State through the PC service. Incoming remote reports contain at most two rotating RF rows. Unknown transport age stays unknown; it cannot certify a fresh mutual link or an online remote board. Report age lower bounds and raw counters remain available. No default geographical position is assigned. The separate 8790 map service is not restarted or overwritten.

For the software contract check:

```powershell
python -X utf8 -m tools.field_gateway.check_field --output simulation/outputs/E2-029/operator-check-01
```

This opens real localhost UDP/HTTP sockets with explicitly synthetic entries. It tests leases, finite route selection, one-entry loss, two application directions, cross-entry deduplication, byte limits, durable unknown requests, CLI waits and partial telemetry. It does not test physical Wi-Fi, power banks, ESP-NOW service routing or zero USB. Actual E2 commands, frozen source and results are in the E2-029 output directories; H/C/M own physical acceptance.
