#ifndef FLIGHT_PEER_MANAGER_H
#define FLIGHT_PEER_MANAGER_H
#include <stdint.h>
#define PM_UNICAST_SLOTS 19u
typedef struct {uint8_t used,mac[6];} pm_slot;
typedef struct {pm_slot slots[PM_UNICAST_SLOTS];unsigned cursor;uint32_t additions,evictions,failures;} pm_state;
typedef struct {int (*exists)(void*,const uint8_t[6]);int (*add)(void*,const uint8_t[6]);int (*del)(void*,const uint8_t[6]);void *ctx;} pm_ops;
void pm_init(pm_state*);
/* Never mutate driver peers while a send is in flight. Broadcast is permanent.
 * Call only with exclusive ownership of a freshly initialized ESP-NOW session. */
int pm_ensure(pm_state*,const pm_ops*,const uint8_t[6],int waiting);
#endif
