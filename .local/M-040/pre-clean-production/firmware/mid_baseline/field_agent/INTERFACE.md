# SR01 bounded source routing v1

All integers little endian. Fixed header60, total<=220, application payload<=160 (no truncation).

| Offset | Bytes | Meaning |
|---|---|---|
|0|4|ASCII SR01|
|4|4|nonzero group|
|8|1|type: RREQ1, RREP2, DATA3, ERROR4|
|9|1|path node count1..5|
|10|1|index: RREQ sender index; others intended receiving index|
|11|1|remaining hops, validated exactly against index/path length|
|12|4|original source boot|
|16|4|DATA/ERROR original business seq; RREQ/RREP request seq|
|20|4|nonzero request round seq; direct DATA uses its business seq|
|24|6|final destination MAC|
|30|30|five MAC slots; unused bytes zero|
|60|0..160|DATA application bytes; ERROR exactly1 byte failed edge index; others empty|

Source identity=path[0], boot, business seq. RREQ round=path[0],boot,request. Paths have no duplicate MAC; RREQ partial path excludes receiver, last path node must equal physical sender; RREP/ERROR reverse sender must be path[index+1], DATA sender path[index-1], receiver exactly path[index]. All physical peers must currently be confirmed. RREQ appends receiver; destinations reply along each qualifying different path, intermediates forward distinct full-prefix copies (32 seen slots retained5s, no first-arrival-only pruning). Full paths selected at source, not by a host. RREQ TTL=5-n, n<5 on wire; DATA TTL=n-index, reverse TTL=index+1. RREQ/RREP seq=request. ERROR failed edge must lie downstream of its receiver; at source it is honored only against exact cached path/round/current source boot. No arbitrary remote cache flush.

Constants/API are in source_route.h: W200ms, absolute1500ms, cache10s, outbound residence250ms. sr_receive/sr_next_tx call sr_tick first: arrival exactly at close/deadline is late. First reply fixes close=min(first+W,deadline). Up to16 unique candidates per round; shortest node count then raw full-path MAC bytes. Not a global optimum and not an assurance of identical over-air candidate sets. At most4 rounds and8 pending business packets, same destination coalesces. Queue/table overflow rejects or emits route_drop, never overwrites live state; expired cache reusable, but no automatic LRU eviction. 32 seen full-prefix entries may limit concurrent floods; no unbounded retry queue. Frame budget per5-node simple round is finite, but loss/order/limits can reduce the candidate set.

Each queued frame pins next-hop boot. Confirmed-neighbor loss/reboot invalidates cached first-hop routes; intermediate DATA forwarding failure emits matching ERROR toward source. Link failure/queue timeout yields delivery_unknown; the original business packet is not automatically resent or rewritten. Later new business starts another round after invalidation, or cache expiry bounds silent remote-error loss to10s. No route atdeadline clears pending with no_route. Destination dedup is64 volatile source-MAC/boot/seq entries; this is not durable exactly-once across reboot/eviction. No endpoint ACK; local send acceptance/link success are not destination receipt.

Control/data core counters count frames removed by sr_next_tx for adapter submission, not actual RF success. ESP adapter separately records submissions/callback outcomes. Core has no heap. Host sizeof(sr_node)=17696; board sizeof/heap/high water/processing time will be separately reported, no RF or RT guarantees inferred from host tests. Events: accepted1, waiting2, request3, candidate4, selected5, delivered6, no_route7, invalidated8, delivery_unknown9, drop10, relay11; event ring overflow increments counter. Delivered/relay include original bytes; source events for request/path do not fabricate endpoint evidence.

Mode commands: route_config(group/channel/autostart), route_start, route_clear, routes. Autonomous mode requires no static/deployment or legacy discovery profile; switching is explicit stop/clear. The board alone receives final dst and payload, does not accept routes in these commands. ND01 neighbor HELLO/confirmation stays M027-compatible. NVS namespaces are separate. Optional local link_filter(allow[], or clear:true) affects physical ingress/egress including HELLO and SR01, not route calculation; runtime only, lost on reset. It is a controlled logical link experiment, not natural RF isolation or a routing oracle.
