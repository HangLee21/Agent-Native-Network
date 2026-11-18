#ifndef MID_NEIGHBORS_H
#define MID_NEIGHBORS_H
#include "mid.h"
/* 30-node target: mean degree ~14, worst case 29 in range. */
#define ND_PEERS 32
#define ND_CONFIRM_MS 9000u
#define ND_LOST_MS 12000u
/* A neighbour silent this long is dropped from the table. Without eviction a
 * departed node keeps 'lost' state forever and, because lost rows are sent
 * first, it permanently occupies a slot that a live neighbour needs. */
#define ND_EVICT_MS 600000u
typedef struct {mid_id id; uint32_t boot,hello,retired[4],state; unsigned cursor; uint64_t seen,ack,reply_at; int used,confirmed;} nd_peer;
typedef struct {mid_id self;uint32_t boot,group,hello_seq[4];unsigned hello_cursor;nd_peer peers[ND_PEERS];uint32_t tx_hello,tx_ack,rx_hello,rx_ack,rejected,full;} nd_node;
void nd_init(nd_node*,mid_id,uint32_t,uint32_t);
void nd_hello(nd_node*,mid_packet*,uint32_t);
/* 1 requires ACK reply, 0 consumed ACK/duplicate, -1 invalid. Physical source must match origin. */
int nd_receive(nd_node*,mid_id,const mid_packet*,uint64_t,mid_packet*);
nd_peer* nd_find(nd_node*,mid_id);
int nd_state(nd_peer*,uint64_t); /* 0 lost, 1 heard, 2 bidirectional */
int nd_direct(nd_node*,mid_id,uint32_t,uint64_t);
void nd_trim(nd_node*,uint64_t now);
#endif

