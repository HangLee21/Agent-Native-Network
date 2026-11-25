#include "peer_cache.h"
int e1_peer_access(e1_peer_cache*c,uint8_t id,uint64_t now,int replace,uint8_t*evicted){
 unsigned i,old=E1_PEER_LIMIT;
 if(evicted)*evicted=E1_PEER_BROADCAST;
 for(i=0;i<c->count;i++)if(c->peer[i]==id){c->last[i]=now;return 0;}
 if(c->count<E1_PEER_LIMIT){i=c->count++;c->peer[i]=id;c->last[i]=now;return 0;}
 if(!replace)return -1;
 for(i=0;i<c->count;i++)if(c->peer[i]!=E1_PEER_BROADCAST&&(old==E1_PEER_LIMIT||c->last[i]<c->last[old]))old=i;
 if(old==E1_PEER_LIMIT)return -1;
 if(evicted)*evicted=c->peer[old];
 c->peer[old]=id;c->last[old]=now;return 1;
}
