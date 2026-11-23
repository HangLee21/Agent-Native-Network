#ifndef FIELD_BRIDGE_H
#define FIELD_BRIDGE_H
#include "mid.h"
#define FG_HEADER 20
#define FG_APP_MAX 128
#define FG_REQUESTS 16
enum {FG_DOWN=1,FG_UP,FG_RECEIPT,FG_REPORT};
typedef struct {uint8_t kind;uint32_t pc_id,session,transaction;uint16_t len;uint8_t body[140];} fg_packet;
typedef struct {int used;uint32_t pc_id,session,transaction,source_seq;mid_id dst;uint16_t len;uint8_t bytes[128];} fg_request;
typedef struct {int used;uint32_t pc_id,session,transaction;uint16_t len;uint8_t bytes[128];} fg_delivery;
typedef struct {fg_request requests[16];fg_delivery deliveries[32];unsigned request_next,delivery_next;uint32_t request_evictions,delivery_evictions;} fg_node;
mid_id fg_service(uint32_t);
int fg_encode(const fg_packet*,uint8_t*,size_t);
int fg_decode(fg_packet*,const uint8_t*,size_t);
/*0 new,1 exact duplicate,-1 changed identity content. New is committed by caller after admission.*/
int fg_request_check(fg_node*,const fg_packet*,mid_id,fg_request**);
fg_request*fg_request_commit(fg_node*,const fg_packet*,mid_id,uint32_t);
/*1 first actual destination delivery,0 duplicate,-1 changed content.*/
int fg_destination(fg_node*,const fg_packet*);
#endif
