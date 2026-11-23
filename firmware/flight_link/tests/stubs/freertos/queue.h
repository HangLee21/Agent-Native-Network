#include "FreeRTOS.h"
int xQueueSend(QueueHandle_t,const void*,unsigned);
int xQueueReceive(QueueHandle_t,void*,unsigned);
int xQueueOverwrite(QueueHandle_t,const void*);
int xQueueReset(QueueHandle_t);
QueueHandle_t xQueueCreate(unsigned,unsigned);
