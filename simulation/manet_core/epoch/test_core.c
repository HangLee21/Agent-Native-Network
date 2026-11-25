#include "aodv.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static ma_node a,b;
static void p32(uint8_t*p,uint32_t v){p[0]=v;p[1]=v>>8;p[2]=v>>16;p[3]=v>>24;}
static void mk(uint8_t*f,unsigned type,unsigned src,unsigned dst,uint32_t boot,uint32_t seq){memset(f,0,MA_HEADER);f[0]=MA_MAGIC;f[1]=MA_VERSION;f[2]=type;f[3]=MA_HEADER;f[4]=8;f[5]=src;f[6]=dst;p32(f+8,boot);p32(f+20,seq);f[28]=1;}
int main(void){uint8_t f[MA_MTU],payload=4;int next,type,len;
 ma_init(&a,1,0);a.route[2]=(ma_route){1,1,2,1,10,10000};assert(ma_submit(&a,2,5,&payload,1,1)==0);len=ma_next(&a,f,&next,&type);assert(len==33&&next==2&&type==MA_DATA);ma_result(&a,0,10);assert(!a.route[2].valid&&a.route[2].seq==11);len=ma_next(&a,f,&next,&type);assert(len==32&&next==-1&&type==MA_RERR);ma_init(&b,0,0);b.route[2]=(ma_route){1,1,1,2,10,10000};assert(ma_receive(&b,1,f,len,11)==0);assert(!b.route[2].valid&&b.route[2].seq==11);puts("RERR propagation PASS");
 ma_init(&a,1,0);a.route[2]=(ma_route){1,1,0,2,0xfffffffeu,10000};mk(f,MA_RREP,0,2,1,1);ma_receive(&a,2,f,32,0);assert(a.route[2].seq==1&&a.route[2].next==2);p32(f+20,0xfffffffdu);ma_receive(&a,0,f,32,1);assert(a.route[2].seq==1&&a.route[2].next==2);puts("sequence wrap and stale rejection PASS");
 ma_init(&a,1,0);a.route[2]=(ma_route){1,1,2,1,9,10000};mk(f,MA_RREP,1,2,99,10);assert(ma_receive(&a,2,f,32,0)<0);assert(a.route[2].seq==9);puts("stale local boot reply PASS");
 ma_init(&a,1,0);mk(f,MA_RREQ,0,3,1,0);p32(f+16,42);p32(f+24,1);assert(ma_receive(&a,0,f,32,0)==0);assert(ma_receive(&a,0,f,32,1)==0);assert(a.rreq_rx==2&&a.rreq_duplicates==1);puts("RREQ dedup PASS");
 ma_init(&a,1,2);mk(f,MA_RREQ,0,3,1,0);p32(f+24,1);for(unsigned i=1;i<=20;i++){p32(f+16,i);ma_receive(&a,0,f,32,i);}assert(a.rreq_forward==8&&a.forward_suppressed==12);p32(f+16,21);ma_receive(&a,0,f,32,1001);assert(a.rreq_forward==9);puts("forward rate cap and window reset PASS");
 ma_init(&a,1,0);a.route[2]=(ma_route){1,1,2,1,10,10000};a.route[0]=(ma_route){1,1,0,1,5,10000};mk(f,MA_RREP,0,2,1,10);assert(ma_receive(&a,2,f,32,0)==0);assert(a.qn==0&&a.route[2].seq==10);puts("unchanged RREP not forwarded PASS");
 ma_init(&a,1,0);a.route[2]=(ma_route){1,1,2,1,10,10000};mk(f,MA_RERR,0,2,1,9);assert(ma_receive(&a,2,f,32,1)==0);assert(a.route[2].valid&&a.route[2].seq==10);puts("stale RERR ignored PASS");
 ma_init(&a,1,0);a.own_seq=5;mk(f,MA_RREQ,0,1,1,5);p32(f+16,1);p32(f+24,1);assert(ma_receive(&a,0,f,32,0)==0);assert(a.own_seq==5);p32(f+16,2);p32(f+20,6);assert(ma_receive(&a,0,f,32,1)==0);assert(a.own_seq==6);p32(f+16,3);p32(f+20,9);assert(ma_receive(&a,0,f,32,2)==0);assert(a.own_seq==9);puts("destination sequence maximum PASS");
 ma_init(&a,1,4);mk(f,MA_RREQ,0,3,1,0);p32(f+16,1);p32(f+24,1);ma_receive(&a,0,f,32,1);for(unsigned i=0;i<40;i++)ma_receive(&a,0,f,32,2+i);for(unsigned i=2;i<14;i++){p32(f+16,i);ma_receive(&a,0,f,32,1001+i);}assert(a.pressure_active&&a.rreq_forward==9&&a.forward_suppressed==4);puts("adaptive pressure cap PASS");
 ma_init(&a,1,1);for(unsigned i=2;i<13;i++)assert(ma_submit(&a,i,i,&payload,1,1)==0);assert(a.rreq_count==10&&a.qn==10&&a.find[12].active&&a.find[12].deadline==1000&&a.find[12].deferred);for(unsigned i=2;i<12;i++)a.find[i].active=0;ma_tick(&a,1000);assert(a.find[12].ttl==2&&a.find[12].attempts==1);puts("baseline deferred ring PASS");
 ma_init(&a,1,1);mk(f,MA_RREQ,0,4,1,0);p32(f+16,1);p32(f+24,50);ma_receive(&a,2,f,32,1);assert(a.route[0].valid&&a.route[0].next==2&&a.route[0].seq==50);p32(f+8,2);p32(f+16,2);p32(f+24,1);ma_receive(&a,3,f,32,2);assert(a.route[0].valid&&a.route[0].next==3&&a.route[0].seq==1);p32(f+8,1);p32(f+16,3);ma_receive(&a,2,f,32,3);assert(a.route[0].next==3&&a.stale_epoch_dropped==1);mk(f,MA_RREP,0,4,1,3);ma_receive(&a,2,f,32,4);assert(a.stale_epoch_dropped==2);puts("monotonic origin epoch guard PASS");
 ma_init(&a,1,1);assert(ma_set_boot(&a,0)<0&&ma_set_boot(&a,42)==0&&a.boot==42);assert(ma_submit(&a,3,1,&payload,1,0)==0);assert(ma_set_boot(&a,43)<0);ma_init(&a,1,1);memset(f,0,32);ma_receive(&a,0,f,32,0);assert(ma_set_boot(&a,43)<0);puts("boot injection before traffic PASS");
 return 0;}
