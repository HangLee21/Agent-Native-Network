#include "source_route.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static mid_id ids[5]={{{2,0,0,0,0,1}},{{2,0,0,0,0,2}},{{2,0,0,0,0,3}},{{2,0,0,0,0,4}},{{2,0,0,0,0,5}}};
static sr_node nodes[5];static int links[5][5];static uint64_t now;static unsigned delivered,frames;static uint8_t bytes[250];
static void events(unsigned at){sr_event e;while(sr_next_event(&nodes[at],&e)){printf("{\"node\":%u,\"at\":%llu,\"event\":%u,\"seq\":%u,\"request\":%u,\"path\":[",at,(unsigned long long)now,e.type,e.seq,e.request);for(unsigned i=0;i<e.path.n;i++)printf("%s%u",i?",":"",e.path.path[i].mac[5]);puts("]}");if(e.type==SR_DELIVERED){assert(at==2&&e.len==160);for(unsigned i=0;i<160;i++)assert(e.payload[i]==(uint8_t)(7*i));delivered++;}}}
static void pump(void){for(unsigned turn=0;turn<30;turn++){int any=0;for(unsigned i=0;i<5;i++){sr_out out;if(!sr_next_tx(&nodes[i],&out,now))continue;any=1;int len=sr_encode(&out.packet,bytes,sizeof(bytes));assert(len>=60&&len<=220);frames++;for(unsigned j=0;j<5;j++)if(links[i][j]&&(out.next.mac[0]==255||mid_equal(out.next,ids[j])))sr_receive(&nodes[j],ids[i],bytes,(size_t)len,now);sr_tx_result(&nodes[i],&out,1,now);}for(unsigned i=0;i<5;i++)events(i);if(!any)return;}assert(!"control did not quiesce");}
static void setup(void){memset(links,0,sizeof(links));for(unsigned i=0;i<5;i++)sr_init(&nodes[i],ids[i],100+i,27);now=0;}
static void edge(unsigned a,unsigned b,int live_edge){links[a][b]=links[b][a]=live_edge;sr_neighbor(&nodes[a],ids[b],100+b,live_edge);sr_neighbor(&nodes[b],ids[a],100+a,live_edge);}
static void reply(sr_node*n,unsigned via,uint64_t at){sr_packet p={.type=SR_RREP,.n=3,.index=0,.ttl=1,.group=27,.boot=n->boot,.seq=1,.request=1,.dst=ids[2],.path={ids[0],ids[via],ids[2]}};int len=sr_encode(&p,bytes,sizeof(bytes));assert(len==60);assert(!sr_receive(n,ids[via],bytes,(size_t)len,at));}
int main(void){
 uint8_t payload[160];for(unsigned i=0;i<160;i++)payload[i]=(uint8_t)(7*i);
 for(unsigned order=0;order<2;order++){
  setup();edge(0,1,1);edge(0,3,1);assert(!sr_submit(&nodes[0],ids[2],1,payload,160,0));
  sr_out discard;assert(sr_next_tx(&nodes[0],&discard,0));
  reply(&nodes[0],order?1:3,100);reply(&nodes[0],order?3:1,150);sr_tick(&nodes[0],300);
  sr_out data;assert(sr_next_tx(&nodes[0],&data,300)&&data.packet.type==SR_DATA&&mid_equal(data.next,ids[1]));assert(data.packet.len==160);
  printf("ORDER %u chose A-B-C; close=300ms\n",order);
 }
 setup();edge(0,1,1);edge(1,2,1);edge(0,3,1);edge(3,2,1);
 assert(!sr_submit(&nodes[0],ids[2],1,payload,160,now));assert(!sr_submit(&nodes[0],ids[2],2,payload,160,now));assert(nodes[0].request_seq==1);pump();now=200;pump();assert(delivered==2);assert(mid_equal(nodes[0].routes[0].path.path[1],ids[1]));
 edge(0,1,0);edge(1,2,0);now=300;assert(!sr_submit(&nodes[0],ids[2],3,payload,160,now));pump();now=500;pump();assert(delivered==3);assert(mid_equal(nodes[0].routes[0].path.path[1],ids[3]));
 edge(0,3,0);edge(3,2,0);now=600;assert(!sr_submit(&nodes[0],ids[2],4,payload,160,now));pump();now=2100;pump();assert(delivered==3);for(unsigned i=0;i<SR_PENDING;i++)assert(!nodes[0].pending[i].used);
 assert(frames<100);printf("GRAPH delivery=3/4; fixed request windows; repair=A-D-C; unreachable terminated; frames=%u; sizeof(sr_node)=%lu\n",frames,(unsigned long)sizeof(sr_node));
 /* Full 4-hop payload encoding, duplicate endpoint and malformed loop/previous hop. */
 setup();edge(3,2,1);sr_packet p={.type=SR_DATA,.n=5,.index=4,.ttl=1,.group=27,.boot=100,.seq=7,.request=1,.dst=ids[2],.path={ids[0],ids[1],ids[4],ids[3],ids[2]},.len=160};memcpy(p.payload,payload,160);
 int len=sr_encode(&p,bytes,sizeof(bytes));assert(len==220);assert(!sr_receive(&nodes[2],ids[3],bytes,(size_t)len,0));assert(!sr_receive(&nodes[2],ids[3],bytes,(size_t)len,1));sr_event e;assert(sr_next_event(&nodes[2],&e)&&e.type==SR_DELIVERED);assert(!sr_next_event(&nodes[2],&e));assert(sr_receive(&nodes[2],ids[0],bytes,(size_t)len,1)<0);p.path[2]=ids[0];assert(sr_encode(&p,bytes,sizeof(bytes))<0);
 setup();edge(0,1,1);assert(!sr_submit(&nodes[0],ids[1],8,payload,160,0));sr_neighbor(&nodes[0],ids[1],999,1);sr_out out;assert(!sr_next_tx(&nodes[0],&out,0)); /* bound packet not sent after reboot */
 /* Matching downstream error invalidates only the original cached route. No replay of unknown packet. */
 setup();edge(0,1,1);edge(1,2,1);edge(0,3,1);edge(3,2,1);unsigned before=delivered;
 assert(!sr_submit(&nodes[0],ids[2],10,payload,160,0));pump();now=200;pump();assert(delivered==before+1);
 edge(1,2,0);now=300;assert(!sr_submit(&nodes[0],ids[2],11,payload,160,now));pump();assert(delivered==before+1);assert(!nodes[0].routes[0].used);
 now=400;assert(!sr_submit(&nodes[0],ids[2],12,payload,160,now));pump();now=600;pump();assert(delivered==before+2);assert(mid_equal(nodes[0].routes[0].path.path[1],ids[3]));
 puts("PASS downstream ERROR correlated to cached path/round; unknown packet11 not resent; new packet12 repaired");
 /* Lost feedback cannot keep a bad cache forever. */
 setup();edge(0,1,1);edge(1,2,1);edge(0,3,1);edge(3,2,1);before=delivered;
 assert(!sr_submit(&nodes[0],ids[2],20,payload,160,0));pump();now=200;pump();edge(1,2,0);links[1][0]=0;
 now=300;assert(!sr_submit(&nodes[0],ids[2],21,payload,160,now));pump();assert(nodes[0].routes[0].used&&delivered==before+1);
 now=10200;assert(!sr_submit(&nodes[0],ids[2],22,payload,160,now));pump();now=10400;pump();assert(delivered==before+2);
 puts("PASS lost ERROR bounded by10s cache expiry; later new packet22 repaired");
 /* Pending table bound and explicit stop cancellation. */
 setup();for(unsigned i=1;i<=8;i++)assert(!sr_submit(&nodes[0],ids[2],i,payload,160,0));assert(sr_submit(&nodes[0],ids[2],9,payload,160,0)<0);assert(nodes[0].request_seq==1);sr_stop(&nodes[0]);assert(!nodes[0].count);for(unsigned i=0;i<SR_PENDING;i++)assert(!nodes[0].pending[i].used);
 /* Arrival exactly at close cannot alter the candidate set, nor can a stale round/boot. */
 setup();edge(0,1,1);edge(0,3,1);assert(!sr_submit(&nodes[0],ids[2],30,payload,160,0));assert(sr_next_tx(&nodes[0],&out,0));reply(&nodes[0],3,100);
 sr_packet late={.type=SR_RREP,.n=3,.index=0,.ttl=1,.group=27,.boot=100,.seq=1,.request=1,.dst=ids[2],.path={ids[0],ids[1],ids[2]}};len=sr_encode(&late,bytes,sizeof(bytes));assert(sr_receive(&nodes[0],ids[1],bytes,(size_t)len,300)<0);assert(sr_next_tx(&nodes[0],&out,300)&&mid_equal(out.next,ids[3]));
 /* Wire integer/length checks, nonzero unused path slots and no truncation. */
 p=(sr_packet){.type=SR_DATA,.n=2,.index=1,.ttl=1,.group=27,.boot=100,.seq=90,.request=90,.dst=ids[1],.path={ids[0],ids[1]},.len=160};memcpy(p.payload,payload,160);len=sr_encode(&p,bytes,sizeof(bytes));assert(len==220);sr_packet decoded;assert(!sr_decode(&decoded,bytes,(size_t)len));assert(!memcmp(decoded.payload,payload,160));bytes[59]=1;assert(sr_decode(&decoded,bytes,(size_t)len)<0);p.len=161;assert(sr_encode(&p,bytes,sizeof(bytes))<0);
 puts("PASS deterministic candidates, graph discovery/repair/no-route, 160B/4-hop, loop/previous-hop, duplicate, next-hop reboot");
 return 0;
}
