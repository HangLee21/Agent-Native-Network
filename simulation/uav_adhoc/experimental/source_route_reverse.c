#include "source_route.h"
#include <string.h>
#ifndef ENGINEERING_RREQ_DEDUP
#define ENGINEERING_RREQ_DEDUP 0
#endif
#ifndef ENGINEERING_REVERSE_CACHE
#define ENGINEERING_REVERSE_CACHE 0
#endif
#define REVERSE_CACHE_MS 3000u
static uint32_t r32(const uint8_t*p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void w32(uint8_t*p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
static sr_path path_of(const sr_packet*p){sr_path r={0};r.n=p->n;memcpy(r.path,p->path,p->n*sizeof(mid_id));return r;}
static int same(sr_path a,sr_path b){return a.n==b.n&&!memcmp(a.path,b.path,a.n*sizeof(mid_id));}
static int better(sr_path a,sr_path b){return a.n<b.n||(a.n==b.n&&memcmp(a.path,b.path,a.n*sizeof(mid_id))<0);}
static int valid(const sr_packet*p){
 unsigned type=sr_base_type(p->type);int service=p->type>4;
 if(p->type<1||p->type>8||service!=sr_service_id(p->dst)||!p->group||!p->boot||!p->seq||!p->request||p->n<1||p->n>5||!mid_unicast(p->dst)||p->len>160)return 0;
 for(unsigned i=0;i<p->n;i++){if(!mid_unicast(p->path[i])||sr_service_id(p->path[i]))return 0;for(unsigned j=0;j<i;j++)if(mid_equal(p->path[i],p->path[j]))return 0;}
 if(type==SR_RREQ)return !p->len&&p->n<5&&p->index==p->n-1&&p->ttl==5-p->n&&p->seq==p->request;
 if(p->n<2||(!service&&!mid_equal(p->dst,p->path[p->n-1])))return 0;
 if(type==SR_DATA)return p->index>0&&p->index<p->n&&p->ttl==p->n-p->index;
 if(p->index>=p->n-1||p->ttl!=p->index+1)return 0;
 if(type==SR_RREP)return p->len==(service?8:0)&&p->seq==p->request;
 return p->len==1&&p->payload[0]<(unsigned)(p->n-(service?0:1))&&p->payload[0]>p->index;
}
int sr_encode(const sr_packet*p,uint8_t*b,size_t cap){
 if(!valid(p)||cap<(size_t)SR_HEADER+p->len)return -1;
 memset(b,0,SR_HEADER);memcpy(b,"SR01",4);w32(b+4,p->group);b[8]=p->type;b[9]=p->n;b[10]=p->index;b[11]=p->ttl;
 w32(b+12,p->boot);w32(b+16,p->seq);w32(b+20,p->request);memcpy(b+24,p->dst.mac,6);memcpy(b+30,p->path,p->n*sizeof(mid_id));memcpy(b+60,p->payload,p->len);return SR_HEADER+p->len;
}
int sr_decode(sr_packet*p,const uint8_t*b,size_t len){
 if(len<60||len>220||memcmp(b,"SR01",4))return -1;
 sr_packet t={.group=r32(b+4),.type=b[8],.n=b[9],.index=b[10],.ttl=b[11],.boot=r32(b+12),.seq=r32(b+16),.request=r32(b+20),.len=(uint16_t)(len-60)};
 if(t.n>5)return -1;
 memcpy(t.dst.mac,b+24,6);memcpy(t.path,b+30,t.n*sizeof(mid_id));for(unsigned i=30+6*t.n;i<60;i++)if(b[i])return -1;
 memcpy(t.payload,b+60,t.len);if(!valid(&t))return -1;*p=t;return 0;
}
static sr_peer* peer(sr_node*n,mid_id id){for(unsigned i=0;i<SR_PEERS;i++)if(n->peers[i].used&&mid_equal(n->peers[i].id,id))return &n->peers[i];return NULL;}
static int live(sr_node*n,mid_id id){sr_peer*p=peer(n,id);return p&&p->live;}
static void ev(sr_node*n,unsigned type,const sr_packet*p,unsigned reason){
 if(n->event_count==SR_EVENTS){n->event_overflows++;return;}
 sr_event*e=&n->events[(n->event_head+n->event_count++)%SR_EVENTS];memset(e,0,sizeof(*e));e->type=type;e->reason=reason;
 if(p){e->seq=p->seq;e->request=p->request;e->boot=p->boot;e->origin=p->path[0];e->dst=p->dst;e->path=path_of(p);if(type==SR_DELIVERED||type==SR_RELAY){e->len=p->len;memcpy(e->payload,p->payload,p->len);}}
}
static int queue(sr_node*n,sr_packet p,mid_id next){
 if(n->count==SR_OUT){n->overflows++;ev(n,SR_DROPPED,&p,1);return -1;}
 sr_peer*adjacent=peer(n,next);n->out[(n->head+n->count)%SR_OUT]=(sr_out){p,next,n->now,adjacent?adjacent->boot:0};n->count++;if(n->count>n->out_high)n->out_high=n->count;return 0;
}
void sr_init(sr_node*n,mid_id self,uint32_t boot,uint32_t group){memset(n,0,sizeof(*n));n->self=self;n->boot=boot;n->group=group;n->rreq_tokens=SR_RREQ_BURST;}
static void invalidate(sr_node*n,mid_id a,mid_id b){
 for(unsigned i=0;i<SR_ROUTES;i++){sr_route*r=&n->routes[i];if(!r->used)continue;for(unsigned j=1;j<r->path.n;j++)if(mid_equal(r->path.path[j-1],a)&&mid_equal(r->path.path[j],b)){r->used=0;sr_packet p={.n=r->path.n,.boot=n->boot,.request=r->request,.dst=r->dst};memcpy(p.path,r->path.path,sizeof(p.path));ev(n,SR_INVALIDATED,&p,2);break;}}
}
void sr_neighbor(sr_node*n,mid_id id,uint32_t boot,int is_live){
 sr_peer*p=peer(n,id);if(!p){for(unsigned i=0;i<SR_PEERS;i++)if(!n->peers[i].used){p=&n->peers[i];break;}}if(!p)return;
 if(p->used&&(!is_live||p->boot!=boot))invalidate(n,n->self,id);
 *p=(sr_peer){1,is_live,id,boot};
}
static sr_route* cached(sr_node*n,mid_id dst){sr_route*best=NULL;
 for(unsigned i=0;i<SR_ROUTES;i++){sr_route*r=&n->routes[i];if(!r->used||!mid_equal(r->dst,dst))continue;sr_peer*p=peer(n,r->path.path[1]);if(n->now>=r->until||!p||!p->live||p->boot!=r->first_boot){r->used=0;continue;}if(!best||better(r->path,best->path))best=r;}return best;
}
static sr_packet packet(sr_node*n,unsigned type,mid_id dst,uint32_t seq,uint32_t req){sr_packet p={.type=(uint8_t)(type+(sr_service_id(dst)?4:0)),.group=n->group,.boot=n->boot,.seq=seq,.request=req,.dst=dst};return p;}
/* Experimental: a received RREQ carries a locally observed reverse path.
 * No global graph, new frames or dynamic allocation. An existing usable route
 * is retained unless the newly observed path is strictly shorter/better. */
static void reverse_cache(sr_node*n,const sr_packet*p,mid_id previous){
 if(!ENGINEERING_REVERSE_CACHE||sr_service_id(p->dst)||p->n<2||n->request_seq==UINT32_MAX)return;
 mid_id dst=p->path[0];if(mid_equal(dst,n->self))return;
 sr_peer*first=peer(n,previous);if(!first||!first->live)return;
 sr_path path={0};path.n=p->n;for(unsigned i=0;i<p->n;i++)path.path[i]=p->path[p->n-1-i];
 sr_route*existing=cached(n,dst);if(existing&&!better(path,existing->path))return;
 sr_route*slot=existing;
 if(!slot)for(unsigned i=0;i<SR_ROUTES;i++)if(!n->routes[i].used||n->routes[i].until<=n->now){slot=&n->routes[i];break;}
 if(!slot)return;
 uint32_t request=++n->request_seq;
 *slot=(sr_route){.used=1,.dst=dst,.path=path,.request=request,.first_boot=first->boot,.until=n->now+REVERSE_CACHE_MS};
 sr_packet observed=packet(n,SR_RREQ,dst,request,request);observed.n=path.n;memcpy(observed.path,path.path,sizeof(observed.path));
 ev(n,SR_SELECTED,&observed,9); /* reason 9 = passive cache installation */
}
static int send_data(sr_node*n,sr_pending*m,sr_route*r){
 sr_packet p=packet(n,SR_DATA,m->dst,m->seq,r->request);p.n=r->path.n;memcpy(p.path,r->path.path,sizeof(p.path));p.index=1;p.ttl=p.n-1;p.len=m->len;memcpy(p.payload,m->payload,p.len);
 int result=queue(n,p,p.path[1]);if(result)ev(n,SR_UNKNOWN,&p,1);m->used=0;return result;
}
static void finish(sr_node*n,sr_round*r){
 sr_packet p=packet(n,SR_RREQ,r->dst,r->request,r->request);p.n=1;p.path[0]=n->self;
 sr_route*cache=NULL;
 if(r->count){
  sr_path best={0};for(unsigned i=0;i<r->count;i++)if(r->proof_until[i]>n->now&&live(n,r->candidates[i].path[1])&&(!best.n||better(r->candidates[i],best)))best=r->candidates[i];
  if(best.n){for(unsigned i=0;i<SR_ROUTES;i++)if(!n->routes[i].used||n->routes[i].until<=n->now||mid_equal(n->routes[i].dst,r->dst)){cache=&n->routes[i];break;}
   if(cache){*cache=(sr_route){.used=1,.dst=r->dst,.path=best,.request=r->request,.first_boot=peer(n,best.path[1])->boot,.until=n->now+SR_CACHE_MS};p.n=best.n;memcpy(p.path,best.path,sizeof(p.path));ev(n,SR_SELECTED,&p,0);}}
 }
 if(cache&&sr_service_id(r->dst)){
  for(unsigned j=0;j<SR_ROUTES;j++)if(n->routes[j].used&&mid_equal(n->routes[j].dst,r->dst))n->routes[j].used=0;
  cache=NULL;
  unsigned order[SR_CANDIDATES];for(unsigned i=0;i<r->count;i++)order[i]=i;for(unsigned i=0;i<r->count;i++)for(unsigned j=i+1;j<r->count;j++)if(better(r->candidates[order[j]],r->candidates[order[i]])){unsigned swap=order[i];order[i]=order[j];order[j]=swap;}
  for(unsigned k=0;k<r->count;k++){unsigned i=order[k];if(r->proof_until[i]<=n->now||!live(n,r->candidates[i].path[1]))continue;sr_route*slot=NULL;for(unsigned j=0;j<SR_ROUTES;j++)if(!n->routes[j].used||n->routes[j].until<=n->now){slot=&n->routes[j];break;}if(!slot)break;*slot=(sr_route){.used=1,.dst=r->dst,.path=r->candidates[i],.request=r->request,.first_boot=peer(n,r->candidates[i].path[1])->boot,.until=r->proof_until[i]};if(same(slot->path,path_of(&p)))cache=slot;}
 }
 if(!cache)ev(n,SR_NO_ROUTE,&p,3);
 for(unsigned i=0;i<SR_PENDING;i++)if(n->pending[i].used&&mid_equal(n->pending[i].dst,r->dst)){if(cache)send_data(n,&n->pending[i],cache);else{p.seq=n->pending[i].seq;ev(n,SR_NO_ROUTE,&p,3);n->pending[i].used=0;}}
 r->used=0;
}
/* Route-discovery token bucket. Refilled on a fixed grid so an idle node cannot
 * accumulate an unbounded burst. */
static int rreq_take(sr_node*n){
 if(!n->rreq_tokens){n->rreq_denied++;return 0;}
 n->rreq_tokens--;return 1;
}
void sr_tick(sr_node*n,uint64_t now){
 if(!n->rreq_refilled)n->rreq_refilled=now;
 if(now-n->rreq_refilled>=SR_RREQ_REFILL_MS*SR_RREQ_BURST){n->rreq_tokens=SR_RREQ_BURST;n->rreq_refilled=now;}
 else while(n->rreq_tokens<SR_RREQ_BURST&&now-n->rreq_refilled>=SR_RREQ_REFILL_MS){n->rreq_tokens++;n->rreq_refilled+=SR_RREQ_REFILL_MS;}
 n->now=now;for(unsigned i=0;i<SR_ROUNDS;i++){sr_round*r=&n->rounds[i];if(r->used&&(now>=r->deadline||(r->close&&now>=r->close)))finish(n,r);}
 for(unsigned i=0;i<SR_ROUTES;i++)if(n->routes[i].used&&now>=n->routes[i].until)n->routes[i].used=0;
}
int sr_submit(sr_node*n,mid_id dst,uint32_t seq,const uint8_t*data,size_t len,uint64_t now){
 sr_tick(n,now);if(!seq||!mid_unicast(dst)||mid_equal(dst,n->self)||len>160||(!data&&len))return -1;
 sr_pending*m=NULL;for(unsigned i=0;i<SR_PENDING;i++)if(!n->pending[i].used){m=&n->pending[i];break;}if(!m){n->overflows++;return -1;}
 sr_packet p=packet(n,SR_DATA,dst,seq,1);p.n=1;p.path[0]=n->self;
 *m=(sr_pending){.used=1,.dst=dst,.seq=seq,.len=(uint16_t)len};if(len)memcpy(m->payload,data,len);
 sr_route direct={.used=1,.dst=dst,.path={.n=2,.path={n->self,dst}},.request=seq};
 sr_route*r=live(n,dst)?&direct:cached(n,dst);
 if(r){if(send_data(n,m,r))return -1;ev(n,SR_ACCEPTED,&p,0);return 0;}
 sr_round*round=NULL;for(unsigned i=0;i<SR_ROUNDS;i++)if(n->rounds[i].used&&mid_equal(n->rounds[i].dst,dst)){round=&n->rounds[i];break;}
 if(!round){for(unsigned i=0;i<SR_ROUNDS;i++)if(!n->rounds[i].used){round=&n->rounds[i];break;}if(!round||n->request_seq==UINT32_MAX){m->used=0;n->overflows++;return -1;}
   if(!rreq_take(n)){m->used=0;return -1;}
  *round=(sr_round){.used=1,.dst=dst,.request=++n->request_seq,.deadline=now+SR_DEADLINE};p=packet(n,SR_RREQ,dst,round->request,round->request);p.n=1;p.path[0]=n->self;p.ttl=4;mid_id broadcast={{255,255,255,255,255,255}};
  if(queue(n,p,broadcast)){round->used=0;m->used=0;return -1;}ev(n,SR_REQUEST,&p,0);
 }
 p.seq=seq;p.request=round->request;ev(n,SR_ACCEPTED,&p,0);ev(n,SR_WAITING,&p,0);unsigned used=0;for(unsigned i=0;i<SR_PENDING;i++)used+=(unsigned)n->pending[i].used;if(used>n->pending_high)n->pending_high=used;return 0;
}
/* Returns 1 the first time this data seq fails locally, 0 afterwards. */
static int retried_take(sr_node*n,uint32_t seq){
 for(unsigned i=0;i<SR_PENDING;i++)if(n->retried[i]==seq)return 0;
 n->retried[n->retried_cursor++%SR_PENDING]=seq;return 1;
}
static void failed(sr_node*n,const sr_packet*data,unsigned edge){
 invalidate(n,data->path[edge],data->path[edge+1]);ev(n,SR_UNKNOWN,data,4);
 if(edge){sr_packet p=*data;p.type=sr_service_id(p.dst)?SR_SERR:SR_ERROR;p.index=(uint8_t)(edge-1);p.ttl=(uint8_t)edge;p.len=1;p.payload[0]=(uint8_t)edge;queue(n,p,p.path[p.index]);return;}
 /* Locally originated data that died on its own first edge is re-discovered once
  * instead of being dropped: the old path is already invalidated, so sr_submit
  * starts a fresh RREQ round and the packet waits in pending for the new path.
  * Bounded to one retry per packet identity, and only for local business data
  * (control frames and relayed packets keep their original behaviour). */
 if(sr_base_type(data->type)==SR_DATA&&mid_equal(data->path[0],n->self)&&retried_take(n,data->seq)){
  if(!sr_submit(n,data->dst,data->seq,data->payload,data->len,n->now))n->retries++;
 }
}
int sr_receive(sr_node*n,mid_id physical,const uint8_t*bytes,size_t len,uint64_t now){
 sr_tick(n,now);sr_packet p;if(sr_decode(&p,bytes,len)||p.group!=n->group||!live(n,physical))goto reject;
 if(mid_equal(physical,p.path[0])&&peer(n,physical)->boot!=p.boot)goto reject;
 if(sr_base_type(p.type)==SR_RREQ){
  if(!mid_equal(physical,p.path[p.n-1]))goto reject;
  for(unsigned i=0;i<p.n;i++)if(mid_equal(p.path[i],n->self))goto reject;
  sr_path old=path_of(&p);sr_seen*slot=NULL;
  for(unsigned i=0;i<SR_SEEN;i++){sr_seen*s=&n->seen[i];if(s->used&&s->until>now&&s->boot==p.boot&&s->request==p.request&&(same(s->path,old)||(ENGINEERING_RREQ_DEDUP&&!sr_service_id(p.dst)&&!mid_equal(p.dst,n->self)&&mid_equal(s->path.path[0],p.path[0]))))return 0;if(!s->used||s->until<=now)slot=s;}
  if(!slot){n->overflows++;goto reject;}*slot=(sr_seen){1,p.boot,p.request,old,now+5000};
  p.path[p.n++]=n->self;
  reverse_cache(n,&p,physical);
  if(mid_equal(p.dst,n->self)||(mid_equal(p.dst,n->service_id)&&n->service_until>now)){p.type=sr_service_id(p.dst)?SR_SREP:SR_RREP;if(p.type==SR_SREP){p.len=8;w32(p.payload,n->pc_session);uint64_t remaining=n->service_until-now;w32(p.payload+4,(uint32_t)(remaining>10000?10000:remaining));}p.index=p.n-2;p.ttl=p.index+1;return queue(n,p,p.path[p.index]);}
  if(p.n==5)return 0;
  p.index=p.n-1;p.ttl=5-p.n;mid_id broadcast={{255,255,255,255,255,255}};return queue(n,p,broadcast);
 }
 if(!mid_equal(p.path[p.index],n->self))goto reject;
 unsigned from=sr_base_type(p.type)==SR_DATA?p.index-1:p.index+1;if(!mid_equal(physical,p.path[from]))goto reject;
 if(sr_base_type(p.type)==SR_RREP){
  if(!p.index){if(p.boot!=n->boot)goto reject;
   sr_round*r=NULL;for(unsigned i=0;i<SR_ROUNDS;i++)if(n->rounds[i].used&&n->rounds[i].request==p.request&&mid_equal(n->rounds[i].dst,p.dst)){r=&n->rounds[i];break;}if(!r)goto reject;
   sr_path candidate=path_of(&p);for(unsigned i=0;i<r->count;i++)if(same(r->candidates[i],candidate))return 0;
   if(r->count==SR_CANDIDATES){n->overflows++;goto reject;}if(p.type==SR_SREP){uint32_t remaining=r32(p.payload+4);if(!r32(p.payload)||remaining<500||remaining>10000)goto reject;r->proof_until[r->count]=now+(remaining>3000?3000:remaining);}else r->proof_until[r->count]=now+SR_CACHE_MS;r->candidates[r->count++]=candidate;if(r->count>n->candidate_high)n->candidate_high=r->count;
   if(!r->close)r->close=now+SR_W<r->deadline?now+SR_W:r->deadline;
   ev(n,SR_CANDIDATE,&p,0);return 0;
  }
 }else if(sr_base_type(p.type)==SR_ERROR){
  if(!p.index){if(p.boot!=n->boot)goto reject;for(unsigned i=0;i<SR_ROUTES;i++){sr_route*r=&n->routes[i];if(r->used&&r->request==p.request&&same(r->path,path_of(&p))){if(p.payload[0]==p.n-1){r->used=0;ev(n,SR_INVALIDATED,&p,7);}else invalidate(n,p.path[p.payload[0]],p.path[p.payload[0]+1]);}}return 0;}
 }else{
  if(p.index==p.n-1){if(p.type==SR_SDATA&&(!mid_equal(p.dst,n->service_id)||n->service_until<=now)){p.type=SR_SERR;p.payload[0]=p.n-1;p.len=1;p.index--;p.ttl=p.index+1;return queue(n,p,p.path[p.index]);}for(unsigned i=0;i<64;i++)if(n->delivered[i].used&&mid_equal(n->delivered[i].origin,p.path[0])&&n->delivered[i].boot==p.boot&&n->delivered[i].seq==p.seq)return 0;
   n->delivered[n->delivered_cursor]=(mid_seen){p.path[0],p.boot,p.seq,1};n->delivered_cursor=(n->delivered_cursor+1)%64;ev(n,SR_DELIVERED,&p,0);return 0;}
  ev(n,SR_RELAY,&p,0);p.index++;p.ttl--;if(!live(n,p.path[p.index])){failed(n,&p,p.index-1);return 0;}return queue(n,p,p.path[p.index]);
 }
 p.index--;p.ttl--;return queue(n,p,p.path[p.index]);
reject:n->rejected++;return -1;
}
int sr_next_tx(sr_node*n,sr_out*out,uint64_t now){
 sr_tick(n,now);while(n->count){sr_out item=n->out[n->head];n->head=(n->head+1)%SR_OUT;n->count--;
  if(now-item.queued>=SR_QUEUE_MS){if(sr_base_type(item.packet.type)==SR_DATA)failed(n,&item.packet,item.packet.index-1);else ev(n,SR_DROPPED,&item.packet,5);continue;}
  if(item.next.mac[0]!=255&&(!live(n,item.next)||peer(n,item.next)->boot!=item.next_boot)){if(sr_base_type(item.packet.type)==SR_DATA)failed(n,&item.packet,item.packet.index-1);continue;}
  *out=item;if(sr_base_type(item.packet.type)==SR_DATA){n->data_frames++;n->data_bytes+=60+item.packet.len;}else{n->control_frames++;n->control_bytes+=60+item.packet.len;}return 1;
 }return 0;
}
void sr_tx_result(sr_node*n,const sr_out*out,int ok,uint64_t now){sr_tick(n,now);if(!ok&&sr_base_type(out->packet.type)==SR_DATA)failed(n,&out->packet,out->packet.index-1);}
int sr_next_event(sr_node*n,sr_event*e){if(!n->event_count)return 0;*e=n->events[n->event_head];n->event_head=(n->event_head+1)%SR_EVENTS;n->event_count--;return 1;}
void sr_stop(sr_node*n){
 for(unsigned i=0;i<SR_PENDING;i++)if(n->pending[i].used){sr_packet p=packet(n,SR_DATA,n->pending[i].dst,n->pending[i].seq,1);p.n=1;p.path[0]=n->self;ev(n,SR_NO_ROUTE,&p,6);n->pending[i].used=0;}
 while(n->count){sr_out*o=&n->out[n->head];if(sr_base_type(o->packet.type)==SR_DATA)ev(n,SR_UNKNOWN,&o->packet,6);n->head=(n->head+1)%SR_OUT;n->count--;}
 memset(n->rounds,0,sizeof(n->rounds));memset(n->routes,0,sizeof(n->routes));
}

void sr_service(sr_node*n,mid_id id,uint32_t session,uint64_t until){n->service_id=id;n->pc_session=session;n->service_until=until;}
int sr_query(sr_node*n,mid_id dst,uint64_t now){sr_tick(n,now);if(live(n,dst)||cached(n,dst))return 1;for(unsigned i=0;i<SR_ROUNDS;i++)if(n->rounds[i].used&&mid_equal(n->rounds[i].dst,dst))return 0;sr_round*r=NULL;for(unsigned i=0;i<SR_ROUNDS;i++)if(!n->rounds[i].used){r=&n->rounds[i];break;}if(!r||n->request_seq==UINT32_MAX)return -1;if(!rreq_take(n))return -1;*r=(sr_round){.used=1,.dst=dst,.request=++n->request_seq,.deadline=now+SR_DEADLINE};sr_packet p=packet(n,SR_RREQ,dst,r->request,r->request);p.n=1;p.ttl=4;p.path[0]=n->self;mid_id broadcast={{255,255,255,255,255,255}};if(queue(n,p,broadcast)){r->used=0;return -1;}ev(n,SR_REQUEST,&p,0);return 0;}

