#ifndef E1_PEER_CACHE_MAC_H
#define E1_PEER_CACHE_MAC_H
#include <stdint.h>
#define E1_PEER_LIMIT 20u
typedef struct {uint64_t last[E1_PEER_LIMIT];uint8_t peer[E1_PEER_LIMIT][6];uint8_t count;} e1_peer_cache;
/* 0 existing/new, 1 eviction, -1 full. Broadcast cannot be evicted.
 * The caller can update a temporary copy and commit only after SDK success. */
int e1_peer_access(e1_peer_cache*,const uint8_t[6],uint64_t,int,uint8_t[6]);
void e1_peer_remove(e1_peer_cache*,const uint8_t[6]);
#endif
