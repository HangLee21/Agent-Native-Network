#include "neighbor_sync.h"
#include <string.h>
void e1_clear_absent_neighbors(sr_node*sr,nd_node*nd){
 for(unsigned i=0;i<SR_PEERS;i++){
  sr_peer*p=&sr->peers[i];
  if(p->used&&!nd_find(nd,p->id)){
   mid_id id=p->id;uint32_t boot=p->boot;
   sr_neighbor(sr,id,boot,0);
   memset(p,0,sizeof(*p));
  }
 }
}
