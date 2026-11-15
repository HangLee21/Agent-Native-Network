#ifndef MOBILE_TELEMETRY_H
#define MOBILE_TELEMETRY_H
#include "mid.h"
#define MT_FRAME 52
#define MT_ROWS 8
#define MT_STALE_MS 30000u
#define MT_AGE_MAX 60000u
typedef struct {uint32_t boot,seq,age_ms,accuracy_mm;int32_t lat_e7,lon_e7;uint8_t source,fix;} mt_position;
typedef struct {int used;mid_id peer;int rssi_valid,channel_valid,rssi,channel;uint32_t count;int minimum,maximum;int64_t sum;uint64_t at,valid_at;} mt_rf;
typedef struct {int used;mid_id peer;uint32_t board_boot,announcement_seq,retired[4];unsigned cursor;mt_position position;uint8_t mode;uint64_t at;} mt_peer;
typedef struct {mid_id self;uint32_t board_boot,group,announcement_seq,retired[4];unsigned cursor;mt_position local;uint64_t injected;mt_rf rf[MT_ROWS];mt_peer peers[MT_ROWS];uint32_t rf_full,peer_full,rejected,duplicates;} mt_node;
void mid_mt_init(mt_node*,mid_id,uint32_t,uint32_t);
int mid_mt_set(mt_node*,const mt_position*,uint64_t);
mt_position mid_mt_aged(mt_position,uint64_t);
mt_position mid_mt_local(const mt_node*,uint64_t);
void mid_mt_sample(mt_node*,mid_id,int,int,int,int,uint64_t);
int mid_mt_encode(mt_node*,uint8_t,uint64_t,uint8_t*,size_t);
/* Returns1 applied,0 duplicate/older,-1 rejected. Caller handles group/ND policy. */
int mid_mt_receive(mt_node*,mid_id,const uint8_t*,size_t,uint64_t);
#endif
