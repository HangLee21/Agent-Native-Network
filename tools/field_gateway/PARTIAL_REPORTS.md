# Partial RF reports and packet evidence

## Opt-in live neighbor evidence

The wire contract is `firmware/mid_baseline/field_agent/NEIGHBORS.md`: `op=neighbors`, monotonic per-entry `query_id`, `event=neighbors`, `encoding=nd.rf.v1` and a complete compact ND table. Enable the PC service with `--neighbor-snapshots` after H installs matching firmware. Only current leased entries advertising `neighbors_api=1` are queried, once every two seconds. No new RF business or serial telemetry is generated. Old firmware keeps the ordinary partial-report path.

`direct.py` saves the monotonic send time, entry boot/address and query ID before sending. Only the first matching current-PC-session response within one second is accepted. Each board age plus the entire rounded-up host RTT is an age upper bound; cache time is added using the host monotonic clock. UTC corrections cannot extend it. The board already includes its millisecond quantization margin. Board ages clamped to 12000/9000 are only lower bounds: their upper fields remain null and they cannot certify freshness.

Each edge's `direct_evidence` retains `query_id`, PC session, both actual ND boots, board snapshot time, host receipt time, RTT, independent seen/confirmation age bounds, ND capacity counter and source. `direct_freshness` refers to ND seen age below 12000 ms; `direct_confirmed` additionally requires confirmed state and ACK age below 9000 ms. Both directions must independently pass these checks and agree with the currently observed board boots for `mutual_confirmed`. `mutual_valid_for_ms` is the minimum remaining lifetime of both directions' seen and ACK evidence. A browser must subtract time since GET and revoke confirmation when it reaches zero. A complete table omitting a formerly queried peer revokes that query's validity without inventing loss. A lost row revokes only that direction's confirmation.

RSSI has its own RF frame age. For a live queried row, `sample_kind=rf_frame`, `sample_age_ms=null`, and `sample_age_upper_bound_ms` / `rssi_sample_age_upper_bound_ms` describe that RF frame; clamped ages use the lower-bound fields. `sample_freshness` / `rssi_sample_freshness` refer to that RF frame, not ACK freshness. Missing RSSI remains null. `previous_rf_observation` retains the previous partial-report sample separately. ND boot evidence in `direct_evidence` is not a fabricated boot for the RF frame (`peer_boot` remains null). Nodes without direct IP access retain partial-report age semantics. The API shape and existing 8794 upstream GET remain usable.

The seven finite checks in E2-031/20261110-01-final-neighbors cover wire decoding, replay/session/address rejection, monotonic expiry, clamped-age bounds, restart/complete-table omission, packet identity and ephemeral HTTP. These are synthetic contract checks; actual firmware loading and current RF confirmation require H's live evidence.

`State` merges neighbor rows only when `neighbors_partial:true`, or when the older `report_scope:partial_rotating_rows` marker is present without an explicit partial flag. A complete report (`neighbors_partial:false`) still removes directions omitted from its complete list. Nodes without neighbors and reports without GPS remain valid.

Each cached direction has its own observer boot, source sample or age anchor, report sequence and state sequence. A later partial report that lists other peers does not delete or refresh it. A repeated sample timestamp or an older exact-age anchor cannot renew RSSI. When timestamps and complete ages are absent, identical measurement values are conservatively retained as the already selected observation. New report arrival alone is not a new RF sample. Cache capacity is 64 directions per observer, with explicit eviction counters.

The GET State response adds `neighbor_merge_policy:per_observer_peer_v1`. H can use this to verify that the intended State code is loaded. Existing running Python processes need H's coordinated reload; saving this file does not change their imports.

## Edge fields for H and D

