/* Actual SR/FLW2 cores, deterministic 4-node event model, no RF. */
#include <source_route.h>
#include <reliable.h>
#ifndef HISTORICAL
#include <reliable_route.h>
#endif
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static mid_id id[4]={{{2,0,0,0,0,1}},{{2,0,0,0,0,2}},{{2,0,0,0,0,3}},{{2,0,0,0,0,4}}};
static sr_node n[4];static fr_state fr[4];static int link[4][4];static unsigned seq[4],rx,acknowledged,timeouts,rerr_lost,ack_lost,cache_retained;static uint64_t now,ack_at,acked[4];static int scenario;
static void edge(unsigned a,unsigned b,int live){link[a][b]=link[b][a]=live;sr_neighbor(&n[a],id[b],100+b,live);sr_neighbor(&n[b],id[a],100+a,live);}
static int submit(void*ctx,const uint8_t dst[6],const uint8_t*b,size_t len){unsigned i=*(unsigned*)ctx;mid_id d;memcpy(d.mac,dst,6);
#ifndef HISTORICAL
 fr_route_before(&fr[i],&n[i],b,len,now);
#endif
 uint32_t q=++seq[i];int r=sr_submit(&n[i],d,q,b,len,now);
#ifndef HISTORICAL
 if(!r)fr_route_submitted(&fr[i],b,len,q);
#endif
 return r;}
static void timeout(void*ctx,const fr_message*m){(void)ctx;(void)m;timeouts++;}
static void events(unsigned i){sr_event e;while(sr_next_event(&n[i],&e))if(e.type==SR_DELIVERED&&e.len>=4&&!memcmp(e.payload,"FLW2",4)){fr_message m;uint8_t a[160];size_t z=0;int r=fr_receive(&fr[i],e.origin.mac,e.boot,e.payload,e.len,now,&m,a,&z);if(r==1)rx++;if(r==1||r==2){mid_id d=e.origin;assert(!sr_submit(&n[i],d,++seq[i],a,z,now));}if(r==3){
#if MID_ROUTE_FEEDBACK && !defined(HISTORICAL)
 if(m.route_seq)sr_confirmed(&n[i],m.route_seq,now);
#endif
 acknowledged++;ack_at=now;if(m.id<=3)acked[m.id]=now;}}}
static void pump(void){for(unsigned turns=0;turns<100;turns++){int progress=0;for(unsigned i=0;i<4;i++){sr_out out;if(!sr_next_tx(&n[i],&out,now))continue;progress=1;uint8_t wire[250];int len=sr_encode(&out.packet,wire,sizeof(wire));assert(len>0);int drop=0;if((scenario==1||scenario==4)&&sr_base_type(out.packet.type)==SR_ERROR){drop=1;rerr_lost++;}if((scenario==2&&ack_lost<2)||(scenario==5&&now<2800)){if(sr_base_type(out.packet.type)==SR_DATA&&out.packet.len>=36&&!memcmp(out.packet.payload,"FLW2",4)&&out.packet.payload[5]==2){drop=1;ack_lost++;}}int unicast=out.next.mac[0]!=255;int delivered_link=0;for(unsigned j=0;j<4;j++)if(link[i][j]&&(!unicast||mid_equal(out.next,id[j]))){delivered_link=1;if(!drop)(void)sr_receive(&n[j],id[i],wire,(size_t)len,now);}sr_tx_result(&n[i],&out,!unicast||delivered_link,now);}for(unsigned i=0;i<4;i++)events(i);if(!progress)return;}assert(!"pump did not quiesce");}
int main(int argc,char**argv){scenario=argc>1?atoi(argv[1]):1;for(unsigned i=0;i<4;i++){sr_init(&n[i],id[i],100+i,27);fr_init(&fr[i],id[i].mac,100+i);}edge(0,1,1);edge(1,2,1);edge(0,3,1);edge(3,2,1);
 uint8_t warm=42;assert(!sr_submit(&n[0],id[2],++seq[0],&warm,1,0));unsigned src=0;
 for(now=0;now<=4700;now+=10){if(now==400&&(scenario==0||scenario==1||scenario==4)){edge(1,2,0);if(scenario==4)edge(3,2,0);}if(now==410&&scenario!=4)assert(!sr_submit(&n[2],id[0],++seq[2],&warm,1,now));if(now==800||now==1900||now==3000){if(now==800&&scenario==3)fr_init(&fr[2],id[2].mac,999);uint32_t msg;assert(!fr_start(&fr[0],id[2].mac,102,(const uint8_t*)"abc",3,now,&msg));}fr_tick(&fr[0],now,submit,timeout,&src);for(unsigned i=0;i<4;i++)sr_tick(&n[i],now);pump();if(now==2650&&scenario==5)for(unsigned k=0;k<SR_ROUTES;k++)if(n[0].routes[k].used&&mid_equal(n[0].routes[k].dst,id[2]))cache_retained=1;}
 unsigned controls=0,data=0;for(unsigned i=0;i<4;i++){controls+=n[i].control_frames;data+=n[i].data_frames;}
#if MID_ROUTE_FEEDBACK && !defined(HISTORICAL)
 unsigned probes=n[0].unconfirmed_probes;
#else
 unsigned probes=0;
#endif
 printf("{\"case\":%d,\"received\":%u,\"confirmed\":%u,\"timeout_unknown\":%u,\"first_confirmed_ms\":%llu,\"second_confirmed_ms\":%llu,\"third_confirmed_ms\":%llu,\"last_confirmation_ms\":%llu,\"rerr_dropped\":%u,\"ack_dropped\":%u,\"control_frames\":%u,\"data_frames\":%u,\"feedback_probes\":%u,\"cache_retained_during_probe\":%u}\n",scenario,rx,acknowledged,timeouts,(unsigned long long)(acked[1]?acked[1]-800:0),(unsigned long long)(acked[2]?acked[2]-1900:0),(unsigned long long)(acked[3]?acked[3]-3000:0),(unsigned long long)ack_at,rerr_lost,ack_lost,controls,data,probes,cache_retained);return 0;}
