#include "neighbors.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 mid_id a={{2,0,0,0,0,1}},b={{2,0,0,0,0,2}},c={{2,0,0,0,0,3}};
 nd_node A,B,C;nd_init(&A,a,10,9);nd_init(&B,b,20,9);nd_init(&C,c,30,8);
 mid_packet h,ack,unused;nd_hello(&A,&h,1);
 assert(nd_receive(&C,a,&h,100,&unused)<0); /* wrong group */
 assert(nd_receive(&B,c,&h,100,&unused)<0); /* source spoof */
 assert(nd_receive(&B,a,&h,100,&ack)==1);
 assert(nd_state(nd_find(&B,a),100)==1); /* one-way hearing not mutual */
 assert(!nd_direct(&A,b,20,100));
 assert(nd_receive(&A,b,&ack,101,&unused)==0);
 assert(nd_direct(&A,b,20,101));
 assert(nd_receive(&B,a,&h,200,&unused)==0); /* duplicate no ACK burst */
 nd_hello(&B,&h,2);assert(nd_receive(&A,b,&h,1000,&ack)==1);
 assert(nd_receive(&B,a,&ack,1001,&unused)==0);assert(nd_direct(&B,a,10,1001));
 assert(nd_state(nd_find(&A,b),9101)==1);assert(!nd_direct(&A,b,20,9101));
 assert(nd_state(nd_find(&A,b),13000)==0);
 /* Old ACK cannot keep a neighbor alive through repeated replay. */
 assert(nd_receive(&B,a,&ack,14000,&unused)==0);assert(!nd_direct(&B,a,10,14000));
 mid_packet oldhello;nd_hello(&B,&oldhello,3);
 /* Peer reboot: boot 21 needs a new challenge and invalidates old data immediately. */
 nd_init(&B,b,21,9);nd_hello(&B,&h,1);assert(nd_receive(&A,b,&h,15000,&ack)==1);
 assert(!nd_direct(&A,b,20,15001));assert(!nd_direct(&A,b,21,15001));
 assert(nd_receive(&A,b,&oldhello,15002,&unused)<0); /* retired old boot */
 nd_hello(&A,&h,4);assert(nd_receive(&B,a,&h,16000,&ack)==1);
 assert(nd_receive(&A,b,&ack,16001,&unused)==0);assert(nd_direct(&A,b,21,16001));
 /* Rebooted local node rejects a reply to a previous local boot. */
 nd_init(&A,a,11,9);assert(nd_receive(&A,b,&ack,17000,&unused)<0);
 /* Malformed control, wrong TTL, and finite table capacity. */
 h.ttl=2;assert(nd_receive(&B,a,&h,17001,&unused)<0);
 for(unsigned i=0;i<ND_PEERS;i++){nd_node X;mid_id id={{2,0,0,0,1,(uint8_t)(i+1)}};nd_init(&X,id,40+i,9);nd_hello(&X,&h,1);assert(nd_receive(&A,id,&h,18000+i*501,&ack)==1);}
 nd_init(&B,b,22,9);nd_hello(&B,&h,1);assert(nd_receive(&A,b,&h,23000,&ack)<0);assert(A.full==1);
 puts("PASS unknown neighbors, group/source checks, one-way, bidirectional challenge, timeout boundaries, duplicate ACK replay, peer/local restart, retired boot, bounded table");
 return 0;
}
