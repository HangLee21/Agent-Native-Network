#include "route_config_store.h"
#include "lora_ref/flight_control.h"
#include <string.h>
static uint32_t rd(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
int rc_valid(const uint8_t*b,size_t n){return b&&n==RC_CONFIG_BYTES&&!memcmp(b,"NDc1",4)&&rd(b+4)&&b[8]>=1&&b[8]<=13&&b[9]<=1&&!b[10]&&!b[11];}
int rc_pack(const uint8_t b[RC_CONFIG_BYTES],uint8_t out[RC_BACKUP_BYTES]){if(!rc_valid(b,RC_CONFIG_BYTES)||!out)return -1;memcpy(out,b,RC_CONFIG_BYTES);uint32_t crc=fc_crc32(b,RC_CONFIG_BYTES);for(unsigned i=0;i<4;i++)out[12+i]=(uint8_t)(crc>>(8*i));return 0;}
int rc_choose(int status,const uint8_t*primary,size_t pn,int backup_status,const uint8_t*backup,size_t bn,uint8_t out[RC_CONFIG_BYTES]){
 if(!out)return -1;
 if(status==0&&rc_valid(primary,pn)){memcpy(out,primary,RC_CONFIG_BYTES);return 0;}
 /* Missing primary is distinct from corruption: a deliberate clear must not
  * revive an old backup. */
 if(status==1)return 2;
 if(backup_status==0&&backup&&bn==RC_BACKUP_BYTES&&rc_valid(backup,RC_CONFIG_BYTES)&&rd(backup+12)==fc_crc32(backup,RC_CONFIG_BYTES)){memcpy(out,backup,RC_CONFIG_BYTES);return 1;}
 return -1;
}
