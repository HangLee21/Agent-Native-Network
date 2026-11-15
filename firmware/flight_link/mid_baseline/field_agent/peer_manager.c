#include "peer_manager.h"
#include <string.h>
static const uint8_t broadcast[6]={255,255,255,255,255,255};
void pm_init(pm_state*s){memset(s,0,sizeof(*s));}
int pm_ensure(pm_state*s,const pm_ops*o,const uint8_t mac[6],int waiting){
 if(!s||!o||!o->exists||!o->add||!o->del||!mac||waiting)return -1;
 if(!o->exists(o->ctx,broadcast)){if(o->add(o->ctx,broadcast)){s->failures++;return -1;}s->additions++;}
 if(!memcmp(mac,broadcast,6))return 0;
 if(mac[0]&1){s->failures++;return -1;}
 for(unsigned i=0;i<PM_UNICAST_SLOTS;i++)if(s->slots[i].used&&!memcmp(s->slots[i].mac,mac,6)){
  if(o->exists(o->ctx,mac))return 0;
  s->slots[i].used=0;break;
 }
 /* The manager owns the whole freshly initialized ESP-NOW session; an
  * untracked external peer is not safe to evict or silently claim. */
 if(o->exists(o->ctx,mac)){s->failures++;return -1;}
 unsigned at=PM_UNICAST_SLOTS;
 for(unsigned k=0;k<PM_UNICAST_SLOTS;k++){unsigned i=(s->cursor+k)%PM_UNICAST_SLOTS;if(!s->slots[i].used){at=i;break;}}
 if(at==PM_UNICAST_SLOTS){at=s->cursor;if(o->exists(o->ctx,s->slots[at].mac)&&o->del(o->ctx,s->slots[at].mac)){s->failures++;return -1;}s->slots[at].used=0;s->evictions++;}
 if(o->add(o->ctx,mac)){s->failures++;return -1;}
 s->slots[at].used=1;memcpy(s->slots[at].mac,mac,6);s->cursor=(at+1)%PM_UNICAST_SLOTS;s->additions++;return 0;
}
