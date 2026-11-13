# MID candidate v1 interface (E1-016, checkpoint 1)

Status: candidate-source ESP-NOW adaptation; not a TRO experiment-version claim. D-015 source audit and H-005 display freeze consumed for target integration. This interface is separate from ann.serial.v1. No existing ANN files or H OLED sources are replaced.

## Wire format

All integers little endian, no C struct serialization. Max frame 250 bytes; reject oversize, no fragmentation. Header 24 bytes: magic `MID1` [0..3], kind [4] (1 config, 2 data), remaining TTL [5] (1..8), body length u16 [6..7], original source MAC [8..13], original boot u32 [14..17], original sequence u32 [18..21], reserved zero [22..23]. Original identity survives forwarding. TTL is an IP-like loop bound, not a forced-hop experiment.

Config body: node_count u8, flow_count u8, node MACs (6*N), flow pairs (src_index,dst_index; 2*K), weights u16 (K*N*N, flow/executor/gateway order). N=2..5, K=1..2; maximum whole frame160 bytes. Reject duplicate MACs/flows, nonunicast MACs, self edges, destination outgoing rows, invalid indices, nonzero rows not summing to65535. Zero row means no route. Whole table replaces current table, keyed by (source,destination,executor). Maximum two concurrent flows is a documented bounded adaptation; additional flows rejected explicitly.

Controls accepted only for the configured publisher MAC + boot. Sequence must increase (no wrap); restart/rebind requires explicit stop/start. Each accepted update is rebroadcast once while TTL>1, including by the serial entry node, preserving original identity. No ACK, transactional commit, dual-version tables, reliable retransmission or ANN route discovery. A repeated Planner publication uses a new seq, same table. Sequence exhaustion requires a new run. Startup does not enable radio automatically.

Every 500ms each executor draws one gateway per flow proportional to the current positive weights. Hold that choice for the period, all packets in that period use it. No per-packet split. Zero row disables forwarding. Routing is not recomputed by the board. Data body: destination MAC6, arbitrary payload0..160 bytes. Source is header origin. Endpoints match full source/destination; intermediate nodes use that flow's selected gateway. Local destination emits rx_local once per (origin,boot,seq) within bounded64-entry cache; the cache is not unlimited historical uniqueness. Data forwarding decrements TTL, no retransmission/ACK. Repeated/reordered control frames do not roll back table.

## Serial adapter contract

JSON lines, output schema `mid.serial.v1`, UART115200/8N1. Input is an object with cmd and nonce (1..64 printable ASCII); maximum1024 bytes excluding newline, CRLF accepted. Duplicate keys, bad/trailing JSON, missing nonce and oversize lines rejected; unknown extra fields ignored. Input schema field optional (not used to dispatch). Each command produces command_result with nonce/ok/error/mode/radio/stopping/locked_until_reset. Boot emits node_id/boot_id/build_id; info repeats these identity fields.

| Command | Extra input | Actual effect |
|---|---|---|
| info | none | firmware mid-espnow, chip/board, label A/B/? and identity, no radio start |
| stats | none | local display/event counters, config seq, queue depth, display_hw; never remote delivery/PDR |
| start | publisher MAC string, publisher_boot nonzero uint32 | bind one publisher run, start ESP-NOW channel6; reject busy/stopping/locked |
| stop | none | stop accepting data/control, cancel queued TX, drain in-flight callback then deinit; no reset/erase |
| config | frame_hex (complete encoded control) | active entry only; origin must equal this board's actual MAC and boot its info boot_id; validate/install, enqueue one rebroadcast |
| send | dst MAC string, payload_hex (0..160 bytes) | active with table/selected route; next sequence generated locally, enqueue source packet, no remote ACK |

For entry A first read info to obtain current A boot. Start A and B with publisher=A MAC and publisher_boot=A boot; B's own boot remains its own identity. Use that A boot in bridge-generated config. Stop/start retains local source seq and boot; any reboot requires fresh info and explicit rebinding all nodes. No implicit RF activity on startup. No arm/start ANN contract, no bench traffic generator.

The main task owns state and H display model. UART reader and Wi-Fi callbacks copy into input queue16; main TX ring16, exactly one in-flight ESP-NOW send, callback matched to its actual next MAC. A queued packet retains the actual next hop selected at queue admission, even if a later500ms period changes the flow choice. Queue expiry1000ms is a local send failure. Missing callback1000ms or input overflow fails closed and locks radio until physical reset, preventing stale callbacks being matched to another send. Stop drains pending callback while rejecting restart; no reliable wireless retry. No automatic NVS erase. Peers only from configured routes or broadcast; all five nodes can originate/forward/receive. H's six-page renderer and page-only PRG are linked unchanged. Labels A/B map verified MACs; C–E unknown.

Events carry node_id, boot_id, build_id, monotonic_ms. command_result means local command accepted. config_rx means decoded control observed (before policy/table validation); config_rejected means rejection; config_stale means valid duplicate/old seq; config_applied only after actual periodic executor adopted it. route_selected includes flow/src/dst/next_hop (null if no route), once per500ms period. tx_queued is local admission, tx_submit is API accepted, tx_link_ok/tx_link_fail are callback only; tx_api_failed/tx_queue_full/queue_timeout/callback_timeout/tx_cancelled are local failures, rx_relay is legitimate forwarding reception, rx_local is unique local destination receipt, rx_duplicate is duplicate destination receipt, data_drop is invalid/TTL/no-route. Control TX produces the same serial submission/result events but does not increment data OLED TX counters. Data records include original MAC/boot/seq, final dst, known flow and actual next_hop. Source display remains 'destination unconfirmed'; link success never becomes end-to-end delivery. No confirmed event exists. H snapshot event mapping and cumulative counters use actual main-task transitions, not Planner intent; helper command names match compiled CLI.

Samples and source hashes: FREEZE.json; earlier checkpoint1 evidence is retained under01/02, final target package is separately identified by its sealed manifest. Neither target compilation nor offline image validation constitutes physical OLED/PRG or RF validation.
