#ifndef MID_SOURCE_ROUTE_H
#define MID_SOURCE_ROUTE_H
#include "mid.h"
#ifndef MID_ROUTE_FEEDBACK
#define MID_ROUTE_FEEDBACK 0
#endif
#define SR_HEADER 60
#define SR_W 200u
#define SR_DEADLINE 1500u
#define SR_CACHE_MS 10000u
#define SR_QUEUE_MS 250u
#define SR_PEERS 32
#define SR_ROUTES 32
#define SR_PENDING 16
#define SR_ROUNDS 4
#define SR_CANDIDATES 16
#define SR_SEEN 128
#define SR_OUT 12
#define SR_EVENTS 32
#define SR_PROOFS 16
#define SR_SUSPECT_WINDOW_MS 5000u
#define SR_FEEDBACK_COOLDOWN_MS 3000u
/* Per-node route-discovery token bucket. Limits the RATE of floods without
 * truncating a single flood's coverage (a fixed forward budget was measured to
 * destroy reachability at 30 nodes). Burst 4, refill one token per 250 ms. */
#define SR_RREQ_BURST 4u
#define SR_RREQ_REFILL_MS 250u
#define SR_FAILED_HOP_HOLDOFF_MS 500u
/* Per source boot/request, bound distinct forwarded path variants per node. */
#define SR_RREQ_PATH_LIMIT 2u
enum {SR_RREQ=1,SR_RREP,SR_DATA,SR_ERROR,SR_SREQ,SR_SREP,SR_SDATA,SR_SERR};
static inline unsigned sr_base_type(unsigned type){return type>4?type-4:type;}
static inline int sr_service_id(mid_id id){return id.mac[0]==2&&id.mac[1]==255;}
enum {SR_ACCEPTED=1,SR_WAITING,SR_REQUEST,SR_CANDIDATE,SR_SELECTED,SR_DELIVERED,SR_NO_ROUTE,SR_INVALIDATED,SR_UNKNOWN,SR_DROPPED,SR_RELAY};
typedef struct {uint8_t type,n,index,ttl;uint32_t group,boot,seq,request;mid_id dst,path[5];uint16_t len;uint8_t payload[MID_PAYLOAD];} sr_packet;
typedef struct {uint8_t n;mid_id path[5];} sr_path;
typedef struct {int used,live;mid_id id;uint32_t boot;uint64_t avoid_until;} sr_peer;
typedef struct {int used;mid_id dst;sr_path path;uint32_t request,first_boot;uint64_t until;
#if MID_ROUTE_FEEDBACK
 uint32_t suspect_seq;uint64_t suspect_at;
#endif
} sr_route;
typedef struct {int used;mid_id dst;uint32_t seq;uint16_t len;uint8_t payload[160];} sr_pending;
typedef struct {int used;mid_id dst;uint32_t request;uint64_t deadline,close;unsigned count;sr_path candidates[SR_CANDIDATES];uint64_t proof_until[SR_CANDIDATES];
#if MID_ROUTE_FEEDBACK
 int probe;uint32_t prior_request;
#endif
} sr_round;
typedef struct {int used;uint32_t boot,request;sr_path path;uint64_t until;} sr_seen;
typedef struct {int used;uint32_t seq,request;mid_id dst;sr_path path;} sr_tx_proof;
typedef struct {sr_packet packet;mid_id next;uint64_t queued;uint32_t next_boot;} sr_out;
typedef struct {unsigned type,reason;uint32_t seq,request,boot;mid_id origin,dst;sr_path path;uint16_t len;uint8_t payload[160];} sr_event;
typedef struct {
 mid_id self,service_id;uint32_t boot,group,request_seq,pc_session;uint64_t now,service_until;
 sr_peer peers[SR_PEERS];sr_route routes[SR_ROUTES];sr_pending pending[SR_PENDING];sr_round rounds[SR_ROUNDS];sr_seen seen[SR_SEEN];
 sr_out out[SR_OUT];unsigned head,count;sr_event events[SR_EVENTS];unsigned event_head,event_count;
 mid_seen delivered[64];unsigned delivered_cursor;
 uint32_t control_frames,control_bytes,data_frames,data_bytes,overflows,rejected,event_overflows;
 unsigned pending_high,out_high,candidate_high;
 /* One bounded local re-discovery per locally originated data identity, so a
  * next hop that moved away does not silently eat the packet. Ring of the last
  * SR_PENDING retried seqs; every data seq is nonzero by construction. */
 uint32_t retried[SR_PENDING];unsigned retried_cursor;unsigned retries;
#if MID_ROUTE_FEEDBACK
 sr_tx_proof proofs[SR_PROOFS];unsigned proof_cursor,unconfirmed_probes;uint64_t feedback_next;
#endif
 /* Route-discovery token bucket: refilled by sr_tick, consumed by sr_query and by
  * the round-start path of sr_submit. Denied requests are counted, never queued. */
 uint8_t rreq_tokens;uint64_t rreq_refilled;uint32_t rreq_denied;
} sr_node;
int sr_encode(const sr_packet*,uint8_t*,size_t);
int sr_decode(sr_packet*,const uint8_t*,size_t);
void sr_init(sr_node*,mid_id,uint32_t,uint32_t);
void sr_neighbor(sr_node*,mid_id,uint32_t,int);
void sr_service(sr_node*,mid_id,uint32_t,uint64_t);
int sr_query(sr_node*,mid_id,uint64_t);
/* 0 accepted, -1 rejected; source seq must be unique/nonzero in this boot. */
int sr_submit(sr_node*,mid_id,uint32_t,const uint8_t*,size_t,uint64_t);
int sr_receive(sr_node*,mid_id,const uint8_t*,size_t,uint64_t);
void sr_tick(sr_node*,uint64_t);
void sr_stop(sr_node*);
int sr_next_tx(sr_node*,sr_out*,uint64_t);
/* Only a local link/API failure is reported here, never endpoint delivery. */
void sr_tx_result(sr_node*,const sr_out*,int,uint64_t);
/* Immediate local API rejection is not evidence that the radio link failed. */
void sr_tx_abort(sr_node*,const sr_out*,uint64_t);
/* Unknown callback outcome: do not replay the same outer packet. */
void sr_tx_unknown(sr_node*,const sr_out*,uint64_t);
/* Experimental: after independent misses, start a bounded alternative-route
 * probe without first invalidating the still-identical cached route. */
int sr_unconfirmed(sr_node*,uint32_t,uint64_t);
void sr_confirmed(sr_node*,uint32_t,uint64_t);
int sr_next_event(sr_node*,sr_event*);
#endif
