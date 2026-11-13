#include "neighbors.h"
#include <string.h>
static uint32_t get(const uint8_t*p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put(uint8_t*p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
void nd_init(nd_node*n,mid_id self,uint32_t boot,uint32_t group){memset(n,0,sizeof(*n));n->self=self;n->boot=boot;n->group=group;}
static void control(nd_node*n,mid_packet*p,uint8_t type,uint32_t seq,uint32_t target,uint32_t echo){
 memset(p,0,sizeof(*p));p->kind=1;p->ttl=1;p->origin=n->self;p->boot=n->boot;p->seq=seq;p->size=17;
 memcpy(p->body,"ND01",4);put(p->body+4,n->group);p->body[8]=type;put(p->body+9,target);put(p->body+13,echo);
}
void nd_hello(nd_node*n,mid_packet*p,uint32_t seq){control(n,p,1,seq,0,0);n->hello_seq[n->hello_cursor++%4]=seq;n->tx_hello++;}
nd_peer* nd_find(nd_node*n,mid_id id){for(unsigned i=0;i<ND_PEERS;i++)if(n->peers[i].used&&mid_equal(n->peers[i].id,id))return &n->peers[i];return NULL;}
int nd_state(nd_peer*p,uint64_t now){if(!p||!p->used||now-p->seen>=ND_LOST_MS)return 0;return p->confirmed&&now-p->ack<ND_CONFIRM_MS?2:1;}
int nd_direct(nd_node*n,mid_id id,uint32_t boot,uint64_t now){nd_peer*p=nd_find(n,id);return p&&(!boot||p->boot==boot)&&nd_state(p,now)==2;}
int nd_receive(nd_node*n,mid_id source,const mid_packet*p,uint64_t now,mid_packet*reply){
 if(p->kind!=1||p->ttl!=1||p->size!=17||memcmp(p->body,"ND01",4)||get(p->body+4)!=n->group||!mid_equal(source,p->origin)||mid_equal(source,n->self)||!mid_unicast(source)||!p->boot||!p->seq)goto invalid;
 unsigned type=p->body[8];uint32_t target=get(p->body+9),echo=get(p->body+13);
 if(type==1){if(target||echo)goto invalid;}
 else if(type==2){int match=0;if(target!=n->boot||!echo)goto invalid;for(unsigned i=0;i<4;i++)if(n->hello_seq[i]==echo)match=1;if(!match)goto invalid;}
 else goto invalid;
 nd_peer*peer=nd_find(n,source);
 if(!peer){for(unsigned i=0;i<ND_PEERS;i++)if(!n->peers[i].used){peer=&n->peers[i];break;}if(!peer){n->full++;return -1;}peer->used=1;peer->id=source;peer->boot=p->boot;}
 if(peer->boot!=p->boot){for(unsigned i=0;i<4;i++)if(peer->retired[i]==p->boot)goto invalid;peer->retired[peer->cursor++%4]=peer->boot;peer->boot=p->boot;peer->hello=0;peer->confirmed=0;peer->ack=0;}
 if(type==1){
  if(p->seq<=peer->hello)return 0;
  peer->hello=p->seq;peer->seen=now;n->rx_hello++;
  /* Suppress unbounded ACK bursts from a single source; normal HELLO interval >=2s. */
  if(peer->reply_at&&now-peer->reply_at<500)return 0;
  peer->reply_at=now;control(n,reply,2,p->seq,p->boot,p->seq);n->tx_ack++;return 1;
 }
 /* Each ACK can renew confirmation only once for a local HELLO challenge. */
 if(peer->confirmed&&echo<=peer->state)return 0;
 peer->state=echo;peer->seen=peer->ack=now;peer->confirmed=1;n->rx_ack++;return 0;
invalid:n->rejected++;return -1;
}
