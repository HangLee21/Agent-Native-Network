#include "source_route.h"
#include "bridge.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static sr_node nodes[4];static mid_id ids[4]={{{2,0,0,0,0,1}},{{2,0,0,0,0,2}},{{2,0,0,0,0,3}},{{2,0,0,0,0,4}}};static int links[4][4];static uint64_t now;static unsigned delivered[4];
static void pump(void){for(unsigned k=0;k<40;k++){int any=0;for(unsigned i=0;i<4;i++){sr_out out;if(!sr_next_tx(&nodes[i],&out,now))continue;any=1;uint8_t bytes[250];int len=sr_encode(&out.packet,bytes,sizeof(bytes));assert(len>0);for(unsigned j=0;j<4;j++)if(links[i][j]&&(out.next.mac[0]==255||mid_equal(out.next,ids[j])))sr_receive(&nodes[j],ids[i],bytes,(size_t)len,now);sr_tx_result(&nodes[i],&out,1,now);}for(unsigned i=0;i<4;i++){sr_event e;while(sr_next_event(&nodes[i],&e))if(e.type==SR_DELIVERED)delivered[i]++;}if(!any)return;}assert(!"unbounded control");}
int main(void){for(unsigned i=0;i<4;i++)sr_init(&nodes[i],ids[i],100+i,31);for(unsigned i=1;i<4;i++){links[0][i]=links[i][0]=1;sr_neighbor(&nodes[0],ids[i],100+i,1);sr_neighbor(&nodes[i],ids[0],100,1);}mid_id pc=fg_service(77);sr_service(&nodes[1],pc,5,10000);sr_service(&nodes[3],pc,5,10000);uint8_t data[160];memset(data,0xab,160);assert(!sr_submit(&nodes[0],pc,1,data,160,0));pump();now=200;pump();assert(delivered[1]==1&&!delivered[3]);unsigned alternatives=0;for(unsigned i=0;i<SR_ROUTES;i++)alternatives+=nodes[0].routes[i].used&&mid_equal(nodes[0].routes[i].dst,pc);assert(alternatives>=2);
 /* B loses only its PC lease; radio stays a confirmed peer. */
 sr_service(&nodes[1],pc,5,0);now=300;assert(!sr_submit(&nodes[0],pc,2,data,160,now));pump();assert(delivered[1]==1&&nodes[0].peers[0].live);now=400;assert(!sr_submit(&nodes[0],pc,3,data,160,now));pump();assert(delivered[3]==1);
 sr_service(&nodes[3],pc,5,0);now=4000;assert(!sr_submit(&nodes[0],pc,4,data,160,now));pump();now=5500;pump();assert(delivered[1]+delivered[3]==2);assert(!sr_submit(&nodes[0],ids[2],5,data,160,now));pump();assert(delivered[2]==1);
 printf("PASS two simultaneous service entries, stable PC id,no fixed entry, deterministic candidate+retained alternative, PC-lease-only failure distinct from RF, all entries absent while board business continues; sizeof(sr_node)=%lu\n",(unsigned long)sizeof(sr_node));return 0;}
