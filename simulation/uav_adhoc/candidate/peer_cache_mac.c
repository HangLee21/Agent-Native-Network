#include "peer_cache_mac.h"
#include <string.h>
static int is_broadcast(const uint8_t*p){static const uint8_t b[6]={255,255,255,255,255,255};return memcmp(p,b,6)==0;}
int e1_peer_access(e1_peer_cache*c,const uint8_t id[6],uint64_t now,int replace,uint8_t evicted[6]){
 unsigned i,old=E1_PEER_LIMIT;
 if(evicted)memset(evicted,255,6);
 for(i=0;i<c->count;i++)if(!memcmp(c->peer[i],id,6)){c->last[i]=now;return 0;}
 if(c->count<E1_PEER_LIMIT){i=c->count++;memcpy(c->peer[i],id,6);c->last[i]=now;return 0;}
 if(!replace)return -1;
 for(i=0;i<c->count;i++)if(!is_broadcast(c->peer[i])&&(old==E1_PEER_LIMIT||c->last[i]<c->last[old]))old=i;
 if(old==E1_PEER_LIMIT)return -1;
 if(evicted)memcpy(evicted,c->peer[old],6);
 memcpy(c->peer[old],id,6);c->last[old]=now;return 1;
}
void e1_peer_remove(e1_peer_cache*c,const uint8_t id[6]){
 for(unsigned i=0;i<c->count;i++)if(!memcmp(c->peer[i],id,6)){
  unsigned tail=(unsigned)--c->count;
  if(i!=tail){memcpy(c->peer[i],c->peer[tail],6);c->last[i]=c->last[tail];}
  return;
 }
}
