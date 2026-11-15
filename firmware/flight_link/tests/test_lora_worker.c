/* Executes the real worker with fake FreeRTOS queues and fake radio port.
 * Nothing in this fixture opens a device or performs RF. */
#include <setjmp.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../mid_baseline/field_agent/lora_ref/runtime.c"
static jmp_buf done;static uint64_t clock_ms;static int scenario,settings_pending,report_one,report_two,inject_rx,cmd_receives,apply_count,listen_fail,tx_kind,tx_failed,tx_complete,port_on;
static int queue_fail_once,task_fail_once,queue_created,task_calls;
static unsigned wdt_adds,wdt_resets,wdt_deletes;static int wdt_existing;
static config_job setting;static int q_settings,q_frames,q_events;
static uint8_t wire[48];
static void put32(uint8_t*p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
int64_t esp_timer_get_time(void){return (int64_t)clock_ms*1000;}
void vTaskDelay(unsigned n){clock_ms+=n;if(clock_ms>7000)longjmp(done,1);}
int xQueueSend(QueueHandle_t q,const void*p,unsigned t){(void)q;(void)p;(void)t;return pdTRUE;}
int xQueueReceive(QueueHandle_t q,void*p,unsigned t){(void)t;if(q==&q_settings&&settings_pending){memcpy(p,&setting,sizeof(setting));settings_pending=0;return pdTRUE;}if(q==&q_frames&&scenario==5&&(!report_one||(apply_count>=2&&!report_two))){frame_job j={.len=48,.seq=(!report_one?11:12),.generation=1,.sampled=clock_ms};memcpy(j.bytes,"LRN1",4);if(!report_one)report_one=1;else report_two=1;memcpy(p,&j,sizeof(j));return pdTRUE;}return 0;}
int xQueueReset(QueueHandle_t q){(void)q;return pdTRUE;}
QueueHandle_t xQueueCreate(unsigned count,unsigned size){if(queue_fail_once){queue_fail_once=0;return NULL;}queue_created++;if(count==8)return &q_events;if(size==sizeof(config_job))return &q_settings;if(size==sizeof(frame_job))return &q_frames;assert(0);return NULL;}
int xQueueOverwrite(QueueHandle_t q,const void*p){assert(q==&q_settings);memcpy(&setting,p,sizeof(setting));settings_pending=1;return pdTRUE;}
int xTaskCreate(void(*fn)(void*),const char*name,unsigned stack,void*arg,unsigned priority,void*handle){(void)fn;(void)name;(void)stack;(void)arg;(void)priority;(void)handle;task_calls++;if(task_fail_once){task_fail_once=0;return 0;}return pdPASS;}
int esp_task_wdt_add(void*p){(void)p;wdt_adds++;return wdt_existing?-1:0;}
int esp_task_wdt_delete(void*p){(void)p;wdt_deletes++;return 0;}
int esp_task_wdt_reset(void){wdt_resets++;return 0;}
int esp_task_wdt_status(void*p){(void)p;return wdt_existing?0:-1;}
int lref_port_apply(const lref_config*c){assert(c->role==2&&c->frequency==470500000);apply_count++;port_on=1;return 0;}
void lref_port_off(void){port_on=0;if((scenario==4&&tx_kind==2)||(scenario==5&&tx_kind==1))tx_failed=1;}
int lref_port_rx(uint8_t*b,unsigned*n,int*rssi,int*snr){(void)rssi;(void)snr;if(!port_on)return 0;if(scenario==1&&!inject_rx){inject_rx=1;return -1;}if(scenario==3&&!inject_rx){inject_rx=1;return -2;}
 if((scenario==1||scenario==3)?apply_count>=2:(scenario==5?report_two:1)){
  int max_cmd=(scenario==2||scenario==4)?2:1;if(cmd_receives<max_cmd&&((cmd_receives==0)||(apply_count>=2))){memcpy(b,wire,48);*n=48;cmd_receives++;return 1;}}
 return 0;}
int lref_port_listen(void){if(scenario==3&&!listen_fail){listen_fail=1;return -1;}return 0;}
int lref_port_tx(const uint8_t*b,unsigned n,uint32_t*toa){assert(n==48);*toa=10;tx_kind=!memcmp(b,"LRN1",4)?1:2;if(scenario==2&&tx_kind==2&&!tx_failed){tx_failed=1;return -1;}return 0;}
int lref_port_tx_done(void){if(((scenario==4&&tx_kind==2)||(scenario==5&&tx_kind==1))&&!tx_failed){return 0;}tx_complete++;return 1;}
void lrn1_set_delay(uint8_t*b,unsigned n,uint32_t d){(void)b;(void)n;(void)d;}
int main(void){const uint8_t mac[6]={2,0,0,0,0,1};memcpy(wire,"LRC2",4);wire[4]=1;wire[5]=1;wire[6]=48;memcpy(wire+8,mac,6);put32(wire+16,7);put32(wire+20,10);put32(wire+24,1);put32(wire+32,60000);put32(wire+36,42);put32(wire+44,fc_crc32(wire,44));
 for(scenario=1;scenario<=5;scenario++){
  clock_ms=0;settings_pending=1;report_one=report_two=inject_rx=cmd_receives=apply_count=listen_fail=tx_kind=tx_failed=tx_complete=port_on=0;running=0;recovery_attempted=recovery_success=recovery_exhausted=0;recovery_state=0;fc_init(&control,mac,7);fc_report_sent(&control,10,0);
  settings=&q_settings;frames=&q_frames;events=&q_events;setting=(config_job){.config={.role=2,.frequency=470500000},.generation=1};
  if(!setjmp(done))worker(NULL);
  assert(apply_count>=2&&recovery_success>=1&&running==2&&control.executed==1&&tx_complete>=1&&lora_ref_progress()>0);
  if(scenario==2||scenario==4)assert(control.duplicates==1);
  if(scenario==5)assert(report_one&&report_two);
 }
 settings=frames=events=NULL;task_started=queue_created=task_calls=0;queue_fail_once=task_fail_once=1;generation=1;cfg.role=2;cfg.frequency=470500000;boot_suppressed=0;lref_recovery schedule={0};assert(spawn_worker(NULL)<0);lref_recovery_fault(&schedule,0);assert(lref_recovery_tick(&schedule,1000,spawn_worker,NULL)==-1);assert(lref_recovery_tick(&schedule,3000,spawn_worker,NULL)==1&&task_started&&task_calls==2);assert(spawn_worker(NULL)==0&&task_calls==2);
 scenario=1;clock_ms=0;inject_rx=cmd_receives=apply_count=tx_kind=tx_failed=tx_complete=port_on=0;running=0;recovery_success=0;watch_requested=1;worker_wdt_registered=0;worker_wdt_due=0;fc_init(&control,mac,7);fc_report_sent(&control,10,0);if(!setjmp(done))worker(NULL);assert(apply_count>=2&&running==2&&control.executed==1&&tx_complete>=1&&wdt_adds==1&&wdt_resets>1);watch_requested=0;worker_progress_step();assert(wdt_deletes==1);watch_requested=1;wdt_existing=1;worker_progress_step();assert(worker_wdt_registered&&wdt_adds==2);
 puts("PASS real LoRa worker with fake queue/radio/WDT API: RX driver, ACK TX, RX rearm, ACK timeout and report TX timeout recover; queue/task create fail then worker processes command; dedup retained");return 0;
}
