#ifndef TEST_ESP_TASK_WDT_H
#define TEST_ESP_TASK_WDT_H
#include "freertos/FreeRTOS.h"
int esp_task_wdt_add(void*);
int esp_task_wdt_delete(void*);
int esp_task_wdt_reset(void);
int esp_task_wdt_status(void*);
#endif
