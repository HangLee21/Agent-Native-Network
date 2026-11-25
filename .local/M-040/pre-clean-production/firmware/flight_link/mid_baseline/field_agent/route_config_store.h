#ifndef ROUTE_CONFIG_STORE_H
#define ROUTE_CONFIG_STORE_H
#include <stddef.h>
#include <stdint.h>
#define RC_CONFIG_BYTES 12u
#define RC_BACKUP_BYTES 16u
/* status: 0 read OK, 1 missing, 2 read failure. Selection: 0 primary,
 * 1 validated backup, 2 deliberately missing, -1 corrupt/unavailable. */
int rc_valid(const uint8_t*,size_t);
int rc_pack(const uint8_t[RC_CONFIG_BYTES],uint8_t[RC_BACKUP_BYTES]);
int rc_choose(int,const uint8_t*,size_t,int,const uint8_t*,size_t,uint8_t[RC_CONFIG_BYTES]);
#endif
