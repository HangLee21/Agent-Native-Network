#ifndef FLIGHT_BOOT_CATALOG_H
#define FLIGHT_BOOT_CATALOG_H
#include <stdint.h>
#define BC_ROWS 32u
#define BC_FRESH_MS 10000u
typedef struct {uint8_t used,mac[6];uint32_t boot;uint64_t at,conflict_until;} bc_row;
typedef struct {bc_row rows[BC_ROWS];uint32_t full,conflicts;} bc_catalog;
void bc_init(bc_catalog*);
/* Only note a source's own boot from an accepted protocol packet, not a path
 * member or destination. No authentication is implied. */
int bc_note(bc_catalog*,const uint8_t[6],uint32_t,uint64_t);
int bc_get(const bc_catalog*,const uint8_t[6],uint64_t,uint32_t*,uint32_t*);
#endif
