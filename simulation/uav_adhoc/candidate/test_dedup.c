#include "source_route.h"
#include "peer_cache_mac.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#ifndef ENGINEERING_RREQ_DEDUP
#define ENGINEERING_RREQ_DEDUP 0
#endif
static mid_id id(unsigned x){mid_id a={{2,0,0,0,0,0}};a.mac[5]=x;return a;}
static sr_node n;static uint8_t data[250];
static void send_request(unsigned source,unsigned via,unsigned boot,unsigned request,unsigned dst){
 sr_packet p={.type=SR_RREQ,.n=2,.index=1,.ttl=3,.group=31,.boot=boot,.seq=request,.request=request,.dst={{2,0,0,0,0,0}}};
 p.dst=id(dst);p.path[0]=id(source);p.path[1]=id(via);
 int z=sr_encode(&p,data,sizeof(data));assert(z>0);assert(sr_receive(&n,id(via),data,z,100)==0);
}
int main(void){
 sr_init(&n,id(4),4,31);sr_neighbor(&n,id(2),2,1);sr_neighbor(&n,id(3),3,1);
 send_request(1,2,1,7,9);send_request(1,3,1,7,9);
 assert(n.count==(ENGINEERING_RREQ_DEDUP?1u:2u));
 /* Same boot/request from a different origin must never be suppressed. */
 send_request(5,3,1,7,9);assert(n.count==(ENGINEERING_RREQ_DEDUP?2u:3u));
 /* Original repeated exact path always suppressed. */
 send_request(1,2,1,7,9);assert(n.count==(ENGINEERING_RREQ_DEDUP?2u:3u));
 e1_peer_cache cache={0};uint8_t removed[6];mid_id broadcast={{255,255,255,255,255,255}};
 assert(e1_peer_access(&cache,broadcast.mac,0,0,removed)==0);
 for(unsigned i=0;i<19;i++){mid_id peer=id(i+1);assert(e1_peer_access(&cache,peer.mac,i+1,0,removed)==0);}
 mid_id next=id(20);
 assert(cache.count==20 && e1_peer_access(&cache,next.mac,22,0,removed)==-1);
 assert(e1_peer_access(&cache,next.mac,23,1,removed)==1 && removed[5]==1);
 for(unsigned i=20;i<120;i++){mid_id peer=id((i%30)+1);assert(e1_peer_access(&cache,peer.mac,i+4,1,removed)>=0);}
 assert(cache.count==20 && e1_peer_access(&cache,broadcast.mac,200,0,removed)==0);
 e1_peer_remove(&cache,next.mac);assert(cache.count<=20);
 e1_peer_cache identities={0};mid_id a={{2,1,0,0,0,5}},b={{2,2,0,0,0,5}};
 assert(e1_peer_access(&identities,a.mac,1,1,removed)==0);
 assert(e1_peer_access(&identities,b.mac,2,1,removed)==0 && identities.count==2);
 e1_peer_cache trial=identities;mid_id c={{2,3,0,0,0,5}};
 assert(e1_peer_access(&trial,c.mac,3,1,removed)==0 && identities.count==2 && trial.count==3);
 e1_peer_remove(&trial,c.mac);assert(trial.count==2);
 puts("PASS bounded relay dedup and distinct-origin collision key");return 0;
}
