#ifndef FLIGHT_PROGRESS_HEALTH_H
#define FLIGHT_PROGRESS_HEALTH_H
#include <stdint.h>
#define HG_MAGIC 0x3147484du
#define HG_STALL_MS 15000u
#define HG_STABLE_MS 120000u
#define HG_MAX_RESTARTS 3u
enum {HG_HEALTHY=0,HG_RESTART_MAIN=1,HG_SUPPRESSED=2,HG_LORA_STALLED=3};
typedef struct {uint32_t magic,count,pending,check;} hg_record;
typedef struct {uint32_t main_seq,lora_seq;uint64_t main_at,lora_at,stable_at;int initialized;} hg_state;
/* reset_kind: 0 other/manual, 1 our marked software reset, 2 task watchdog. */
void hg_boot(hg_record*,int reset_kind);
void hg_mark_restart(hg_record*);
/* A monitor cycle can request at most one supervisor-initiated restart.
 * LoRa stall alone is reported, not used to reset the shared Wi-Fi device. */
int hg_tick(hg_state*,hg_record*,uint64_t,uint32_t,uint32_t,int);
#endif
