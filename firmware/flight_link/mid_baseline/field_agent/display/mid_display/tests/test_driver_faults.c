#include "mid_display.h"
#include "mock_platform.h"
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct mock_queue {unsigned bytes,occupied;uint8_t payload[4096];};
static struct mock_queue queue;
static void (*task_function)(void *);
static jmp_buf stopped;
static int mode,tx_calls,probe_calls,supply_on,supply_off,saw_ready,queues_deleted;
static int64_t now;
QueueHandle_t xQueueCreate(unsigned length,unsigned bytes){assert(length==1&&bytes<=sizeof(queue.payload));queue.bytes=bytes;return &queue;}
int xQueueOverwrite(QueueHandle_t q,const void *data){assert(q==&queue);memcpy(q->payload,data,q->bytes);q->occupied=1;return pdTRUE;}
int xQueueReceive(QueueHandle_t q,void *data,unsigned ticks){assert(ticks<=20);now+=(int64_t)ticks*1000;if(!q->occupied)return pdFALSE;memcpy(data,q->payload,q->bytes);q->occupied=0;return pdTRUE;}
void vQueueDelete(QueueHandle_t q){assert(q==&queue);queues_deleted++;}
int xTaskCreate(void (*function)(void *),const char *name,unsigned stack,void *arg,unsigned priority,void *handle){(void)name;(void)arg;(void)handle;assert(stack==6144&&priority==1);task_function=function;return pdPASS;}
void vTaskDelay(unsigned ticks){now+=(int64_t)ticks*1000;}
void vTaskDelete(void *task){assert(task==NULL);longjmp(stopped,1);}
int gpio_config(const gpio_config_t *config){assert(config);return ESP_OK;}
int gpio_set_level(int pin,int level){if(pin==36){if(level)supply_on++;else supply_off++;}return ESP_OK;}
int gpio_get_level(int pin){assert(pin==0);return 1;}
int i2c_new_master_bus(const i2c_master_bus_config_t *cfg,i2c_master_bus_handle_t *bus){assert(cfg->sda_io_num==18&&cfg->scl_io_num==17);*bus=&queue;return ESP_OK;}
int i2c_master_probe(i2c_master_bus_handle_t bus,uint16_t address,int timeout){assert(bus&&timeout==50&&(address==0x3c||address==0x3d));probe_calls++;return mode==0?ESP_FAIL:ESP_OK;}
int i2c_master_bus_add_device(i2c_master_bus_handle_t bus,const i2c_device_config_t *cfg,i2c_master_dev_handle_t *dev){assert(bus&&cfg->scl_speed_hz==400000);*dev=&queue;return ESP_OK;}
int i2c_master_transmit(i2c_master_dev_handle_t dev,const uint8_t *bytes,size_t size,int timeout){
    assert(dev&&bytes&&timeout==50);tx_calls++;if(size==1025)assert(bytes[0]==0x40);
    if((mode==1&&tx_calls==3)||(mode==2&&tx_calls==4))return ESP_FAIL;
    return ESP_OK;
}
int i2c_master_bus_rm_device(i2c_master_dev_handle_t dev){assert(dev);return ESP_OK;}
int i2c_del_master_bus(i2c_master_bus_handle_t bus){assert(bus);return ESP_OK;}
int64_t esp_timer_get_time(void){return now;}
const char *esp_err_to_name(int error){(void)error;return "MOCK_FAILURE";}
void mock_log(const char *format,...){if(strstr(format,"ready:")){assert(mid_display_hardware_state()==MID_DISPLAY_HW_READY);saw_ready=1;}}
int main(int argc,char **argv){
    assert(argc==2);mode=atoi(argv[1]);assert(mode>=0&&mode<=2);
    mid_display_identity id={.mac={0x90,0xda,0x72,0x48,0xa4,0xf8},.channel=1,.label='A',.protocol=MID_DISPLAY_MID};
    mid_display_snapshot s;assert(!mid_display_model_init(&s,&id));
    mid_display_snapshot bad=s;bad.identity.protocol=MID_DISPLAY_ANN;bad.tx_state=MID_DISPLAY_TX_ANN_CONFIRMED;
    assert(mid_display_start(&bad)==-1&&mid_display_hardware_state()==MID_DISPLAY_HW_OFF);
    assert(!mid_display_start(&s)&&mid_display_hardware_state()==MID_DISPLAY_HW_STARTING);
    assert(task_function&&probe_calls==0&&tx_calls==0&&supply_on==0);
    assert(!mid_display_publish(&s)); /* publishing itself performs no bus/power operation */
    assert(mid_display_start(&s)==-1); /* no second worker */
    if(!setjmp(stopped))task_function(NULL);
    assert(mid_display_hardware_state()==MID_DISPLAY_HW_FAILED);
    assert(supply_on==1&&supply_off==0&&queues_deleted==0);
    assert(mid_display_publish(&s)==-1);
    assert(saw_ready==(mode==2));
    printf("PASS: synthetic I2C fault mode=%d; queue-only publisher; first-frame readiness; failure isolation; shared power retained.\n",mode);
    return 0;
}
