#include "route_config_store.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void){uint8_t a[12]={'N','D','c','1',27,0,0,0,6,1,0,0},b[12],backup[16],out[12];memcpy(b,a,12);b[4]=28;assert(!rc_pack(a,backup));assert(rc_choose(0,b,12,0,backup,16,out)==0&&!memcmp(out,b,12));
 /* Model a torn/invalid primary after changing config: old verified backup is
  * selected. A deliberate missing key never resurrects a cleared config. */
 b[0]=0;assert(rc_choose(0,b,12,0,backup,16,out)==1&&!memcmp(out,a,12));assert(rc_choose(2,b,12,0,backup,16,out)==1);assert(rc_choose(1,b,12,0,backup,16,out)==2);
 backup[15]^=1;assert(rc_choose(0,b,12,0,backup,16,out)<0);assert(rc_choose(2,b,12,1,backup,16,out)<0);a[8]=14;assert(!rc_valid(a,12));assert(rc_pack(a,backup)<0);
 puts("PASS route configuration selection: valid primary, corrupt/torn primary backup, missing does not resurrect, corrupt backup rejected (host model)");return 0;}
