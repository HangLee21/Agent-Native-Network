#ifndef MANET_AODV_H
#define MANET_AODV_H
#include <stdint.h>
#include <stddef.h>
/* Portable bounded AODV adaptation. No heap allocation inside protocol core. */
#define MA_NODES 40
#define MA_MTU 250
#define MA_HEADER 32
#define MA_PENDING 16
#define MA_TXQ 32
#define MA_EVENTS 64
#define MA_SEEN 128
#define MA_BROADCAST 255
#define MA_RREQ 1
#define MA_RREP 2
#define MA_DATA 3
#define MA_RERR 4
#define MA_MAGIC 0xa7
#define MA_VERSION 2

typedef struct {uint8_t valid,known,next,hops;uint32_t seq;uint64_t expires;} ma_route;
typedef struct {uint8_t used,dst,len;uint32_t seq;uint64_t until;uint8_t data[160];} ma_pending;
typedef struct {uint8_t used,origin;uint32_t boot,id;uint64_t until;} ma_seen;
typedef struct {uint8_t data[MA_MTU],len,next,type;} ma_tx;
typedef struct {uint32_t v[8];uint8_t payload[160];} ma_event;
typedef struct {uint8_t active,ttl,attempts,deferred;uint64_t deadline;} ma_discovery;
typedef struct {uint8_t id,policy,ring_cap,data_ttl;uint32_t pending_ms;uint32_t boot,own_seq,rreq_id;uint64_t rreq_window,rerr_window,forward_window;uint8_t rreq_count,rerr_count,forward_count;uint32_t forward_suppressed;ma_route route[MA_NODES];ma_pending pending[MA_PENDING];ma_seen seen[MA_SEEN];ma_discovery find[MA_NODES];ma_tx tx[MA_TXQ],inflight;ma_event events[MA_EVENTS];uint8_t qh,qn,eh,en,has_inflight;uint32_t overflow,event_overflow,rejected,denied,tx_overflow,seen_overflow,rreq_rx,rreq_duplicates,rreq_forward,rrep_dest,rrep_intermediate,rerr_issued;uint8_t pending_high,tx_high;uint8_t peer_used[20],peer_id[20];uint64_t peer_time[20];} ma_node;
void ma_init(ma_node*,unsigned,unsigned);
int ma_limits(ma_node*,unsigned,unsigned,unsigned);
int ma_submit(ma_node*,unsigned,uint32_t,const uint8_t*,unsigned,uint64_t);
int ma_receive(ma_node*,unsigned,const uint8_t*,unsigned,uint64_t);
void ma_tick(ma_node*,uint64_t);
int ma_next(ma_node*,uint8_t*,int*,int*);
void ma_result(ma_node*,int,uint64_t);
int ma_event_next(ma_node*,uint32_t*,uint8_t*);
int ma_peer(ma_node*,int,uint64_t);
#endif
