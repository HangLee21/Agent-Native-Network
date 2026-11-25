#include "neighbors.h"
#include "neighbor_sync.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#ifndef ENGINEERING_RECLAIM_LOST
#define ENGINEERING_RECLAIM_LOST 0
#endif
static mid_id id(unsigned n){mid_id x={{2,0,0,0,0,0}};x.mac[5]=(uint8_t)(n+1);return x;}
static nd_node receiver,senders[41];
static int hello(unsigned i,uint64_t now){mid_packet p,reply;nd_hello(&senders[i],&p,1);return nd_receive(&receiver,id(i),&p,now,&reply);}
int main(void){
 nd_init(&receiver,id(0),1,31);
 for(unsigned i=1;i<=40;i++)nd_init(&senders[i],id(i),i+1,31);
 for(unsigned i=1;i<=32;i++)assert(hello(i,100)==1);
 assert(hello(33,101)==-1); /* no live/heard peer can be displaced */
 for(unsigned i=33;i<=40;i++){
  int got=hello(i,12101+i);
  assert(ENGINEERING_RECLAIM_LOST?got==1:got==-1);
 }
 sr_node router;sr_init(&router,id(0),1,31);
 for(unsigned i=1;i<=32;i++)sr_neighbor(&router,id(i),i+1,1);
 e1_clear_absent_neighbors(&router,&receiver);
 if(ENGINEERING_RECLAIM_LOST){assert(nd_find(&receiver,id(1))==NULL);assert(nd_find(&receiver,id(40))!=NULL);assert(!router.peers[0].used);sr_neighbor(&router,id(40),41,1);assert(router.peers[0].used&&mid_equal(router.peers[0].id,id(40))&&router.peers[0].live);}
 else {assert(nd_find(&receiver,id(1))!=NULL);assert(nd_find(&receiver,id(40))==NULL);assert(router.peers[0].live);}
 puts("PASS 32-peer bound, no live eviction and 40-member churn");return 0;
}
