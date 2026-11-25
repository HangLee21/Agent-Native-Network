#include "source_route.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MAXN 6
static sr_node nodes[MAXN];static mid_id ids[MAXN];static unsigned delivered,no_route;
static int link(int a,int b){return (a+1==b||b+1==a);}
static void drain(unsigned count){
 for(unsigned i=0;i<count;i++){sr_event e;while(sr_next_event(&nodes[i],&e)){
  if(e.type==SR_DELIVERED){assert(i==count-1&&e.len==4&&!memcmp(e.payload,"test",4));delivered++;}
  if(e.type==SR_NO_ROUTE&&i==0&&e.seq==10)no_route++;
 }}
}
static void pump(unsigned count,uint64_t t){
 for(unsigned round=0;round<100;round++){
  int any=0;for(unsigned i=0;i<count;i++){
   sr_out out;if(!sr_next_tx(&nodes[i],&out,t))continue;any=1;
   uint8_t bytes[250];int len=sr_encode(&out.packet,bytes,sizeof(bytes));assert(len>0);
   for(unsigned j=0;j<count;j++)if(link(i,j)&&(out.next.mac[0]==255||mid_equal(out.next,ids[j])))
    (void)sr_receive(&nodes[j],ids[i],bytes,(size_t)len,t);
   sr_tx_result(&nodes[i],&out,1,t);
  }
  drain(count);if(!any)return;
 }
 assert(!"control exchange did not quiesce");
}
static void scenario(unsigned count){
 memset(nodes,0,sizeof(nodes));delivered=no_route=0;
 for(unsigned i=0;i<count;i++){ids[i]=(mid_id){{2,0,0,0,0,0}};ids[i].mac[5]=(uint8_t)(i+1);sr_init(&nodes[i],ids[i],i+1,31);}
 for(unsigned i=0;i<count;i++)for(unsigned j=0;j<count;j++)if(link(i,j))sr_neighbor(&nodes[i],ids[j],j+1,1);
 assert(sr_submit(&nodes[0],ids[count-1],10,(const uint8_t*)"test",4,1)==0);pump(count,1);
 for(unsigned i=0;i<count;i++){sr_tick(&nodes[i],201);}pump(count,201);
 for(unsigned i=0;i<count;i++){sr_tick(&nodes[i],1501);}pump(count,1501);
 if(count<=5)assert(delivered==1);else assert(delivered==0 && no_route>0);
}
int main(void){scenario(2);scenario(3);scenario(5);scenario(6);puts("PASS 1-, 2-, 4-hop delivery and 5-hop boundary");return 0;}
