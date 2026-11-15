#include "progress_health.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void){hg_record r={0};hg_boot(&r,0);for(unsigned k=0;k<3;k++){hg_state s={0};assert(hg_tick(&s,&r,0,1,1,1)==HG_HEALTHY);assert(hg_tick(&s,&r,14000,2,2,1)==HG_HEALTHY);assert(hg_tick(&s,&r,29000,2,3,1)==HG_RESTART_MAIN);hg_mark_restart(&r);hg_boot(&r,1);assert(r.count==k+1);}hg_state s={0};assert(hg_tick(&s,&r,0,1,1,1)==HG_HEALTHY);assert(hg_tick(&s,&r,15000,1,2,1)==HG_SUPPRESSED);hg_state q={0};assert(hg_tick(&q,&r,0,1,1,1)==HG_HEALTHY);assert(hg_tick(&q,&r,15000,2,1,1)==HG_LORA_STALLED);for(unsigned i=1;i<=130;i++)(void)hg_tick(&q,&r,15000+i*1000,2+i,1+i,1);assert(r.count==0);for(unsigned i=0;i<3;i++){hg_boot(&r,2);assert(r.count==i+1);}hg_boot(&r,0);assert(!r.count);r.check^=1;hg_boot(&r,1);assert(r.count==0&&r.magic==HG_MAGIC);puts("PASS simulated main stalls, bounded software/task-WDT resets, LoRa-only software isolation, stable reset and corrupt RTC record");return 0;}
