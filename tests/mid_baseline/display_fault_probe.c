#include "mid_display.h"
#include "mock_platform.h"
#include <assert.h>
#include <setjmp.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
struct mock_queue {mid_display_snapshot value;int occupied;};
static struct mock_queue q;static int scenario,deleted,io_calls,power_off,frames,probes,ready_seen;static int64_t clock_us;
static void (*run_worker)(void *);static jmp_buf stop;
QueueHandle_t xQueueCreate(unsigned n,unsigned bytes){assert(n==1&&bytes==sizeof(q.value));return scenario==0?NULL:&q;}
int xQueueOverwrite(QueueHandle_t h,const void *v){assert(h==&q);memcpy(&q.value,v,sizeof(q.value));q.occupied=1;return pdTRUE;}
int xQueueReceive(QueueHandle_t h,void *v,unsigned wait){assert(h==&q&&wait<=20);clock_us+=wait*1000;assert(clock_us<3000000);if(!q.occupied)return pdFALSE;memcpy(v,&q.value,sizeof(q.value));q.occupied=0;return pdTRUE;}
void vQueueDelete(QueueHandle_t h){assert(h==&q);deleted++;}
int xTaskCreate(void (*f)(void *),const char *name,unsigned stack,void *arg,unsigned priority,void *handle){(void)name;(void)arg;(void)handle;assert(priority==1&&stack==6144);run_worker=f;return scenario==1?pdFALSE:pdPASS;}
void vTaskDelay(unsigned n){clock_us+=n*1000;}
void vTaskDelete(void *v){assert(!v);longjmp(stop,1);}
int gpio_config(const gpio_config_t *v){assert(v);return ESP_OK;}
int gpio_set_level(int pin,int value){io_calls++;if(pin==36&&!value)power_off++;return ESP_OK;}
int gpio_get_level(int pin){assert(pin==0);return 1;}
int i2c_new_master_bus(const i2c_master_bus_config_t *c,i2c_master_bus_handle_t *b){assert(c->sda_io_num==18&&c->scl_io_num==17);io_calls++;*b=&q;return ESP_OK;}
int i2c_master_probe(i2c_master_bus_handle_t b,uint16_t addr,int ms){assert(b&&ms==50&&(addr==0x3c||addr==0x3d));probes++;io_calls++;return scenario==2?ESP_FAIL:ESP_OK;}
int i2c_master_bus_add_device(i2c_master_bus_handle_t b,const i2c_device_config_t *c,i2c_master_dev_handle_t *d){assert(b&&c->scl_speed_hz==400000);*d=&q;io_calls++;return ESP_OK;}
int i2c_master_transmit(i2c_master_dev_handle_t d,const uint8_t *b,size_t n,int ms){assert(d&&b&&ms==50);io_calls++;if(mid_display_hardware_state()==MID_DISPLAY_HW_READY)ready_seen=1;if(n==1025){frames++;assert(b[0]==0x40);if(scenario==3)return ESP_FAIL;}if(scenario==4&&frames==1&&n!=1025)return ESP_FAIL;return ESP_OK;}
int i2c_master_bus_rm_device(i2c_master_dev_handle_t d){assert(d);return ESP_OK;}
int i2c_del_master_bus(i2c_master_bus_handle_t b){assert(b);return ESP_OK;}
int64_t esp_timer_get_time(void){return clock_us;}
const char *esp_err_to_name(int n){(void)n;return "E2 synthetic failure";}
void mock_log(const char *s,...){(void)s;}
int main(int argc,char **argv){
 assert(argc==2);scenario=atoi(argv[1]);assert(scenario>=0&&scenario<=4);
 mid_display_snapshot s;mid_display_identity id={.mac={0x90,0xda,0x72,0x48,0xa4,0xf8},.label='A',.protocol=MID_DISPLAY_MID,.channel=1};assert(!mid_display_model_init(&s,&id));
 int code=mid_display_start(&s);
 if(scenario<2){assert(code==-1&&mid_display_hardware_state()==MID_DISPLAY_HW_FAILED);assert(deleted==(scenario==1));assert(!io_calls);}
 else{assert(!code&&mid_display_hardware_state()==MID_DISPLAY_HW_STARTING);assert(!io_calls);assert(!mid_display_publish(&s));assert(!io_calls);if(!setjmp(stop))run_worker(NULL);assert(mid_display_hardware_state()==MID_DISPLAY_HW_FAILED&&deleted==0);assert(ready_seen==(scenario==4));if(scenario==2)assert(probes==2);}
 assert(!power_off);assert(mid_display_publish(&s)==-1);assert(mid_display_start(&s)==-1);assert(!strcmp(mid_display_destination_text(&s),"NO TX"));printf("PASS independent backend scenario %d; IO=%d frames=%d ready=%d no automatic restart\n",scenario,io_calls,frames,ready_seen);return 0;
}
