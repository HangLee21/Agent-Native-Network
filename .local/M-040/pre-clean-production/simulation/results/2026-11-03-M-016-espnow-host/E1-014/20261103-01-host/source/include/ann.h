#ifndef ANN_H
#define ANN_H
#include <stdint.h>
#include <stddef.h>
#define ANN_VERSION 1
#define ANN_FRAME_MAX 250
#define ANN_HEADER 112
#define ANN_PAYLOAD_MAX (ANN_FRAME_MAX-ANN_HEADER)
#define ANN_PATH_MAX 8
#define ANN_TABLE 16
#define ANN_QUEUE 32
#define ANN_PENDING 8
#define ANN_LIFETIME_MAX 60000u
#define ANN_RETRY_MS 500u
#define ANN_ATTEMPTS 3
typedef uint64_t ann_id;
enum ann_type { ANN_HELLO=1, ANN_RREQ, ANN_RREP, ANN_DATA, ANN_ACK, ANN_ERROR, ANN_CANCEL };
enum ann_kind { ANN_TRANSACTION=1, ANN_STATE, ANN_ECHO };
enum ann_event_type { ANN_GENERATED=1, ANN_RX, ANN_DELIVERED, ANN_CONFIRMED, ANN_EXPIRED,
                      ANN_CANCELLED, ANN_REJECTED, ANN_DUPLICATE, ANN_ECHOED };
typedef struct { uint8_t type,flags,ttl,path_len,index,kind; ann_id origin,dst,path[ANN_PATH_MAX];
                 uint32_t boot,seq,remaining_ms,key; uint16_t payload_len; uint8_t payload[ANN_PAYLOAD_MAX]; } ann_packet;
typedef struct { ann_id next; ann_packet packet; uint64_t queued_ms; } ann_out;
typedef struct { uint8_t type; ann_id origin; uint32_t boot,seq; uint64_t t_ms; int status;
                 uint16_t frame_bytes,payload_bytes; } ann_event;
typedef struct { int used; ann_id id; uint32_t boot; uint64_t until; } ann_peer;
typedef struct { int used; ann_id dst,path[ANN_PATH_MAX]; uint8_t len; uint64_t until; } ann_route;
typedef struct { int used,cancelled; ann_id origin; uint32_t boot,seq; uint8_t type; uint64_t until; } ann_seen;
typedef struct { int used; ann_packet packet; uint64_t deadline,due; unsigned discoveries,attempts; } ann_pending;
typedef struct { int used; ann_id origin; uint32_t boot,key,seq; uint16_t len; uint8_t data[ANN_PAYLOAD_MAX]; uint64_t until; } ann_state;
typedef struct { ann_id id; uint32_t boot,seq; int active; uint64_t now;
 ann_peer peers[ANN_TABLE]; ann_route routes[ANN_TABLE]; ann_seen seen[ANN_TABLE];
 ann_pending pending[ANN_PENDING]; ann_state states[ANN_TABLE];
 ann_out out[ANN_QUEUE]; unsigned out_head,out_count;
 ann_event events[ANN_QUEUE]; unsigned event_head,event_count;
 uint32_t delivered,confirmed,rejected,duplicates,event_overflow,queue_overflow;
} ann_node;
void ann_init(ann_node*,ann_id,uint32_t);
void ann_start(ann_node*,uint64_t);
void ann_stop(ann_node*,uint64_t);
int ann_submit(ann_node*,ann_id,uint8_t,uint32_t,const void*,size_t,uint32_t,uint8_t,uint64_t,uint32_t*);
int ann_cancel(ann_node*,uint32_t,uint64_t);
void ann_tick(ann_node*,uint64_t);
int ann_encode(const ann_packet*,uint8_t*,size_t);
int ann_decode(ann_packet*,const uint8_t*,size_t);
int ann_receive(ann_node*,ann_id,const uint8_t*,size_t,uint64_t);
int ann_next_tx(ann_node*,ann_out*,uint64_t);
void ann_tx_result(ann_node*,const ann_out*,int,uint64_t);
int ann_next_event(ann_node*,ann_event*);
#endif
