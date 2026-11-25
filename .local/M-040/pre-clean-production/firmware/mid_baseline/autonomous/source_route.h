#ifndef MID_SOURCE_ROUTE_H
#define MID_SOURCE_ROUTE_H
#include "mid.h"
#define SR_HEADER 60
#define SR_W 200u
#define SR_DEADLINE 1500u
#define SR_CACHE_MS 10000u
#define SR_QUEUE_MS 250u
#define SR_PEERS 8
#define SR_ROUTES 8
#define SR_PENDING 8
#define SR_ROUNDS 4
#define SR_CANDIDATES 16
#define SR_SEEN 32
#define SR_OUT 12
#define SR_EVENTS 32
enum {SR_RREQ=1,SR_RREP,SR_DATA,SR_ERROR};
enum {SR_ACCEPTED=1,SR_WAITING,SR_REQUEST,SR_CANDIDATE,SR_SELECTED,SR_DELIVERED,SR_NO_ROUTE,SR_INVALIDATED,SR_UNKNOWN,SR_DROPPED,SR_RELAY};
typedef struct {uint8_t type,n,index,ttl;uint32_t group,boot,seq,request;mid_id dst,path[5];uint16_t len;uint8_t payload[MID_PAYLOAD];} sr_packet;
typedef struct {uint8_t n;mid_id path[5];} sr_path;
typedef struct {int used,live;mid_id id;uint32_t boot;} sr_peer;
typedef struct {int used;mid_id dst;sr_path path;uint32_t request,first_boot;uint64_t until;} sr_route;
typedef struct {int used;mid_id dst;uint32_t seq;uint16_t len;uint8_t payload[160];} sr_pending;
typedef struct {int used;mid_id dst;uint32_t request;uint64_t deadline,close;unsigned count;sr_path candidates[SR_CANDIDATES];} sr_round;
typedef struct {int used;uint32_t boot,request;sr_path path;uint64_t until;} sr_seen;
typedef struct {sr_packet packet;mid_id next;uint64_t queued;uint32_t next_boot;} sr_out;
typedef struct {unsigned type,reason;uint32_t seq,request,boot;mid_id origin,dst;sr_path path;uint16_t len;uint8_t payload[160];} sr_event;
typedef struct {
 mid_id self;uint32_t boot,group,request_seq;uint64_t now;
 sr_peer peers[SR_PEERS];sr_route routes[SR_ROUTES];sr_pending pending[SR_PENDING];sr_round rounds[SR_ROUNDS];sr_seen seen[SR_SEEN];
 sr_out out[SR_OUT];unsigned head,count;sr_event events[SR_EVENTS];unsigned event_head,event_count;
 mid_seen delivered[64];unsigned delivered_cursor;
 uint32_t control_frames,control_bytes,data_frames,data_bytes,overflows,rejected,event_overflows;
 unsigned pending_high,out_high,candidate_high;
} sr_node;
int sr_encode(const sr_packet*,uint8_t*,size_t);
int sr_decode(sr_packet*,const uint8_t*,size_t);
void sr_init(sr_node*,mid_id,uint32_t,uint32_t);
void sr_neighbor(sr_node*,mid_id,uint32_t,int);
/* 0 accepted, -1 rejected; source seq must be unique/nonzero in this boot. */
int sr_submit(sr_node*,mid_id,uint32_t,const uint8_t*,size_t,uint64_t);
int sr_receive(sr_node*,mid_id,const uint8_t*,size_t,uint64_t);
void sr_tick(sr_node*,uint64_t);
void sr_stop(sr_node*);
int sr_next_tx(sr_node*,sr_out*,uint64_t);
/* Only a local link/API failure is reported here, never endpoint delivery. */
void sr_tx_result(sr_node*,const sr_out*,int,uint64_t);
int sr_next_event(sr_node*,sr_event*);
#endif
