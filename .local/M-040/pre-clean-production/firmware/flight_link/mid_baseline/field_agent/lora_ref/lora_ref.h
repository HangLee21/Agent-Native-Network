#ifndef MID_LORA_REF_H
#define MID_LORA_REF_H
#include "neighbors.h"
#include "telemetry.h"
#include "cJSON.h"
/* Main-task APIs. Worker alone owns LR1121/SPI. Defaults off. */
void lora_ref_init(mid_id self,uint32_t boot);
int lora_ref_command(cJSON*,const char*,const char**);
void lora_ref_status(cJSON*);
uint32_t lora_ref_progress(void);
int lora_ref_watch_enabled(void);
cJSON* lora_ref_tick(nd_node*,mt_node*,uint64_t,int (*allowed)(mid_id));
#endif
