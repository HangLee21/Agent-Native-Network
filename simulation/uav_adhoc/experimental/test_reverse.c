#include "source_route.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#ifndef ENGINEERING_REVERSE_CACHE
#define ENGINEERING_REVERSE_CACHE 0
#endif
static sr_node n[3];static mid_id id[3]={{{2,0,0,0,0,1}},{{2,0,0,0,0,2}},{{2,0,0,0,0,3}}};static unsigned c_to_a;
static int link(unsigned a,unsigned b){return a+1==b||b+1==a;}
static void events(void){for(unsigned i=0;i<3;i++){sr_event e;while(sr_next_event(&n[i],&e))if(e.type==SR_DELIVERED&&i==0&&e.seq==33){assert(e.len==3&&!memcmp(e.payload,"ack",3));c_to_a++;}}}
static void pump(uint64_t t){
 for(unsigned k=0;k<100;k++){
  int any=0;for(unsigned i=0;i<3;i++){sr_out o;if(!sr_next_tx(&n[i],&o,t))continue;any=1;uint8_t b[250];int z=sr_encode(&o.packet,b,sizeof(b));assert(z>0);
   for(unsigned j=0;j<3;j++)if(link(i,j)&&(o.next.mac[0]==255||mid_equal(o.next,id[j])))(void)sr_receive(&n[j],id[i],b,z,t);
   sr_tx_result(&n[i],&o,1,t);
  }events();if(!any)return;
 }assert(!"unexpected nonquiescence");
}
static void setup(void){
 memset(n,0,sizeof(n));c_to_a=0;
 for(unsigned i=0;i<3;i++)sr_init(&n[i],id[i],i+1,31);
 for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++)if(link(i,j))sr_neighbor(&n[i],id[j],j+1,1);
}
int main(void){
 setup();
 assert(sr_submit(&n[0],id[2],10,(const uint8_t*)"foo",3,1)==0);pump(1);
 assert(sr_submit(&n[2],id[0],33,(const uint8_t*)"ack",3,10)==0);
 sr_out first;assert(sr_next_tx(&n[2],&first,10));assert(sr_base_type(first.packet.type)==(ENGINEERING_REVERSE_CACHE?SR_DATA:SR_RREQ));
 uint8_t raw[250];int len=sr_encode(&first.packet,raw,sizeof(raw));assert(len>0);assert(sr_receive(&n[1],id[2],raw,(size_t)len,10)==0);sr_tx_result(&n[2],&first,1,10);pump(10);
 for(unsigned i=0;i<3;i++){sr_tick(&n[i],210);}pump(210);assert(c_to_a==1);
 sr_neighbor(&n[2],id[1],2,0);
 assert(sr_submit(&n[2],id[0],34,(const uint8_t*)"ack",3,220)==0);sr_out out;assert(sr_next_tx(&n[2],&out,220));assert(sr_base_type(out.packet.type)==SR_RREQ);
 /* At the exact 3 s expiry, even an otherwise live first hop must rediscover. */
 setup();assert(sr_submit(&n[0],id[2],10,(const uint8_t*)"foo",3,1)==0);pump(1);
 sr_tick(&n[2],3001);assert(sr_submit(&n[2],id[0],35,(const uint8_t*)"ack",3,3001)==0);
 assert(sr_next_tx(&n[2],&out,3001)&&sr_base_type(out.packet.type)==SR_RREQ);
 /* A full route table is not enlarged or overwritten by a passive route. */
 setup();for(unsigned i=0;i<SR_ROUTES;i++){n[2].routes[i].used=1;n[2].routes[i].dst=(mid_id){{2,0,0,0,0,0}};n[2].routes[i].dst.mac[5]=(uint8_t)(10+i);n[2].routes[i].until=10000;}
 assert(sr_submit(&n[0],id[2],10,(const uint8_t*)"foo",3,1)==0);pump(1);
 assert(n[2].request_seq==0);
 for(unsigned i=0;i<SR_ROUTES;i++)assert(n[2].routes[i].used&&n[2].routes[i].dst.mac[5]==10+i);
 puts("PASS reverse cache, 3s expiry, full table and stale first-hop invalidation");return 0;
}
