#include "reliable.h"
#include "lora_ref/flight_control.h"
#include <string.h>
static uint16_t r16(const uint8_t*p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static uint32_t r32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void w16(uint8_t*p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void w32(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static int unicast(const uint8_t*p){unsigned nz=0;for(unsigned i=0;i<6;i++)nz|=p[i];return nz&&!(p[0]&1);}
static size_t encode(uint8_t*out,unsigned kind,const uint8_t src[6],const uint8_t dst[6],uint32_t boot,uint32_t db,uint32_t id,const uint8_t*payload,size_t len){size_t total=FR_HEADER+len+FR_CRC;memset(out,0,total);memcpy(out,"FLW2",4);out[4]=1;out[5]=(uint8_t)kind;w16(out+6,(uint16_t)total);w32(out+8,boot);w32(out+12,id);w32(out+16,db);memcpy(out+20,src,6);memcpy(out+26,dst,6);if(len)memcpy(out+FR_HEADER,payload,len);w32(out+total-4,fc_crc32(out,total-4));return total;}
void fr_init(fr_state*s,const uint8_t self[6],uint32_t boot){memset(s,0,sizeof(*s));memcpy(s->self,self,6);s->boot=boot;}
int fr_start(fr_state*s,const uint8_t dst[6],uint32_t db,const uint8_t*payload,size_t len,uint64_t now,uint32_t*id){if(!s||!dst||!id||!s->boot||!db||!unicast(dst)||!memcmp(dst,s->self,6)||len>FR_MAX_PAYLOAD||(!payload&&len)||s->next_id==UINT32_MAX){if(s)s->rejected++;return -1;}for(unsigned i=0;i<FR_PENDING;i++)if(!s->pending[i].used){fr_pending*p=&s->pending[i];memset(p,0,sizeof(*p));p->used=1;memcpy(p->dst,dst,6);p->dst_boot=db;p->id=++s->next_id;p->len=(uint8_t)len;if(len)memcpy(p->payload,payload,len);p->due=now;p->deadline=now+FR_LIFETIME_MS;*id=p->id;return 0;}s->rejected++;return -1;}
void fr_tick(fr_state*s,uint64_t now,fr_send_fn send,fr_timeout_fn timeout,void*ctx){if(!s||!send)return;for(unsigned i=0;i<FR_PENDING;i++){fr_pending*p=&s->pending[i];if(!p->used||now<p->due)continue;if(now>=p->deadline||p->attempts>=3){fr_message m={.origin_boot=s->boot,.dst_boot=p->dst_boot,.id=p->id,.len=p->len,.submissions=p->attempts,.local_rejections=p->local_rejections};memcpy(m.src,s->self,6);memcpy(m.dst,p->dst,6);if(p->len)memcpy(m.payload,p->payload,p->len);p->used=0;s->timeouts++;if(timeout)timeout(ctx,&m);return;}uint8_t wire[160];size_t n=encode(wire,1,s->self,p->dst,s->boot,p->dst_boot,p->id,p->payload,p->len);if(!send(ctx,p->dst,wire,n)){p->attempts++;p->due=now+FR_RETRY_MS;}else{if(p->local_rejections<255)p->local_rejections++;s->local_submit_failures++;p->due=now+FR_LOCAL_RETRY_MS;}if(p->due>p->deadline)p->due=p->deadline;return;}}
int fr_receive(fr_state*s,const uint8_t outer[6],uint32_t outer_boot,const uint8_t*b,size_t len,uint64_t now,fr_message*m,uint8_t ack[160],size_t*ack_len){
 if(!s||!outer||!b||!m||!ack||!ack_len)return -1;
 *ack_len=0;
 if(len<4||memcmp(b,"FLW2",4))return 0;
 if(len<FR_HEADER+FR_CRC||len>160||b[4]!=1||(b[5]!=1&&b[5]!=2)||r16(b+6)!=len||r32(b+len-4)!=fc_crc32(b,len-4)){s->rejected++;return -1;}
 uint32_t boot=r32(b+8),id=r32(b+12),db=r32(b+16);const uint8_t*src=b+20,*dst=b+26;size_t payload_len=len-FR_HEADER-FR_CRC;
 if(!boot||!id||!db||!outer_boot||!unicast(src)||!unicast(dst)||!memcmp(src,dst,6)){s->rejected++;return -1;}
 memset(m,0,sizeof(*m));memcpy(m->src,src,6);memcpy(m->dst,dst,6);m->origin_boot=boot;m->dst_boot=db;m->id=id;m->len=(uint16_t)payload_len;if(payload_len)memcpy(m->payload,b+FR_HEADER,payload_len);
 if(b[5]==1){if(memcmp(dst,s->self,6)||memcmp(src,outer,6)||boot!=outer_boot||db!=s->boot){s->rejected++;return -1;}
  fr_seen*slot=NULL;for(unsigned i=0;i<FR_SEEN;i++){fr_seen*q=&s->seen[i];if(q->used&&now>=q->until)q->used=0;if(q->used&&q->origin_boot==boot&&q->id==id&&!memcmp(q->src,src,6)){if(q->len!=payload_len||memcmp(q->payload,b+FR_HEADER,payload_len)){s->rejected++;return -1;}s->duplicates++;*ack_len=encode(ack,2,src,dst,boot,db,id,NULL,0);return 2;}if(!q->used&&!slot)slot=q;}
  if(!slot){s->seen_full++;return -1;}slot->used=1;memcpy(slot->src,src,6);slot->origin_boot=boot;slot->id=id;slot->len=(uint8_t)payload_len;if(payload_len)memcpy(slot->payload,b+FR_HEADER,payload_len);slot->until=now+FR_SEEN_MS;*ack_len=encode(ack,2,src,dst,boot,db,id,NULL,0);return 1;
 }
 if(payload_len||memcmp(src,s->self,6)||memcmp(dst,outer,6)||boot!=s->boot||db!=outer_boot){s->rejected++;return -1;}
 for(unsigned i=0;i<FR_PENDING;i++){fr_pending*p=&s->pending[i];if(p->used&&p->id==id&&p->dst_boot==db&&!memcmp(p->dst,dst,6)){
#if MID_ROUTE_FEEDBACK
 m->route_seq=p->first_route_seq;
#endif
 p->used=0;s->delivered++;return 3;}}
 return 4;
}
