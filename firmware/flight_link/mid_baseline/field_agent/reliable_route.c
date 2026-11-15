#include "reliable_route.h"
#include <string.h>
#if MID_ROUTE_FEEDBACK
static fr_pending*find(fr_state*s,const uint8_t*b,size_t len){if(!s||!b||len<36||memcmp(b,"FLW2",4)||b[4]!=1||b[5]!=1)return 0;uint32_t id=(uint32_t)b[12]|((uint32_t)b[13]<<8)|((uint32_t)b[14]<<16)|((uint32_t)b[15]<<24);for(unsigned i=0;i<FR_PENDING;i++)if(s->pending[i].used&&s->pending[i].id==id)return &s->pending[i];return 0;}
#endif
void fr_route_before(fr_state*s,sr_node*n,const uint8_t*b,size_t len,uint64_t now){
#if MID_ROUTE_FEEDBACK
 fr_pending*p=find(s,b,len);if(p&&p->attempts>=2&&!p->feedback_done&&p->first_route_seq){p->feedback_done=1;(void)sr_unconfirmed(n,p->first_route_seq,now);}
#else
 (void)s;(void)n;(void)b;(void)len;(void)now;
#endif
}
void fr_route_submitted(fr_state*s,const uint8_t*b,size_t len,uint32_t seq){
#if MID_ROUTE_FEEDBACK
 fr_pending*p=find(s,b,len);if(p&&!p->first_route_seq)p->first_route_seq=seq;
#else
 (void)s;(void)b;(void)len;(void)seq;
#endif
}