| Field | Meaning |
|---|---|
| `from`, `to` | Physical peer → reporting receiver; never original business source → destination |
| `observer_boot` | Boot of the reporting receiver that owns this sample |
| `peer_boot` | Peer boot supplied by the original observation, or null |
| `peer_current_boot` | Gateway's currently known peer identity; not a fabricated sample boot |
| `sample_age_ms` | Complete age including cache time, only when known |
| `sample_age_lower_bound_ms` | Age lower bound plus elapsed gateway time for this selected sample |
| `sample_received_ms` | Gateway receipt anchor for this selected observation |
| `sample_report_seq` | Report that supplied this selected RF observation |
| `state_report_seq` | Latest accepted report that supplied this direction's state |
| `sample_identity_basis` | Explicit observer stamp, exact age anchor, or conservative measurement-value retention |
| `sample_freshness` | `fresh`, `stale` or `unknown`; prefer this over the legacy boolean |
| `sample_stale` | Compatibility flag: true whenever the sample is not certified fresh |
| `invalidated_reason` | Peer boot mismatch or unverified sample epoch after peer restart, otherwise null |
| `mutual_confirmed` | Both current observer epochs report confirmed directions with complete fresh sample ages and valid epoch checks |

The RF source and measured RSSI remain unchanged. A missing RSSI stays null. A direction can be displayed as a real observed direction even when its age is unknown; that does not certify a currently effective bidirectional link. Lost cancels mutual confirmation immediately. Stale/lost rows remain available as history, so callers can render them faded rather than silently replacing them with a live edge.

An observer boot change clears its outgoing cache and cached directions pointing to that peer. Retired boots cannot reappear under a new report session. A later untagged observation with a sample predating the peer-restart observation, or with unknown sample time after that restart, cannot certify a fresh current-epoch edge. Explicit peer-boot evidence can resolve the ambiguity. Ordinary process-session changes on the same board boot do not independently renew the sample.

The current FG02 format emits at most two rows per report. It gives sample ages as lower bounds, with `transport_age_ms:null`; these rows remain unknown until their growing lower bound proves them stale. Repeated lower-bound-only values do not get fresh timestamps. Native ND confirmation/loss limits are 9/12 seconds, while report cadence is at least 30 seconds. Partial merging repairs omission; it cannot create continuously fresh radio evidence across that sampling gap or turn a lower bound into an upper bound.

For known transport ages, normalization leaves the source sample age in the row and report transport age in `report_age_ms`, so State adds transport delay once. Row `age_is_lower_bound:true` keeps complete age unknown even when report transport age is known.

## Packet identity and confirmation

`packet_evidence.summarize_packets(events, history_gap=...)` is a pure reference projection for H/D. It accepts canonical events or 8794 timeline rows. It keys each packet by `origin`, `origin_boot`, `seq`, `dst`; observer identity stays separate. Route-request sequence numbers, explicit control kinds and FG02 envelope rows are excluded from ordinary board-business aggregation.

States are `queued_only`, `submitted_pending`, `relayed_pending`, `destination_received`, `explicit_no_route`, `explicit_rejection`, `cancelled_before_submission`, `delivery_unknown`, `observed_only`, or `evidence_conflict`. Destination receipt requires `rx_local` at the actual destination and retained payload bytes. `bytes_match_source:true` additionally requires the same original bytes at the source. Missing source bytes leave that comparison null. Later sender/link errors do not erase an already byte-matched destination receipt. A sender's stop cancellation is separate from no-route evidence.

The five native RAM record classes provide positive admission/submission/relay/receive evidence. They do not provide per-packet failure records. Polling or RAM coverage gaps can explain a missing destination observation; they do not establish packet loss. A local transmit failure is evidence about that local attempt, not proof that the entire logical message was permanently lost. The reference helper never invents an observation timeout or infers a full hop path from source and destination.

The saved actual 8794 timeline in E2-031/02 yielded 1999 destination observations, including 1790 packets with matching source and destination bytes. Another 520 had only queue/submission evidence. These are counts in the retained observation window, not delivery ratio or a new RF experiment. Concrete identities and original bytes are in E2-031/04-real-replay/examples.json. Two saved PC snapshots each had ten rows; the new offline merge retained eighteen actual directions, ten unknown and eight stale, with zero fresh mutual claims.
