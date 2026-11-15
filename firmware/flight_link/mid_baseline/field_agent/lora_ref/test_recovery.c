#include "recovery.h"
#include "flight_control.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct{unsigned calls,failures,role,frequency;} fake;
static int apply(void*x){fake*f=x;f->calls++;if(f->failures){f->failures--;return -1;}assert(f->role==2&&f->frequency==470500000);return 0;}
static void put32(uint8_t*p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
int main(void){
 const uint8_t mac[6]={2,0,0,0,0,1};uint8_t c[48]={0},reply[48];fc_state fc;fc_init(&fc,mac,7);fc_report_sent(&fc,10,0);memcpy(c,"LRC2",4);c[4]=1;c[5]=1;c[6]=48;memcpy(c+8,mac,6);put32(c+16,7);put32(c+20,10);put32(c+24,1);put32(c+32,60000);put32(c+36,42);put32(c+44,fc_crc32(c,44));assert(fc_receive(&fc,c,48,10,3,reply)==1);
 for(unsigned fault=0;fault<4;fault++){lref_recovery r={0};fake f={.failures=1,.role=2,.frequency=470500000};lref_recovery_fault(&r,100);assert(!lref_recovery_tick(&r,1099,apply,&f));assert(lref_recovery_tick(&r,1100,apply,&f)==-1);assert(!lref_recovery_tick(&r,3099,apply,&f));assert(lref_recovery_tick(&r,3100,apply,&f)==1);assert(!r.active&&!r.exhausted&&f.calls==2);assert(fc_receive(&fc,c,48,3101,3,reply)==2&&fc.executed==1);}
 lref_recovery r={0};fake f={.failures=4,.role=2,.frequency=470500000};lref_recovery_fault(&r,0);assert(lref_recovery_tick(&r,1000,apply,&f)==-1);assert(lref_recovery_tick(&r,3000,apply,&f)==-1);assert(lref_recovery_tick(&r,7000,apply,&f)==-1);assert(lref_recovery_tick(&r,15000,apply,&f)==-2);assert(!lref_recovery_tick(&r,74999,apply,&f));assert(lref_recovery_tick(&r,75000,apply,&f)==1);
 puts("PASS portable LoRa recovery scheduler: bounded backoff, cooldown, later recovery, control dedup retained; fake apply only");return 0;
}
