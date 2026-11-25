#ifndef FIELD_AGENT_H
#define FIELD_AGENT_H
#include "mid.h"
#define FA_CONFIG_BYTES 72
#define FA_RECORDS 128
#define FA_ORIGINS 16
#define FA_KINDS 5
enum {FA_ADMITTED=0,FA_SUBMITTED,FA_RECEIVED,FA_RELAY_RX,FA_RELAY_TX};
typedef struct {uint32_t min_ms,max_ms,segment;uint8_t min_len,max_len,bytes,observed,start,roster_n;uint16_t checkpoint_s;mid_id roster[8];} fa_config;
typedef struct {mid_id origin,dst;uint32_t boot,seq,segment;uint64_t cursor,at;uint8_t kind,len;uint8_t payload[160];} fa_record;
typedef struct {int used;mid_id origin;uint32_t boot,highest[FA_KINDS];uint64_t seen[FA_KINDS];} fa_seen;
typedef struct {fa_config cfg;int configured,running;uint64_t due,cursor;uint32_t rounds,no_destination,rejected,overwritten,late,origins_full;uint32_t totals[FA_KINDS],segment_counts[FA_KINDS];uint64_t payload_bytes[FA_KINDS];fa_record records[FA_RECORDS];unsigned head,count;fa_seen seen[FA_ORIGINS];char note[32];} fa_node;
typedef uint32_t(*fa_rng)(void*);
int fa_config_valid(const fa_config*);
int fa_config_encode(const fa_config*,uint8_t*,size_t);
int fa_config_decode(fa_config*,const uint8_t*,size_t);
void fa_init(fa_node*);
void fa_apply(fa_node*,const fa_config*,uint64_t,fa_rng,void*);
void fa_resume(fa_node*,uint64_t,fa_rng,void*);
/* Caller passes eligible candidates incl optional logical PC service; excludes self. */
int fa_next(fa_node*,mid_id,const mid_id*,unsigned,uint64_t,fa_rng,void*,mid_id*,uint8_t*,unsigned*);
int fa_log(fa_node*,unsigned,mid_id,uint32_t,uint32_t,mid_id,const uint8_t*,unsigned,uint64_t);
void fa_mark(fa_node*,uint32_t,const char*);
const fa_record*fa_after(const fa_node*,uint64_t);
#endif
