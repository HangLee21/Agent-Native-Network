#include "mid.h"
#include <string.h>
static uint16_t r16(const uint8_t *p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static uint32_t r32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void w16(uint8_t*p,uint16_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void w32(uint8_t*p,uint32_t x){unsigned i;for(i=0;i<4;i++)p[i]=(uint8_t)(x>>(i*8));}
int mid_equal(mid_id a,mid_id b){return memcmp(a.mac,b.mac,6)==0;}
int mid_unicast(mid_id id){static const uint8_t zero[6]={0};return !(id.mac[0]&1)&&memcmp(id.mac,zero,6)!=0;}
int mid_encode(const mid_packet*p,uint8_t*out,size_t cap){
 size_t len=MID_HEADER+p->size;
 if(p->size>sizeof(p->body)||cap<len||p->ttl<1||p->ttl>8||(p->kind!=1&&p->kind!=2)||!mid_unicast(p->origin)||!p->boot||!p->seq)return -1;
 memcpy(out,"MID1",4);out[4]=p->kind;out[5]=p->ttl;w16(out+6,p->size);memcpy(out+8,p->origin.mac,6);w32(out+14,p->boot);w32(out+18,p->seq);out[22]=out[23]=0;memcpy(out+24,p->body,p->size);return (int)len;
}
int mid_decode(mid_packet*p,const uint8_t*in,size_t len){
 mid_packet tmp={0};
 if(len<24||len>250||memcmp(in,"MID1",4)||in[22]||in[23])return -1;
 tmp.kind=in[4];tmp.ttl=in[5];tmp.size=r16(in+6);memcpy(tmp.origin.mac,in+8,6);tmp.boot=r32(in+14);tmp.seq=r32(in+18);
 if(tmp.size!=len-24||tmp.ttl<1||tmp.ttl>8||(tmp.kind!=1&&tmp.kind!=2)||!mid_unicast(tmp.origin)||!tmp.boot||!tmp.seq)return -1;
 memcpy(tmp.body,in+24,tmp.size);*p=tmp;return 0;
}
static int valid(const mid_table*t){
 unsigned f,i,j;uint32_t sum;
 if(t->n<2||t->n>5||t->k<1||t->k>2)return 0;
 for(i=0;i<t->n;i++){if(!mid_unicast(t->nodes[i]))return 0;for(j=0;j<i;j++)if(mid_equal(t->nodes[i],t->nodes[j]))return 0;}
 for(f=0;f<t->k;f++){
  if(t->src[f]>=t->n||t->dst[f]>=t->n||t->src[f]==t->dst[f])return 0;
  for(i=0;i<f;i++)if(t->src[f]==t->src[i]&&t->dst[f]==t->dst[i])return 0;
  for(i=0;i<t->n;i++){sum=0;for(j=0;j<t->n;j++){uint16_t w=t->w[f][i][j];if(w&&(i==j||i==t->dst[f]))return 0;sum+=w;}if(sum&&sum!=65535)return 0;}
 }
 return 1;
}
int mid_table_encode(const mid_table*t,uint8_t*out,size_t cap){
 unsigned i,j,f;size_t pos=2,len=2+6*t->n+2*t->k+2*t->k*t->n*t->n;
 if(!valid(t)||cap<len)return -1;
 out[0]=t->n;out[1]=t->k;
 for(i=0;i<t->n;i++){memcpy(out+pos,t->nodes[i].mac,6);pos+=6;}
 for(f=0;f<t->k;f++){out[pos++]=t->src[f];out[pos++]=t->dst[f];}
 for(f=0;f<t->k;f++)for(i=0;i<t->n;i++)for(j=0;j<t->n;j++){w16(out+pos,t->w[f][i][j]);pos+=2;}
 return (int)pos;
}
int mid_table_decode(mid_table*t,const uint8_t*in,size_t len){
 mid_table tmp={0};unsigned i,j,f;size_t pos=2;
 if(len<2)return -1;
 tmp.n=in[0];tmp.k=in[1];
 if(tmp.n<2||tmp.n>5||tmp.k<1||tmp.k>2||len!=2u+6u*tmp.n+2u*tmp.k+2u*tmp.k*tmp.n*tmp.n)return -1;
 for(i=0;i<tmp.n;i++){memcpy(tmp.nodes[i].mac,in+pos,6);pos+=6;}
 for(f=0;f<tmp.k;f++){tmp.src[f]=in[pos++];tmp.dst[f]=in[pos++];}
 for(f=0;f<tmp.k;f++)for(i=0;i<tmp.n;i++)for(j=0;j<tmp.n;j++){tmp.w[f][i][j]=r16(in+pos);pos+=2;}
 if(!valid(&tmp))return -1;
 *t=tmp;return 0;
}
void mid_init(mid_node*n,mid_id self,mid_id publisher,uint32_t boot){unsigned f;memset(n,0,sizeof(*n));n->self=self;n->publisher=publisher;n->publisher_boot=boot;for(f=0;f<MID_F;f++)n->next[f]=-1;}
static int index_of(const mid_table*t,mid_id id){unsigned i;for(i=0;i<t->n;i++)if(mid_equal(t->nodes[i],id))return (int)i;return -1;}
int mid_config(mid_node*n,const mid_packet*p){
 mid_table t;unsigned f;
 if(p->kind!=1||!mid_equal(p->origin,n->publisher)||p->boot!=n->publisher_boot||!p->seq||mid_table_decode(&t,p->body,p->size)||index_of(&t,n->self)<0)return -1;
 if(n->have_seq&&p->seq<=n->config_seq)return 0;
 n->table=t;n->config_seq=p->seq;n->have_seq=n->have_table=1;
 /* No forwarding on a stale choice while the new table waits for next period. */
 for(f=0;f<MID_F;f++)n->next[f]=-1;
 return 1;
}
int mid_tick(mid_node*n,uint64_t now,const uint16_t draw[MID_F]){
 unsigned f,j;int i;
 if(!n->have_table||(n->ticked&&now-n->last_tick<500))return 0;
 for(f=0;f<n->table.k;f++)if(draw[f]>=65535)return -1;
 n->last_tick=now;n->ticked=1;i=index_of(&n->table,n->self);
 for(f=0;f<n->table.k;f++){uint32_t sum=0;n->next[f]=-1;for(j=0;j<n->table.n;j++){sum+=n->table.w[f][i][j];if(draw[f]<sum){n->next[f]=(int)j;break;}}}
 return 1;
}
int mid_data(mid_node*n,const mid_packet*p,mid_id*next){
 unsigned i,f;mid_id dst;int result=-1;
 if(!n->have_table||p->kind!=2||!p->boot||!p->seq||p->ttl<1||p->ttl>8||p->size<6||p->size>6+MID_PAYLOAD)return -1;
 memcpy(dst.mac,p->body,6);
 for(f=0;f<n->table.k;f++)if(mid_equal(n->table.nodes[n->table.src[f]],p->origin)&&mid_equal(n->table.nodes[n->table.dst[f]],dst)){
  if(mid_equal(n->self,dst))result=2;
  else if(n->next[f]>=0&&p->ttl>1){*next=n->table.nodes[n->next[f]];result=1;}
  break;
 }
 if(result<0)return -1;
 for(i=0;i<64;i++)if(n->seen[i].used&&mid_equal(n->seen[i].origin,p->origin)&&n->seen[i].boot==p->boot&&n->seen[i].seq==p->seq)return 0;
 n->seen[n->cursor]=(mid_seen){p->origin,p->boot,p->seq,1};n->cursor=(n->cursor+1)%64;return result;
}
