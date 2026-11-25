#include "aodv.h"
#include <stdlib.h>
void *host_new(unsigned id,int policy){ma_node*n;if(id>=MA_NODES)return NULL;n=(ma_node*)calloc(1,sizeof(*n));if(n)ma_init(n,id,(unsigned)policy);return n;}
void host_free(void*p){free(p);}
void host_tick(void*p,uint64_t t){ma_tick(p,t);}
void host_sync(void*p,uint64_t t){(void)p;(void)t;}
void host_sync_unlimited(void*p,uint64_t t){(void)p;(void)t;}
void host_sync_changed(void*p,uint64_t t){(void)p;(void)t;}
unsigned host_service_flags(void*p,uint64_t t){ma_node*n=p;ma_tick(n,t);return (n->en?1u:0u)|(n->qn?2u:0u);}
int host_hello(void*p,uint8_t*b){(void)p;(void)b;return 0;}
int host_nd(void*p,unsigned src,const uint8_t*b,unsigned len,uint64_t t,uint8_t*reply){(void)p;(void)src;(void)b;(void)len;(void)t;(void)reply;return -1;}
int host_peer_access(void*p,int dst,uint64_t t){return ma_peer(p,dst,t);}
int host_peer_state(void*p,unsigned id){(void)p;(void)id;return -1;}
int host_submit(void*p,unsigned dst,uint32_t seq,const uint8_t*b,unsigned len,uint64_t t){return ma_submit(p,dst,seq,b,len,t);}
int host_next(void*p,uint64_t t,uint8_t*b,int*dst,int*type){(void)t;return ma_next(p,b,dst,type);}
void host_result(void*p,int ok,uint64_t t){ma_result(p,ok,t);}
int host_receive(void*p,unsigned src,const uint8_t*b,unsigned len,uint64_t t){return ma_receive(p,src,b,len,t);}
int host_event(void*p,unsigned*out,uint8_t*payload){return ma_event_next(p,out,payload);}
void host_stats(void*p,unsigned*out){ma_node*n=p;out[0]=n->overflow;out[1]=n->denied;out[2]=n->rejected;out[3]=n->event_overflow;out[4]=0;out[5]=0;out[6]=n->pending_high;out[7]=n->tx_high;}

void host_extended(void*p,unsigned*out){ma_node*n=p;out[0]=n->tx_overflow;out[1]=n->seen_overflow;out[2]=n->rreq_rx;out[3]=n->rreq_duplicates;out[4]=n->rreq_forward;out[5]=n->rrep_dest;out[6]=n->rrep_intermediate;out[7]=n->rerr_issued;}

void host_extended2(void*p,unsigned*out){ma_node*n=p;out[0]=n->forward_suppressed;}
