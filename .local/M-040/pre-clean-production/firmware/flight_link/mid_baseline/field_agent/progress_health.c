#include "progress_health.h"
#include <string.h>
static uint32_t sum(const hg_record*r){return r->magic^r->count^r->pending^0xa615c3e9u;}
static void seal(hg_record*r){r->check=sum(r);}
void hg_boot(hg_record*r,int reset_kind){if(r->magic!=HG_MAGIC||r->check!=sum(r)||r->count>HG_MAX_RESTARTS||r->pending>1){memset(r,0,sizeof(*r));r->magic=HG_MAGIC;}if(reset_kind==2||(reset_kind==1&&r->pending)){if(r->count<HG_MAX_RESTARTS)r->count++;}else r->count=0;r->pending=0;seal(r);}
void hg_mark_restart(hg_record*r){r->pending=1;seal(r);}
int hg_tick(hg_state*s,hg_record*r,uint64_t now,uint32_t main_seq,uint32_t lora_seq,int watch_lora){
 if(!s->initialized){s->initialized=1;s->main_seq=main_seq;s->lora_seq=lora_seq;s->main_at=s->lora_at=s->stable_at=now;return HG_HEALTHY;}
 if(main_seq!=s->main_seq){s->main_seq=main_seq;s->main_at=now;}
 if(!watch_lora||lora_seq!=s->lora_seq){s->lora_seq=lora_seq;s->lora_at=now;}
 int main_stall=now-s->main_at>=HG_STALL_MS,lora_stall=watch_lora&&now-s->lora_at>=HG_STALL_MS;
 if(main_stall||lora_stall)s->stable_at=now;else if(now-s->stable_at>=HG_STABLE_MS&&r->count){r->count=0;r->pending=0;seal(r);s->stable_at=now;}
 if(main_stall)return r->count>=HG_MAX_RESTARTS?HG_SUPPRESSED:HG_RESTART_MAIN;
 return lora_stall?HG_LORA_STALLED:HG_HEALTHY;
}
