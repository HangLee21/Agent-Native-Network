#ifndef LREF_RECOVERY_H
#define LREF_RECOVERY_H
#include <stdint.h>
#define LREF_RECOVERY_MAX 4u
#define LREF_RECOVERY_COOLDOWN_MS 60000u
typedef struct {uint64_t due;unsigned attempts;int active,exhausted;} lref_recovery;
typedef int (*lref_recover_apply)(void *);
void lref_recovery_reset(lref_recovery *);
void lref_recovery_fault(lref_recovery *,uint64_t);
/* 0 not due, 1 restored, -1 attempt failed, -2 exhausted. */
int lref_recovery_tick(lref_recovery *,uint64_t,lref_recover_apply,void *);
#endif
