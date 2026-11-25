#ifndef ANN_CONSOLE_H
#define ANN_CONSOLE_H
#include "ann.h"
typedef struct { ann_node *node; int armed,bench; char run_id[49]; uint64_t arm_until,next,duration_end;
 uint32_t count,sent,interval,frame_bytes; ann_id dst; int echo;
 const char *chip,*build_id; } ann_console;
void ann_console_init(ann_console*,ann_node*,const char*,const char*);
/* One UTF-8 flat JSON command, at most 512 bytes. Writes one JSON reply; never opens a serial device. */
int ann_command(ann_console*,const char*,size_t,char*,size_t,uint64_t);
void ann_console_tick(ann_console*,uint64_t);
void ann_id_text(ann_id,char[18]);
int ann_id_parse(const char*,ann_id*);
#endif
