#include "recovery.h"
#include <string.h>
void lref_recovery_reset(lref_recovery*r){memset(r,0,sizeof(*r));}
void lref_recovery_fault(lref_recovery*r,uint64_t now){if(!r->active&&!r->exhausted){r->active=1;r->due=now+1000;}}
int lref_recovery_tick(lref_recovery*r,uint64_t now,lref_recover_apply apply,void*ctx){
 if(r->exhausted&&now>=r->due){r->active=1;r->exhausted=0;r->attempts=0;}
 if(!r->active||now<r->due||!apply)return 0;
 r->attempts++;if(!apply(ctx)){lref_recovery_reset(r);return 1;}
 if(r->attempts>=LREF_RECOVERY_MAX){r->active=0;r->exhausted=1;r->due=now+LREF_RECOVERY_COOLDOWN_MS;return -2;}
 r->due=now+(1000u<<r->attempts);return -1;
}
