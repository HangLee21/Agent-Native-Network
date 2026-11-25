/* Host-only adapter to the actual frozen firmware ND and source-route core. */
#include "source_route.h"
#include "neighbors.h"
#include "peer_cache_mac.h"
#include "neighbor_sync.h"
#include <stdlib.h>
#include <string.h>
typedef struct {sr_node sr;nd_node nd;sr_out tx;mid_id id;uint32_t sequence,peer_capacity_samples;int policy;e1_peer_cache peer_cache;mid_id sync_id[ND_PEERS];uint32_t sync_boot[ND_PEERS];uint8_t sync_state[ND_PEERS],sync_used[ND_PEERS];} host_node;
static mid_id ident(unsigned id){mid_id x={{2,0,0,0,0,0}};x.mac[5]=(uint8_t)(id+1);return x;}
void *host_new(unsigned id,int policy){host_node*n=calloc(1,sizeof(*n));if(!n)return NULL;n->id=ident(id);n->policy=policy;sr_init(&n->sr,n->id,id+1,31);nd_init(&n->nd,n->id,id+1,31);return n;}
void host_free(void*p){free(p);}
void host_sync(void*p,uint64_t t){host_node*n=p;unsigned admitted=0;for(unsigned i=0;i<ND_PEERS;i++){nd_peer*q=&n->nd.peers[i];if(q->used){int live=nd_state(q,t)==2;if(live&&admitted++>=20){live=0;n->peer_capacity_samples++;}sr_neighbor(&n->sr,q->id,q->boot,live);}}}
void host_sync_unlimited(void*p,uint64_t t){host_node*n=p;if(n->policy&4)e1_clear_absent_neighbors(&n->sr,&n->nd);for(unsigned i=0;i<ND_PEERS;i++){nd_peer*q=&n->nd.peers[i];if(q->used)sr_neighbor(&n->sr,q->id,q->boot,nd_state(q,t)==2);}}
void host_sync_changed(void*p,uint64_t t){host_node*n=p;for(unsigned i=0;i<ND_PEERS;i++){nd_peer*q=&n->nd.peers[i];if(q->used){int live=nd_state(q,t)==2;if(!n->sync_used[i]||n->sync_boot[i]!=q->boot||n->sync_state[i]!=live||!mid_equal(n->sync_id[i],q->id)){if((n->policy&4)&&n->sync_used[i]&&!mid_equal(n->sync_id[i],q->id))e1_clear_absent_neighbors(&n->sr,&n->nd);sr_neighbor(&n->sr,q->id,q->boot,live);n->sync_used[i]=1;n->sync_boot[i]=q->boot;n->sync_state[i]=(uint8_t)live;n->sync_id[i]=q->id;}}}}
int host_peer_access(void*p,int dst,uint64_t t){host_node*n=p;uint8_t evicted[6];mid_id addr=dst<0?(mid_id){{255,255,255,255,255,255}}:ident((unsigned)dst);return e1_peer_access(&n->peer_cache,addr.mac,t,(n->policy&2)!=0,evicted);}
int host_peer_state(void*p,unsigned id){host_node*n=p;mid_id target=ident(id);for(unsigned i=0;i<SR_PEERS;i++)if(n->sr.peers[i].used&&mid_equal(n->sr.peers[i].id,target))return n->sr.peers[i].live;return -1;}
void host_tick(void*p,uint64_t t){host_node*n=p;sr_tick(&n->sr,t);}
unsigned host_service_flags(void*p,uint64_t t){host_node*n=p;sr_tick(&n->sr,t);return (n->sr.event_count?1u:0u)|(n->sr.count?2u:0u);}
int host_hello(void*p,uint8_t*b){host_node*n=p;mid_packet x;nd_hello(&n->nd,&x,++n->sequence);return mid_encode(&x,b,250);}
int host_nd(void*p,unsigned src,const uint8_t*b,unsigned len,uint64_t t,uint8_t*reply){host_node*n=p;mid_packet x,y;if(mid_decode(&x,b,len))return -1;int r=nd_receive(&n->nd,ident(src),&x,t,&y);return r==1?mid_encode(&y,reply,250):r;}
int host_submit(void*p,unsigned dst,uint32_t seq,const uint8_t*b,unsigned len,uint64_t t){return sr_submit(&((host_node*)p)->sr,ident(dst),seq,b,len,t);}
int host_next(void*p,uint64_t t,uint8_t*b,int*dest,int*type){host_node*n=p;if(!sr_next_tx(&n->sr,&n->tx,t))return 0;*dest=n->tx.next.mac[0]==255?-1:(int)n->tx.next.mac[5]-1;*type=sr_base_type(n->tx.packet.type);return sr_encode(&n->tx.packet,b,250);}
void host_result(void*p,int ok,uint64_t t){host_node*n=p;sr_tx_result(&n->sr,&n->tx,ok,t);}
int host_receive(void*p,unsigned src,const uint8_t*b,unsigned len,uint64_t t){return sr_receive(&((host_node*)p)->sr,ident(src),b,len,t);}
int host_event(void*p,unsigned*out,uint8_t*payload){sr_event e;if(!sr_next_event(&((host_node*)p)->sr,&e))return 0;out[0]=e.type;out[1]=e.reason;out[2]=e.origin.mac[5]-1;out[3]=e.boot;out[4]=e.seq;out[5]=e.dst.mac[5]-1;out[6]=e.request;out[7]=e.len;if(e.len)memcpy(payload,e.payload,e.len);return 1;}
void host_stats(void*p,unsigned*out){host_node*n=p;out[0]=n->sr.overflows;out[1]=n->sr.rreq_denied;out[2]=n->sr.rejected;out[3]=n->sr.event_overflows;out[4]=n->nd.full;out[5]=n->peer_capacity_samples;out[6]=n->sr.pending_high;out[7]=n->sr.out_high;}
void host_state(void*p,unsigned*out){host_node*n=p;memset(out,0,8*sizeof(*out));for(unsigned i=0;i<SR_PEERS;i++)out[0]+=(unsigned)(n->sr.peers[i].used&&n->sr.peers[i].live);for(unsigned i=0;i<SR_ROUTES;i++)out[1]+=(unsigned)n->sr.routes[i].used;for(unsigned i=0;i<SR_ROUNDS;i++)out[2]+=(unsigned)n->sr.rounds[i].used;for(unsigned i=0;i<SR_PENDING;i++)out[3]+=(unsigned)n->sr.pending[i].used;out[4]=n->sr.count;for(unsigned i=0;i<ND_PEERS;i++)out[5]+=(unsigned)n->nd.peers[i].used;out[6]=n->peer_cache.count;out[7]=n->sr.event_count;}
