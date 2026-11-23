#include "telemetry.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void){
 mid_id a={{2,0,0,0,0,1}},b={{2,0,0,0,0,2}},wrong={{2,0,0,0,0,3}};mt_node A,B;mid_mt_init(&A,a,100,30);mid_mt_init(&B,b,200,30);uint8_t wire[MT_FRAME],old[MT_FRAME];
 assert(mid_mt_encode(&A,2,0,wire,sizeof(wire))==MT_FRAME);assert(mid_mt_receive(&B,a,wire,sizeof(wire),0)==1);assert(!B.peers[0].position.fix&&!B.peers[0].position.boot); /* bare board */
 mt_position p={.boot=7,.seq=1,.age_ms=500,.accuracy_mm=UINT32_MAX,.lat_e7=312345678,.lon_e7=1212345678,.source=2,.fix=1};
 assert(!mid_mt_set(&A,&p,1000));assert(mid_mt_set(&A,&p,1001)<0);assert(mid_mt_local(&A,2000).age_ms==1500);
 assert(mid_mt_encode(&A,2,2000,wire,sizeof(wire))==52);memcpy(old,wire,52);assert(mid_mt_receive(&B,a,wire,52,2100)==1);assert(mid_mt_receive(&B,a,wire,52,9999)==0&&B.peers[0].at==2100);
 mt_position remote=mid_mt_aged(B.peers[0].position,1000);assert(remote.age_ms==2500&&remote.fix&&remote.source==2&&remote.accuracy_mm==UINT32_MAX);assert(remote.lat_e7==312345678&&remote.lon_e7==1212345678);
 assert(mid_mt_receive(&B,wrong,wire,52,2200)<0);wire[4]=31;assert(mid_mt_receive(&B,a,wire,52,2200)<0);memcpy(wire,old,52);wire[49]=1;assert(mid_mt_receive(&B,a,wire,52,2200)<0);
 assert(!mid_mt_local(&A,31001).fix);assert(mid_mt_local(&A,UINT64_MAX).age_ms==60000);assert(mid_mt_encode(&A,2,31001,wire,52)==52&&!wire[47]);
 p.boot=8;p.seq=1;p.source=1;assert(!mid_mt_set(&A,&p,32000));p.boot=7;p.seq=2;assert(mid_mt_set(&A,&p,32001)<0);p.boot=8;p.seq=2;p.lat_e7=900000001;assert(mid_mt_set(&A,&p,32002)<0);
 mid_mt_init(&A,a,101,30);assert(mid_mt_encode(&A,2,33000,wire,52)==52);assert(mid_mt_receive(&B,a,wire,52,33001)==1);assert(mid_mt_receive(&B,a,old,52,33002)<0); /* retired boardboot */
 mid_mt_sample(&B,a,1,-50,1,6,100);mid_mt_sample(&B,a,1,-70,1,6,200);mid_mt_sample(&B,a,1,0,1,6,300);assert(B.rf[0].count==3&&B.rf[0].minimum==-70&&B.rf[0].maximum==0&&B.rf[0].sum==-120);
 mid_mt_sample(&B,a,0,0,0,0,400);assert(!B.rf[0].rssi_valid&&B.rf[0].count==3&&B.rf[0].valid_at==300); /* unavailable not synthetic0 */
 for(unsigned i=0;i<MT_ROWS;i++){mid_id x={{2,0,0,0,1,(uint8_t)i}};mid_mt_sample(&B,x,1,-60,1,6,500);}assert(B.rf_full==1);
 p=(mt_position){.boot=9,.seq=1,.source=0,.fix=0,.accuracy_mm=UINT32_MAX};assert(!mid_mt_set(&A,&p,35000));assert(mid_mt_encode(&A,2,35000,wire,51)<0);
 printf("PASS52B position wire, simulated/gnss/unavailable, age+stale, epoch/seq/replay, board restart, malformed/source/group, real RSSI0 and missing metadata, bounded rows; sizeof(mt_node)=%lu\n",(unsigned long)sizeof(mt_node));
 return 0;
}
