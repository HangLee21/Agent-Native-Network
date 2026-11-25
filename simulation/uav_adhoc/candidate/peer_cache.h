#ifndef E1_PEER_CACHE_H
#define E1_PEER_CACHE_H
#include <stdint.h>
#define E1_PEER_LIMIT 20u
#define E1_PEER_BROADCAST 255u
typedef struct { uint64_t last[E1_PEER_LIMIT]; uint8_t peer[E1_PEER_LIMIT]; uint8_t count; } e1_peer_cache;
/* Return 0 on existing/new, 1 on LRU replacement, -1 on full/rejected.
 * Broadcast is pinned; caller must perform SDK add/delete and handle failure. */
int e1_peer_access(e1_peer_cache*,uint8_t,uint64_t,int,uint8_t*);
#endif
