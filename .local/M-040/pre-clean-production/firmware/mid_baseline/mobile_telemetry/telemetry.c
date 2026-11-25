#include "telemetry.h"
#include <string.h>
static uint32_t get(const uint8_t*p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put(uint8_t*p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
static int valid(mt_position p,int injected){
 if(p.source>2||p.fix>1||p.age_ms>MT_AGE_MAX)return 0;
 if((injected||p.fix)&&(!p.boot||!p.seq))return 0;
 if((!p.boot)!=(!p.seq))return 0;
 if(!p.boot&&(p.source||p.fix))return 0;
 if(p.fix)return p.source&&p.lat_e7>=-900000000&&p.lat_e7<=900000000&&p.lon_e7>=-1800000000&&p.lon_e7<=1800000000;
 return !p.lat_e7&&!p.lon_e7&&p.accuracy_mm==UINT32_MAX;
}
void mid_mt_init(mt_node*n,mid_id self,uint32_t boot,uint32_t group){memset(n,0,sizeof(*n));n->self=self;n->board_boot=boot;n->group=group;n->local.age_ms=MT_AGE_MAX;n->local.accuracy_mm=UINT32_MAX;}
mt_position mid_mt_aged(mt_position p,uint64_t elapsed){
 uint64_t age=elapsed>MT_AGE_MAX?MT_AGE_MAX:p.age_ms+elapsed;p.age_ms=(uint32_t)(age>MT_AGE_MAX?MT_AGE_MAX:age);
 if(age>MT_STALE_MS){p.fix=0;p.lat_e7=p.lon_e7=0;p.accuracy_mm=UINT32_MAX;}return p;
}
mt_position mid_mt_local(const mt_node*n,uint64_t now){return mid_mt_aged(n->local,now-n->injected);}
int mid_mt_set(mt_node*n,const mt_position*p,uint64_t now){
 if(!valid(*p,1)){n->rejected++;return -1;}
 if(p->boot==n->local.boot&&p->seq<=n->local.seq){n->duplicates++;return -1;}
 if(n->local.boot&&p->boot!=n->local.boot){for(unsigned i=0;i<4;i++)if(n->retired[i]==p->boot){n->rejected++;return -1;}n->retired[n->cursor++%4]=n->local.boot;}
 n->local=*p;n->injected=now;return 0;
}
void mid_mt_sample(mt_node*n,mid_id peer,int rssi_valid,int rssi,int channel_valid,int channel,uint64_t at){
 mt_rf*r=NULL;for(unsigned i=0;i<MT_ROWS;i++)if(n->rf[i].used&&mid_equal(n->rf[i].peer,peer)){r=&n->rf[i];break;}
 if(!r){for(unsigned i=0;i<MT_ROWS;i++)if(!n->rf[i].used){r=&n->rf[i];break;}}if(!r){n->rf_full++;return;}
 r->used=1;r->peer=peer;r->at=at;r->rssi_valid=rssi_valid;r->rssi=rssi;r->channel_valid=channel_valid;r->channel=channel;
 if(rssi_valid){r->valid_at=at;if(r->count<UINT32_MAX){if(!r->count)r->minimum=r->maximum=rssi;if(rssi<r->minimum)r->minimum=rssi;if(rssi>r->maximum)r->maximum=rssi;r->count++;r->sum+=rssi;}}
}
int mid_mt_encode(mt_node*n,uint8_t mode,uint64_t now,uint8_t*b,size_t cap){
 if(cap<MT_FRAME||!n->group||!n->board_boot||!mid_unicast(n->self)||mode>2||n->announcement_seq==UINT32_MAX)return -1;
 mt_position p=mid_mt_local(n,now);if(!valid(p,0))return -1;
 memset(b,0,MT_FRAME);memcpy(b,"MT01",4);put(b+4,n->group);memcpy(b+8,n->self.mac,6);put(b+14,n->board_boot);put(b+18,++n->announcement_seq);
 put(b+22,p.boot);put(b+26,p.seq);put(b+30,p.age_ms);put(b+34,(uint32_t)p.lat_e7);put(b+38,(uint32_t)p.lon_e7);put(b+42,p.accuracy_mm);b[46]=p.source;b[47]=p.fix;b[48]=mode;return MT_FRAME;
}
int mid_mt_receive(mt_node*n,mid_id physical,const uint8_t*b,size_t len,uint64_t now){
 if(len!=MT_FRAME||memcmp(b,"MT01",4)||get(b+4)!=n->group||memcmp(physical.mac,b+8,6)||!mid_unicast(physical)||mid_equal(physical,n->self)||!get(b+14)||!get(b+18)||b[48]>2||b[49]||b[50]||b[51])goto reject;
 mt_position p={.boot=get(b+22),.seq=get(b+26),.age_ms=get(b+30),.lat_e7=(int32_t)get(b+34),.lon_e7=(int32_t)get(b+38),.accuracy_mm=get(b+42),.source=b[46],.fix=b[47]};if(!valid(p,0))goto reject;
 uint32_t boot=get(b+14),seq=get(b+18);mt_peer*r=NULL;
 for(unsigned i=0;i<MT_ROWS;i++)if(n->peers[i].used&&mid_equal(n->peers[i].peer,physical)){r=&n->peers[i];break;}
 if(!r){for(unsigned i=0;i<MT_ROWS;i++)if(!n->peers[i].used){r=&n->peers[i];break;}}if(!r){n->peer_full++;return -1;}
 if(r->used&&r->board_boot==boot&&seq<=r->announcement_seq){n->duplicates++;return 0;}
 if(r->used&&r->board_boot!=boot){for(unsigned i=0;i<4;i++)if(r->retired[i]==boot)goto reject;r->retired[r->cursor++%4]=r->board_boot;}
 r->used=1;r->peer=physical;r->board_boot=boot;r->announcement_seq=seq;r->position=p;r->mode=b[48];r->at=now;return 1;
reject:n->rejected++;return -1;
}
