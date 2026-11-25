#ifndef ANN_LOG_H
#define ANN_LOG_H
#include "ann_console.h"
void ann_log_event(const ann_console*,const ann_event*,char*,size_t);
void ann_log_tx(const ann_console*,const ann_out*,const char*,int,uint64_t,char*,size_t);
#endif
