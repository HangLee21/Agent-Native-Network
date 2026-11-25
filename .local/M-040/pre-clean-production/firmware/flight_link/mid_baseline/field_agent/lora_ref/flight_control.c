#include "flight_control.h"
#include <string.h>

static uint16_t get16(const uint8_t *p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static uint32_t get32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint64_t get64(const uint8_t *p){return (uint64_t)get32(p)|((uint64_t)get32(p+4)<<32);}
static void put16(uint8_t *p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
uint32_t fc_crc32(const uint8_t *p,size_t n){uint32_t crc=0xffffffffu;while(n--){crc^=*p++;for(unsigned i=0;i<8;i++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return ~crc;}
void fc_init(fc_state *s,const uint8_t mac[6],uint32_t boot){memset(s,0,sizeof(*s));memcpy(s->mac,mac,6);s->boot=boot;}
void fc_report_sent(fc_state *s,uint32_t seq,uint64_t sent_ms){if(!s||!seq)return;fc_report *r=&s->reports[s->report_next++%FC_REPORTS];*r=(fc_report){.seq=seq,.sent_ms=sent_ms,.used=1};}
int fc_receive(fc_state *s,const uint8_t *b,size_t len,uint64_t now,uint32_t status,uint8_t out[FC_FRAME]){
    if(!s||!b||!out||len!=FC_FRAME||memcmp(b,"LRC2",4)||b[4]!=1||get16(b+6)!=FC_FRAME||memcmp(b+8,s->mac,6)||get16(b+14)||get32(b+40)||get32(b+44)!=fc_crc32(b,44)){if(s)__atomic_fetch_add(&s->rejected,1,__ATOMIC_RELAXED);return 0;}
    uint8_t op=b[5];uint32_t boot=get32(b+16),report=get32(b+20),ttl=get32(b+32),arg=get32(b+36);uint64_t id=get64(b+24),sent=0;int found=0;
    if((op!=1&&op!=2)||(op==2&&arg)||!boot||boot!=s->boot||!report||!id||ttl<1000||ttl>60000){__atomic_fetch_add(&s->rejected,1,__ATOMIC_RELAXED);return 0;}
    for(unsigned i=0;i<FC_REPORTS;i++)if(s->reports[i].used&&s->reports[i].seq==report){sent=s->reports[i].sent_ms;found=1;break;}
    if(!found||now<sent||now-sent>ttl){__atomic_fetch_add(&s->rejected,1,__ATOMIC_RELAXED);return 0;}
    fc_entry *free_entry=NULL;
    for(unsigned i=0;i<FC_SEEN;i++){
        fc_entry *e=&s->entries[i];
        if(e->used&&now>e->expires_ms)e->used=0;
        if(e->used&&get64(e->request+24)==id){
            if(memcmp(e->request,b,44)){__atomic_fetch_add(&s->rejected,1,__ATOMIC_RELAXED);return 0;}
            memcpy(out,e->response,FC_FRAME);put16(out+14,1);put32(out+40,(uint32_t)now);put32(out+44,fc_crc32(out,44));__atomic_fetch_add(&s->duplicates,1,__ATOMIC_RELAXED);return 2;
        }
        if(!e->used&&!free_entry)free_entry=e;
    }
    if(!free_entry){__atomic_fetch_add(&s->full,1,__ATOMIC_RELAXED);return 0;}
    memset(out,0,FC_FRAME);memcpy(out,"LRA2",4);out[4]=1;out[5]=op;put16(out+6,FC_FRAME);memcpy(out+8,s->mac,6);put32(out+16,s->boot);put32(out+20,report);memcpy(out+24,b+24,8);put32(out+32,2);put32(out+36,op==1?arg:(status&3u));put32(out+40,(uint32_t)now);put32(out+44,fc_crc32(out,44));
    free_entry->used=1;memcpy(free_entry->request,b,44);memcpy(free_entry->response,out,FC_FRAME);free_entry->expires_ms=sent+ttl;__atomic_fetch_add(&s->executed,1,__ATOMIC_RELAXED);return 1;
}
