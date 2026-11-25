#include "mid.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static mid_id id(unsigned n){mid_id x={{2,0,0,0,0,(uint8_t)(n+1)}};return x;}
static mid_table table(unsigned n,unsigned src,unsigned dst){mid_table t={0};t.n=(uint8_t)n;t.k=1;t.src[0]=(uint8_t)src;t.dst[0]=(uint8_t)dst;for(unsigned i=0;i<n;i++){t.nodes[i]=id(i);if(i!=dst)t.w[0][i][dst]=65535;}return t;}
static mid_packet config(mid_table *t,unsigned seq){mid_packet p={.kind=1,.ttl=8,.boot=1,.seq=seq};p.origin=id(0);int n=mid_table_encode(t,p.body,sizeof(p.body));assert(n>0);p.size=(uint16_t)n;return p;}
static mid_packet data(unsigned src,unsigned dst,unsigned seq){mid_packet p={.kind=2,.ttl=8,.boot=17,.seq=seq,.size=22};p.origin=id(src);mid_id d=id(dst);memcpy(p.body,d.mac,6);return p;}
static void peer_pairs(void){
 unsigned count=0;uint16_t draws[2]={0,0};
 for(unsigned src=0;src<5;src++)for(unsigned dst=0;dst<5;dst++)if(src!=dst){
  mid_table t=table(5,src,dst);mid_packet c=config(&t,1);mid_node a,b;mid_id next;
  mid_init(&a,id(src),id(0),1);mid_init(&b,id(dst),id(0),1);assert(mid_config(&a,&c)==1&&mid_config(&b,&c)==1);assert(mid_tick(&a,0,draws)==1);
  mid_packet p=data(src,dst,++count);assert(mid_data(&a,&p,&next)==1&&mid_equal(next,id(dst)));assert(mid_data(&b,&p,&next)==2);assert(mid_data(&b,&p,&next)==0);
 }
 assert(count==20);puts("20 directed endpoint pairs on actual frozen C; synthetic transport only");
}
static void periods(void){
 mid_table t=table(3,0,2);t.w[0][0][2]=49151;t.w[0][0][1]=16384;mid_packet c=config(&t,1);mid_node n;mid_init(&n,id(0),id(0),1);assert(mid_config(&n,&c)==1);
 uint16_t draw[2]={16383,0};assert(mid_tick(&n,100,draw)==1&&n.next[0]==1);draw[0]=16384;assert(mid_tick(&n,599,draw)==0&&n.next[0]==1);assert(mid_tick(&n,600,draw)==1&&n.next[0]==2);
 draw[0]=65535;assert(mid_tick(&n,1100,draw)==-1&&n.next[0]==2);draw[0]=65534;assert(mid_tick(&n,1100,draw)==1&&n.next[0]==2);puts("Cumulative boundary and 500ms hold; invalid random draw rejected");
}
static void two_destinations(void){
 mid_table t=table(3,0,1);t.k=2;t.src[1]=0;t.dst[1]=2;for(unsigned i=0;i<3;i++)if(i!=2)t.w[1][i][2]=65535;
 mid_packet c=config(&t,1);mid_node n;mid_id next;uint16_t draw[2]={0,0};mid_init(&n,id(0),id(0),1);assert(mid_config(&n,&c)==1&&mid_tick(&n,0,draw)==1);
 mid_packet p=data(0,1,1);assert(mid_data(&n,&p,&next)==1&&mid_equal(next,id(1)));p=data(0,2,2);assert(mid_data(&n,&p,&next)==1&&mid_equal(next,id(2)));
 puts("Same source two destinations retained; source-global distinct sequences used");
}
static void control_and_wire(void){
 mid_node n;mid_init(&n,id(1),id(0),1);mid_table t=table(3,0,2);mid_packet c=config(&t,4);assert(mid_config(&n,&c)==1&&mid_config(&n,&c)==0);c.seq=3;assert(mid_config(&n,&c)==0);c.seq=5;assert(mid_config(&n,&c)==1);c.boot=2;assert(mid_config(&n,&c)==-1);
 uint8_t bytes[250];mid_packet p=data(0,2,11),d;int length=mid_encode(&p,bytes,sizeof(bytes));assert(length==46&&mid_decode(&d,bytes,(size_t)length)==0);assert(mid_decode(&d,bytes,(size_t)length-1)==-1);bytes[22]=1;assert(mid_decode(&d,bytes,(size_t)length)==-1);puts("Control origin/boot/increasing sequence and frame length/reserved-byte checks; no actual rebroadcast adapter exercised");
}
int main(int argc,char **argv){assert(argc==2);switch(atoi(argv[1])){case 0:peer_pairs();break;case 1:periods();break;case 2:two_destinations();break;case 3:control_and_wire();break;default:abort();}puts("PASS independent frozen candidate core");return 0;}
