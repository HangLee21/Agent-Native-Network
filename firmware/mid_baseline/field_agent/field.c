#include "field.h"
#include <string.h>
static uint32_t r32(const uint8_t*p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void w32(uint8_t*p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
int fa_config_valid(const fa_config*c){
 if(c->min_ms<2000||c->max_ms<c->min_ms||c->max_ms>3600000||!c->min_len||c->max_len<c->min_len||c->max_len>160||c->bytes>1||c->observed>1||c->start>1||c->roster_n>8||!c->segment||(c->checkpoint_s&&(c->checkpoint_s<60||c->checkpoint_s>3600)))return -1;
 for(unsigned i=0;i<c->roster_n;i++){if(!mid_unicast(c->roster[i]))return -1;for(unsigned j=0;j<i;j++)if(mid_equal(c->roster[i],c->roster[j]))return -1;}return 0;
}
int fa_config_encode(const fa_config*c,uint8_t*b,size_t cap){if(cap<72||fa_config_valid(c))return -1;memset(b,0,72);memcpy(b,"FA01",4);w32(b+4,c->min_ms);w32(b+8,c->max_ms);b[12]=c->min_len;b[13]=c->max_len;b[14]=c->bytes;b[15]=c->observed;b[16]=c->start;b[17]=c->roster_n;b[18]=(uint8_t)c->checkpoint_s;b[19]=(uint8_t)(c->checkpoint_s>>8);w32(b+20,c->segment);memcpy(b+24,c->roster,c->roster_n*sizeof(mid_id));return 72;}
int fa_config_decode(fa_config*c,const uint8_t*b,size_t len){if(len!=72||memcmp(b,"FA01",4)||b[17]>8)return -1;fa_config t={.min_ms=r32(b+4),.max_ms=r32(b+8),.min_len=b[12],.max_len=b[13],.bytes=b[14],.observed=b[15],.start=b[16],.roster_n=b[17],.checkpoint_s=(uint16_t)(b[18]|((uint16_t)b[19]<<8)),.segment=r32(b+20)};memcpy(t.roster,b+24,t.roster_n*sizeof(mid_id));for(unsigned i=24+6*t.roster_n;i<72;i++)if(b[i])return -1;if(fa_config_valid(&t))return -1;*c=t;return 0;}
void fa_init(fa_node*n){memset(n,0,sizeof(*n));}
static void schedule(fa_node*n,uint64_t now,fa_rng rng,void*arg){n->due=now+n->cfg.min_ms+rng(arg)%(n->cfg.max_ms-n->cfg.min_ms+1);}
void fa_resume(fa_node*n,uint64_t now,fa_rng rng,void*arg){if(n->configured){n->running=1;schedule(n,now,rng,arg);}}
void fa_apply(fa_node*n,const fa_config*c,uint64_t now,fa_rng rng,void*arg){if(n->cfg.segment!=c->segment)fa_mark(n,c->segment,NULL);n->cfg=*c;n->configured=1;n->running=c->start;schedule(n,now,rng,arg);}
int fa_next(fa_node*n,mid_id self,const mid_id*eligible,unsigned count,uint64_t now,fa_rng rng,void*arg,mid_id*dst,uint8_t*bytes,unsigned*len){
 if(!n->running||now<n->due)return 0;
 n->rounds++;schedule(n,now,rng,arg);mid_id choices[16];unsigned used=0;
 for(unsigned i=0;i<count&&used<16;i++)if(mid_unicast(eligible[i])&&!mid_equal(eligible[i],self)){int duplicate=0;for(unsigned j=0;j<used;j++)if(mid_equal(eligible[i],choices[j]))duplicate=1;if(!duplicate)choices[used++]=eligible[i];}
 if(!used){n->no_destination++;return 0;}*dst=choices[rng(arg)%used];unsigned maximum=n->cfg.max_len;if(dst->mac[0]==2&&dst->mac[1]==255&&maximum>128)maximum=128;if(n->cfg.min_len>maximum){n->rejected++;return 0;}*len=n->cfg.min_len+rng(arg)%(maximum-n->cfg.min_len+1);
 if(n->cfg.bytes){uint32_t bits=0;for(unsigned i=0;i<*len;i++){if(!(i%4))bits=rng(arg);bytes[i]=(uint8_t)(bits>>(8*(i%4)));}}
 else{static const char*const words[]={"Hello","mobile","radio","packet","travels","through","our","shared","network","today"};unsigned at=0;while(at<*len){const char*w=words[rng(arg)%10];for(unsigned i=0;w[i]&&at<*len;i++)bytes[at++]=(uint8_t)w[i];if(at<*len)bytes[at++]=' ';}}
 return 1;
}
int fa_log(fa_node*n,unsigned kind,mid_id origin,uint32_t boot,uint32_t seq,mid_id dst,const uint8_t*payload,unsigned len,uint64_t at){
 if(kind>=FA_KINDS||!mid_unicast(origin)||!boot||!seq||len>160)return -1;
 fa_seen*s=NULL;
 for(unsigned i=0;i<FA_ORIGINS;i++)if(n->seen[i].used&&mid_equal(n->seen[i].origin,origin)&&n->seen[i].boot==boot){s=&n->seen[i];break;}
 if(!s){for(unsigned i=0;i<FA_ORIGINS;i++)if(!n->seen[i].used){s=&n->seen[i];break;}}if(!s){n->origins_full++;return -1;}
 if(!s->used){s->used=1;s->origin=origin;s->boot=boot;}
 uint32_t hi=s->highest[kind];if(seq>hi){uint32_t delta=seq-hi;s->seen[kind]=delta>=64?1:(s->seen[kind]<<delta)|1;s->highest[kind]=seq;}else{uint32_t delta=hi-seq;if(delta>=64){n->late++;return -1;}uint64_t mask=(uint64_t)1<<delta;if(s->seen[kind]&mask)return 0;s->seen[kind]|=mask;}
 if(n->count==FA_RECORDS){n->head=(n->head+1)%FA_RECORDS;n->count--;n->overwritten++;}fa_record*r=&n->records[(n->head+n->count++)%FA_RECORDS];memset(r,0,sizeof(*r));r->origin=origin;r->dst=dst;r->boot=boot;r->seq=seq;r->segment=n->cfg.segment;r->kind=(uint8_t)kind;r->len=(uint8_t)len;r->cursor=++n->cursor;r->at=at;if(len)memcpy(r->payload,payload,len);n->totals[kind]++;n->segment_counts[kind]++;n->payload_bytes[kind]+=len;return 1;
}
void fa_mark(fa_node*n,uint32_t segment,const char*note){n->cfg.segment=segment;memset(n->segment_counts,0,sizeof(n->segment_counts));memset(n->note,0,sizeof(n->note));if(note){size_t len=strlen(note);if(len>31)len=31;memcpy(n->note,note,len);}}
const fa_record*fa_after(const fa_node*n,uint64_t after){for(unsigned i=0;i<n->count;i++){const fa_record*r=&n->records[(n->head+i)%FA_RECORDS];if(r->cursor>after)return r;}return NULL;}
