#ifndef MID_H
#define MID_H
#include <stdint.h>
#include <stddef.h>
#define MID_N 5
#define MID_F 2
#define MID_FRAME 250
#define MID_HEADER 24
#define MID_PAYLOAD 160
typedef struct { uint8_t mac[6]; } mid_id;
typedef struct { uint8_t n,k; mid_id nodes[MID_N]; uint8_t src[MID_F],dst[MID_F]; uint16_t w[MID_F][MID_N][MID_N]; } mid_table;
typedef struct { uint8_t kind,ttl; mid_id origin; uint32_t boot,seq; uint16_t size; uint8_t body[MID_FRAME-MID_HEADER]; } mid_packet;
typedef struct { mid_id origin; uint32_t boot,seq; int used; } mid_seen;
typedef struct {
 mid_id self,publisher; uint32_t publisher_boot,config_seq; int have_seq,have_table;
 mid_table table; int next[MID_F]; uint64_t last_tick; int ticked;
 mid_seen seen[64]; unsigned cursor;
} mid_node;
int mid_equal(mid_id a,mid_id b);
int mid_unicast(mid_id id);
int mid_encode(const mid_packet *p,uint8_t *out,size_t cap);
int mid_decode(mid_packet *p,const uint8_t *in,size_t len);
int mid_table_encode(const mid_table *t,uint8_t *out,size_t cap);
int mid_table_decode(mid_table *t,const uint8_t *in,size_t len);
void mid_init(mid_node *n,mid_id self,mid_id publisher,uint32_t boot);
/* 1 accepted, 0 duplicate, -1 invalid; packet may be rebroadcast if ttl>1. */
int mid_config(mid_node *n,const mid_packet *p);
/* draw[k] uniform 0..65534 supplied by adapter; 1 if a new 500ms period selected. */
int mid_tick(mid_node *n,uint64_t now,const uint16_t draw[MID_F]);
/* 2 local endpoint, 1 forward (next filled), 0 duplicate, -1 invalid/no-route/ttl. */
int mid_data(mid_node *n,const mid_packet *p,mid_id *next);
#endif
