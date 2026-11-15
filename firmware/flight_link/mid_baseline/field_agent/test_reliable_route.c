#include "source_route.h"
#include "reliable.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static mid_id ids[3]={{{2,0,0,0,0,1}},{{2,0,0,0,0,2}},{{2,0,0,0,0,3}}};
static sr_node nodes[3];static fr_state states[3];static unsigned seq[3], received,confirmed,dropped_ack;static uint64_t now;
static int submit(void *ctx,const uint8_t dst[6],const uint8_t *buf,size_t len){unsigned i=*(unsigned*)ctx;mid_id d;memcpy(d.mac,dst,6);return sr_submit(&nodes[i],d,++seq[i],buf,len,now);}
static void pump(void){
 for(unsigned turn=0;turn<100;turn++){
  int progress=0;
  for(unsigned i=0;i<3;i++){sr_out out;if(!sr_next_tx(&nodes[i],&out,now))continue;progress=1;uint8_t wire[250];int len=sr_encode(&out.packet,wire,sizeof(wire));assert(len>0);
   for(unsigned j=0;j<3;j++)if((i+1==j||j+1==i)&&(out.next.mac[0]==255||mid_equal(out.next,ids[j])))(void)sr_receive(&nodes[j],ids[i],wire,(size_t)len,now);
   sr_tx_result(&nodes[i],&out,1,now);
  }
  for(unsigned i=0;i<3;i++){sr_event e;while(sr_next_event(&nodes[i],&e)){progress=1;if(e.type!=SR_DELIVERED)continue;fr_message msg;uint8_t ack[160];size_t n=0;int r=fr_receive(&states[i],e.origin.mac,e.boot,e.payload,e.len,now,&msg,ack,&n);assert(r>=0);
   if(r==1){assert(i==2&&msg.len==3&&!memcmp(msg.payload,"abc",3));received++;}
   if(r==1||r==2){if(!dropped_ack)dropped_ack=1;else assert(!submit(&i,e.origin.mac,ack,n));}
   if(r==3){assert(i==0);confirmed++;}
  }}
  if(!progress)return;
 }
 assert(!"network did not quiesce");
}
int main(void){for(unsigned i=0;i<3;i++){sr_init(&nodes[i],ids[i],100+i,27);fr_init(&states[i],ids[i].mac,100+i);}for(unsigned i=0;i<2;i++){sr_neighbor(&nodes[i],ids[i+1],101+i,1);sr_neighbor(&nodes[i+1],ids[i],100+i,1);}
 uint32_t id;assert(!fr_start(&states[0],ids[2].mac,102,(const uint8_t*)"abc",3,0,&id));unsigned src=0;
 for(now=0;now<=7000;now+=100){fr_tick(&states[0],now,submit,NULL,&src);for(unsigned i=0;i<3;i++)sr_tick(&nodes[i],now);pump();}
 assert(received==1&&confirmed==1&&dropped_ack==1&&states[2].duplicates==1&&states[0].timeouts==0);
 puts("PASS three-node multi-hop, dropped first ACK, bounded retry, duplicate suppression and endpoint confirmation (host fixture)");return 0;
}
