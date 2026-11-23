#include "lora_ref.h"
#include "port.h"
#include "flight_control.h"
#include "recovery.h"
#include "../lrn1_frame.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_task_wdt.h"
#include "nvs.h"
#include <string.h>
#include <stdio.h>
typedef struct {lref_config config;uint32_t generation;} config_job;
typedef struct {uint8_t bytes[208];unsigned len;uint32_t seq,generation;uint64_t sampled;} frame_job;
typedef struct {int kind,result,rssi,snr;uint32_t seq,toa;uint64_t at,done;frame_job frame;lref_config config;} ref_event;
static QueueHandle_t settings,frames,events;
/* Factory default only. A board that already has a saved lr_ref/cfg keeps its
 * saved frequency until lora_ref_config explicitly changes it, so moving the
 * default to 470 MHz does not silently retune deployed boards. */
/* Published by the worker (it owns SPI) and read by the frame builder. */
static volatile uint16_t health_vbat_mv;static volatile int16_t health_temp_c=-128;
static lref_config cfg={.magic=0x3146524c,.period=10000,.jitter=250,.frequency=470000000,.bw=125000,.sf=7,.cr=5,.preamble=8,.sync=18,.start=1};
static mid_id identity;static uint32_t own_boot,generation,applied_version,sequence,rx_sequence;
static uint64_t due;
static uint32_t attempted,submitted,completed,skipped,rx_bad,event_drops,rx_ok,last_rx_ms;
static int running,boot_suppressed;
static fc_state control;
static uint32_t control_ack_submitted,control_ack_done,control_ack_failed;
static uint32_t recovery_attempted,recovery_success,recovery_exhausted;
static int recovery_state;
static lref_recovery task_recovery;
static uint32_t task_start_attempts,task_start_failures;
static int task_started;
static uint32_t worker_progress;static int watch_requested,worker_wdt_registered;static uint64_t worker_wdt_due;
uint32_t lora_ref_progress(void){return __atomic_load_n(&worker_progress,__ATOMIC_ACQUIRE);}
int lora_ref_watch_enabled(void){return __atomic_load_n(&watch_requested,__ATOMIC_ACQUIRE);}
static uint64_t ms(void){return (uint64_t)esp_timer_get_time()/1000;}
static void worker_progress_step(void){__atomic_fetch_add(&worker_progress,1,__ATOMIC_RELEASE);int want=lora_ref_watch_enabled();if(want&&!worker_wdt_registered&&ms()>=worker_wdt_due){if(esp_task_wdt_add(NULL)==ESP_OK||esp_task_wdt_status(NULL)==ESP_OK)__atomic_store_n(&worker_wdt_registered,1,__ATOMIC_RELEASE);else worker_wdt_due=ms()+5000;}else if(!want&&worker_wdt_registered){if(esp_task_wdt_delete(NULL)==ESP_OK)__atomic_store_n(&worker_wdt_registered,0,__ATOMIC_RELEASE);}if(worker_wdt_registered)(void)esp_task_wdt_reset();}
static uint32_t crc32(const uint8_t*p,unsigned n){uint32_t crc=0xffffffffu;while(n--){crc^=*p++;for(unsigned i=0;i<8;i++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return ~crc;}
#ifndef LREF_WORKER_TEST
static uint32_t lrn1_cursor;
/* Health rides along every Nth frame so neighbour rows stay full in dense clusters. */
#define LRN1_STATUS_EVERY 5u
static unsigned capture(nd_node*n,mt_node*m,uint64_t now,int(*allowed)(mid_id),uint8_t*data,uint32_t seq){
 lrn1_result res;lrn1_status st;lrn1_gps gps;const lrn1_status*pst=0;const lrn1_gps*pg=0;
 nd_trim(n,now);
 if(seq%LRN1_STATUS_EVERY==0u){memset(&st,0,sizeof st);lrn1_platform_status(&st);pst=&st;}
 memset(&gps,0,sizeof gps);if(lrn1_platform_gps(&gps))pg=&gps;
 unsigned len=lrn1_build(n,m,now,allowed,lrn1_node_number(),pst,pg,data,208,seq,cfg.period,&lrn1_cursor,&res);
 if(!len)__atomic_fetch_add(&skipped,1,__ATOMIC_RELAXED);
 return len;
}
#endif
static void emit_event(ref_event*e){if(xQueueSend(events,e,0)!=pdTRUE)__atomic_fetch_add(&event_drops,1,__ATOMIC_RELAXED);}
static int recover_apply(void*ctx){return lref_port_apply((const lref_config*)ctx);}
static void worker(void*unused){
 (void)unused;lref_config current={0};uint32_t applied_generation=0;ref_event e;lref_recovery recovery={0};int fault_seen=0;
 for(;;){config_job next;
  worker_progress_step();
  if(xQueueReceive(settings,&next,0)==pdTRUE){current=next.config;applied_generation=next.generation;lref_recovery_reset(&recovery);fault_seen=0;__atomic_store_n(&recovery_state,0,__ATOMIC_RELEASE);int ok=lref_port_apply(&current);__atomic_store_n(&running,ok?-1:(int)current.role,__ATOMIC_RELEASE);__atomic_store_n(&applied_version,applied_generation,__ATOMIC_RELEASE);memset(&e,0,sizeof(e));e.kind=2;e.seq=next.generation;e.result=ok;e.at=ms();e.config=current;emit_event(&e);}
  if(__atomic_load_n(&running,__ATOMIC_ACQUIRE)==1){memset(&e,0,sizeof(e));e.kind=0;e.at=ms();e.config=current;int r=lref_port_rx(e.frame.bytes,&e.frame.len,&e.rssi,&e.snr);
   if(r==1){uint8_t*p=e.frame.bytes;unsigned n=e.frame.len;uint32_t crc=(uint32_t)p[n-4]|((uint32_t)p[n-3]<<8)|((uint32_t)p[n-2]<<16)|((uint32_t)p[n-1]<<24);
    if(memcmp(p,"LRN1",4)||p[4]!=44||p[5]!=20||p[7]>8||n!=48u+20u*p[7]||crc!=crc32(p,n-4))__atomic_fetch_add(&rx_bad,1,__ATOMIC_RELAXED);else{e.at=ms();__atomic_fetch_add(&rx_ok,1,__ATOMIC_RELAXED);__atomic_store_n(&last_rx_ms,(uint32_t)e.at,__ATOMIC_RELAXED);emit_event(&e);}
   }else if(r<0){__atomic_fetch_add(&rx_bad,1,__ATOMIC_RELAXED);if(r==-1)__atomic_store_n(&running,-1,__ATOMIC_RELEASE);}
   if(r!=0&&__atomic_load_n(&running,__ATOMIC_ACQUIRE)==1&&lref_port_listen())__atomic_store_n(&running,-1,__ATOMIC_RELEASE);
  }
  if(__atomic_load_n(&running,__ATOMIC_ACQUIRE)==2){
   uint8_t incoming[208],reply[FC_FRAME];unsigned incoming_len=0;int rssi=0,snr=0;
   int received=lref_port_rx(incoming,&incoming_len,&rssi,&snr);
   if(received==1&&incoming_len>=4&&!memcmp(incoming,"LRC2",4)){
    int result=fc_receive(&control,incoming,incoming_len,ms(),3u,reply);
    if(result){uint32_t toa=0;int rc=lref_port_tx(reply,sizeof(reply),&toa);if(!rc){__atomic_fetch_add(&control_ack_submitted,1,__ATOMIC_RELAXED);uint64_t stop=ms()+toa+1500;int done=0;while(ms()<stop){done=lref_port_tx_done();worker_progress_step();if(done)break;vTaskDelay(pdMS_TO_TICKS(5)+1);}if(done==1)__atomic_fetch_add(&control_ack_done,1,__ATOMIC_RELAXED);else rc=-1;}if(rc){__atomic_fetch_add(&control_ack_failed,1,__ATOMIC_RELAXED);lref_port_off();__atomic_store_n(&running,-1,__ATOMIC_RELEASE);}}
   }else if(received==-1)__atomic_store_n(&running,-1,__ATOMIC_RELEASE);
   if(received!=0&&__atomic_load_n(&running,__ATOMIC_ACQUIRE)==2&&lref_port_listen())__atomic_store_n(&running,-1,__ATOMIC_RELEASE);
   frame_job job;if(__atomic_load_n(&running,__ATOMIC_ACQUIRE)==2&&xQueueReceive(frames,&job,0)==pdTRUE){
    if(job.generation!=applied_generation){__atomic_fetch_add(&skipped,1,__ATOMIC_RELAXED);continue;}
    memset(&e,0,sizeof(e));e.kind=1;e.seq=job.seq;e.frame=job;e.config=current;e.at=ms();uint64_t delay=e.at-job.sampled;
    if(delay>UINT32_MAX){__atomic_fetch_add(&skipped,1,__ATOMIC_RELAXED);continue;}
    lrn1_set_delay(e.frame.bytes,job.len,(uint32_t)delay);
    __atomic_fetch_add(&attempted,1,__ATOMIC_RELAXED);int r=lref_port_tx(e.frame.bytes,e.frame.len,&e.toa);e.result=r?-1:0;if(r)__atomic_store_n(&running,-1,__ATOMIC_RELEASE);
    if(!r){lref_port_health((uint16_t*)&health_vbat_mv,(int16_t*)&health_temp_c);fc_report_sent(&control,job.seq,ms());__atomic_fetch_add(&submitted,1,__ATOMIC_RELAXED);emit_event(&e);uint64_t stop=ms()+e.toa+1500;int done=0;while(ms()<stop){done=lref_port_tx_done();worker_progress_step();if(done)break;vTaskDelay(pdMS_TO_TICKS(5)+1);}e.done=ms();e.result=done==1?1:done<0?-1:2;if(done==1){__atomic_fetch_add(&completed,1,__ATOMIC_RELAXED);if(lref_port_listen())__atomic_store_n(&running,-1,__ATOMIC_RELEASE);}else{lref_port_off();__atomic_store_n(&running,-1,__ATOMIC_RELEASE);}}
    emit_event(&e);
   }}
  if(__atomic_load_n(&running,__ATOMIC_ACQUIRE)==-1&&current.role&&applied_generation){
   if(!fault_seen){fault_seen=1;lref_port_off();xQueueReset(frames);lref_recovery_fault(&recovery,ms());__atomic_store_n(&recovery_state,1,__ATOMIC_RELEASE);}
   int rr=lref_recovery_tick(&recovery,ms(),recover_apply,&current);
   if(rr){__atomic_fetch_add(&recovery_attempted,1,__ATOMIC_RELAXED);if(rr==1){__atomic_fetch_add(&recovery_success,1,__ATOMIC_RELAXED);__atomic_store_n(&running,(int)current.role,__ATOMIC_RELEASE);__atomic_store_n(&recovery_state,0,__ATOMIC_RELEASE);fault_seen=0;}else if(rr==-2){__atomic_fetch_add(&recovery_exhausted,1,__ATOMIC_RELAXED);__atomic_store_n(&recovery_state,2,__ATOMIC_RELEASE);}else __atomic_store_n(&recovery_state,1,__ATOMIC_RELEASE);
    memset(&e,0,sizeof(e));e.kind=3;e.seq=applied_generation;e.result=rr;e.at=ms();e.config=current;emit_event(&e);}
  }
  worker_progress_step();vTaskDelay(pdMS_TO_TICKS(5)+1);
 }
}
/* Called only by the main task; retain successfully allocated queues and never
 * create a second worker. Failed starts are retried by the bounded scheduler. */
static int spawn_worker(void*unused){(void)unused;if(task_started)return 0;task_start_attempts++;
 if(!settings)settings=xQueueCreate(1,sizeof(config_job));
 if(!frames)frames=xQueueCreate(1,sizeof(frame_job));
 if(!events)events=xQueueCreate(8,sizeof(ref_event));
 if(!settings||!frames||!events){task_start_failures++;return -1;}
 config_job initial={.config=cfg,.generation=generation};if(boot_suppressed)initial.config.role=0;
 if(xQueueOverwrite(settings,&initial)!=pdTRUE||xTaskCreate(worker,"lr_ref",6144,NULL,3,NULL)!=pdPASS){task_start_failures++;return -1;}
 __atomic_store_n(&task_started,1,__ATOMIC_RELEASE);return 0;
}
#ifndef LREF_WORKER_TEST
static int valid(const lref_config*c){return c->magic==0x3146524c&&c->role<=2&&c->period>=1000&&c->period<=3600000&&c->jitter<=1000&&c->jitter<=c->period/4&&c->frequency>=410000000&&c->frequency<=493000000&&(c->bw==125000||c->bw==250000||c->bw==500000)&&c->sf>=7&&c->sf<=12&&c->cr>=5&&c->cr<=8&&c->preamble>=8&&c->preamble<=64&&(c->sync==18||c->sync==52)&&c->power==0&&c->start<=1&&c->period>=lref_toa(c,208)+100+c->jitter;}
void lora_ref_init(mid_id self,uint32_t boot){identity=self;own_boot=boot;fc_init(&control,self.mac,boot);nvs_handle_t h;lref_config saved;size_t size=sizeof(saved);if(nvs_open("lr_ref",NVS_READONLY,&h)==ESP_OK){esp_err_t r=nvs_get_blob(h,"cfg",&saved,&size);nvs_close(h);if(r==ESP_OK&&size==sizeof(saved)&&valid(&saved)){cfg=saved;}}
 generation=1;boot_suppressed=!cfg.start&&cfg.role!=0;__atomic_store_n(&watch_requested,cfg.role!=0&&!boot_suppressed,__ATOMIC_RELEASE);due=ms()+1000+((boot^((uint32_t)self.mac[4]<<8)^self.mac[5])%cfg.period);lref_recovery_reset(&task_recovery);if(spawn_worker(NULL)){running=-1;lref_recovery_fault(&task_recovery,ms());}
}
static int overlay(cJSON*j,const char*key,uint32_t*out){cJSON*v=cJSON_GetObjectItemCaseSensitive(j,key);if(!v)return 0;if(!cJSON_IsNumber(v)||v->valuedouble<0||v->valuedouble>UINT32_MAX||(double)(uint32_t)v->valuedouble!=v->valuedouble)return -1;*out=(uint32_t)v->valuedouble;return 0;}
int lora_ref_command(cJSON*j,const char*name,const char**why){
 if(!strcmp(name,"lora_ref_status"))return 1;
 if(strcmp(name,"lora_ref_config"))return -1;
 if(!settings||!frames||!events){*why="lora_task_unavailable";return 0;}
 lref_config c=cfg;cJSON*r=cJSON_GetObjectItemCaseSensitive(j,"role");if(r){if(!cJSON_IsString(r)){*why="invalid_lora_role";return 0;}if(!strcmp(r->valuestring,"off"))c.role=0;else if(!strcmp(r->valuestring,"rx"))c.role=1;else if(!strcmp(r->valuestring,"tx"))c.role=2;else{*why="invalid_lora_role";return 0;}}
 if(overlay(j,"report_period_ms",&c.period)||overlay(j,"jitter_ms",&c.jitter)||overlay(j,"frequency_hz",&c.frequency)||overlay(j,"sf",&c.sf)||overlay(j,"bandwidth_hz",&c.bw)||overlay(j,"coding_rate",&c.cr)||overlay(j,"preamble_symbols",&c.preamble)||overlay(j,"sync_word",&c.sync)){*why="invalid_lora_number";return 0;}
 uint32_t power=0;if(overlay(j,"tx_power_dbm",&power)||power){*why="pilot_supports_only_nominal_0dBm";return 0;}
 cJSON*start=cJSON_GetObjectItemCaseSensitive(j,"start_on_boot");if(start){if(!cJSON_IsBool(start)){*why="invalid_lora_boot_policy";return 0;}c.start=cJSON_IsTrue(start);}
 if(!valid(&c)){*why="invalid_lora_config_or_period_below_ToA";return 0;}
 nvs_handle_t h;esp_err_t err=nvs_open("lr_ref",NVS_READWRITE,&h);if(err!=ESP_OK){*why="lora_nvs_open";return 0;}err=nvs_set_blob(h,"cfg",&c,sizeof(c));if(err==ESP_OK)err=nvs_commit(h);nvs_close(h);if(err!=ESP_OK){*why="lora_nvs_write";return 0;}
 cfg=c;boot_suppressed=0;__atomic_store_n(&watch_requested,cfg.role!=0,__ATOMIC_RELEASE);uint32_t gen=__atomic_add_fetch(&generation,1,__ATOMIC_RELEASE);config_job job={.config=cfg,.generation=gen};xQueueReset(frames);xQueueOverwrite(settings,&job);due=ms()+1000+(esp_random()%cfg.period);return 1;
}
void lora_ref_status(cJSON*j){static const char*names[]={"off","rx","tx"};cJSON_AddStringToObject(j,"lora_ref_requested_role",names[cfg.role]);cJSON_AddNumberToObject(j,"lora_ref_worker_state",__atomic_load_n(&running,__ATOMIC_ACQUIRE));cJSON_AddBoolToObject(j,"start_on_boot",cfg.start);cJSON_AddBoolToObject(j,"boot_role_suppressed",boot_suppressed);cJSON_AddNumberToObject(j,"requested_generation",__atomic_load_n(&generation,__ATOMIC_ACQUIRE));cJSON_AddNumberToObject(j,"applied_generation",__atomic_load_n(&applied_version,__ATOMIC_ACQUIRE));cJSON_AddNumberToObject(j,"report_period_ms",cfg.period);cJSON_AddNumberToObject(j,"jitter_ms",cfg.jitter);cJSON_AddNumberToObject(j,"frequency_hz",cfg.frequency);cJSON_AddNumberToObject(j,"tx_power_dbm",cfg.power);cJSON_AddNumberToObject(j,"sync_word",cfg.sync);cJSON_AddNumberToObject(j,"preamble_symbols",cfg.preamble);cJSON_AddNumberToObject(j,"sf",cfg.sf);cJSON_AddNumberToObject(j,"bandwidth_hz",cfg.bw);cJSON_AddNumberToObject(j,"coding_rate",cfg.cr);cJSON_AddNumberToObject(j,"max_frame_toa_ms",lref_toa(&cfg,208));cJSON_AddNumberToObject(j,"lora_chip_type",lref_chip_type);cJSON_AddNumberToObject(j,"lora_chip_fw",lref_chip_fw);cJSON_AddNumberToObject(j,"lora_chip_errors",lref_chip_errors);cJSON_AddNumberToObject(j,"lora_ref_rx_frames",__atomic_load_n(&rx_ok,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"lora_ref_last_rx_ms",(double)__atomic_load_n(&last_rx_ms,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"attempted",__atomic_load_n(&attempted,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"submitted",__atomic_load_n(&submitted,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"tx_done",__atomic_load_n(&completed,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"skipped",__atomic_load_n(&skipped,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"rx_bad",__atomic_load_n(&rx_bad,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"event_drops",__atomic_load_n(&event_drops,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"control_executed",__atomic_load_n(&control.executed,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"control_duplicates",__atomic_load_n(&control.duplicates,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"control_rejected",__atomic_load_n(&control.rejected,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"control_cache_full",__atomic_load_n(&control.full,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"control_ack_submitted",__atomic_load_n(&control_ack_submitted,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"control_ack_tx_done",__atomic_load_n(&control_ack_done,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"control_ack_failed",__atomic_load_n(&control_ack_failed,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"recovery_state",__atomic_load_n(&recovery_state,__ATOMIC_ACQUIRE));cJSON_AddNumberToObject(j,"recovery_attempted",__atomic_load_n(&recovery_attempted,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"recovery_success",__atomic_load_n(&recovery_success,__ATOMIC_RELAXED));cJSON_AddNumberToObject(j,"recovery_exhausted",__atomic_load_n(&recovery_exhausted,__ATOMIC_RELAXED));cJSON_AddBoolToObject(j,"worker_created",task_started);cJSON_AddBoolToObject(j,"worker_task_wdt_registered",__atomic_load_n(&worker_wdt_registered,__ATOMIC_ACQUIRE));cJSON_AddNumberToObject(j,"worker_start_attempts",task_start_attempts);cJSON_AddNumberToObject(j,"worker_start_failures",task_start_failures);}
static void id_text(char*s,mid_id id){snprintf(s,18,"%02x:%02x:%02x:%02x:%02x:%02x",id.mac[0],id.mac[1],id.mac[2],id.mac[3],id.mac[4],id.mac[5]);}
cJSON*lora_ref_tick(nd_node*n,mt_node*m,uint64_t now,int(*allowed)(mid_id)){
 if(!task_started)(void)lref_recovery_tick(&task_recovery,now,spawn_worker,NULL);
 if(cfg.role==2&&__atomic_load_n(&running,__ATOMIC_ACQUIRE)==2&&now>=due){uint32_t span=2*cfg.jitter+1;due=now+cfg.period-cfg.jitter+(esp_random()%span);if(sequence==UINT32_MAX||!n->boot||!n->group)__atomic_fetch_add(&skipped,1,__ATOMIC_RELAXED);else{frame_job job={.seq=++sequence,.generation=__atomic_load_n(&generation,__ATOMIC_ACQUIRE),.sampled=now};job.len=capture(n,m,now,allowed,job.bytes,job.seq);if(xQueueSend(frames,&job,0)!=pdTRUE)__atomic_fetch_add(&skipped,1,__ATOMIC_RELAXED);}}
 ref_event e;if(!events||xQueueReceive(events,&e,0)!=pdTRUE)return NULL;
 if(e.kind==0&&rx_sequence==UINT32_MAX){__atomic_fetch_add(&event_drops,1,__ATOMIC_RELAXED);return NULL;}
 cJSON*j=cJSON_CreateObject();cJSON_AddStringToObject(j,"schema","lora.ref.v1");cJSON_AddStringToObject(j,"event",e.kind==0?"lora_ref_rx":e.kind==1?"lora_ref_tx":e.kind==2?"lora_ref_config_applied":"lora_ref_recovery");char mac[18];id_text(mac,identity);
 cJSON_AddStringToObject(j,e.kind==0?"gateway_id":"observer_id",mac);cJSON_AddNumberToObject(j,e.kind==0?"gateway_boot":"observer_boot",own_boot);
 if(e.kind==0){char hex[417];for(unsigned i=0;i<e.frame.len;i++)snprintf(hex+2*i,3,"%02x",e.frame.bytes[i]);hex[2*e.frame.len]=0;cJSON_AddStringToObject(j,"frame_hex",hex);cJSON_AddNumberToObject(j,"rx_seq",++rx_sequence);cJSON_AddNumberToObject(j,"received_at_ms",(double)e.at);cJSON*radio=cJSON_AddObjectToObject(j,"lora");cJSON_AddNumberToObject(radio,"frequency_hz",e.config.frequency);cJSON_AddNumberToObject(radio,"sf",e.config.sf);cJSON_AddNumberToObject(radio,"bandwidth_hz",e.config.bw);cJSON_AddNumberToObject(radio,"coding_rate",e.config.cr);cJSON_AddNumberToObject(radio,"preamble_symbols",e.config.preamble);cJSON_AddNumberToObject(radio,"sync_word",e.config.sync);cJSON_AddNumberToObject(radio,"rssi_dbm",e.rssi);cJSON_AddNumberToObject(radio,"snr_db",e.snr);}
 else if(e.kind==1){cJSON_AddNumberToObject(j,"report_seq",e.seq);cJSON_AddNumberToObject(j,"frame_bytes",e.frame.len);cJSON_AddNumberToObject(j,"snapshot_at_ms",(double)e.frame.sampled);cJSON_AddNumberToObject(j,"tx_started_ms",(double)e.at);if(e.done)cJSON_AddNumberToObject(j,"tx_done_ms",(double)e.done);else cJSON_AddNullToObject(j,"tx_done_ms");cJSON_AddNumberToObject(j,"predicted_toa_ms",e.toa);cJSON_AddStringToObject(j,"result",e.result==0?"submitted":e.result==1?"tx_done":e.result==2?"timeout":"driver_error");lora_ref_status(j);}
 else if(e.kind==2){cJSON_AddBoolToObject(j,"ok",e.result==0);cJSON_AddNumberToObject(j,"applied_at_ms",(double)e.at);cJSON_AddNumberToObject(j,"generation",e.seq);cJSON_AddNumberToObject(j,"applied_role",e.config.role);cJSON_AddNumberToObject(j,"applied_period_ms",e.config.period);lora_ref_status(j);}else{cJSON_AddStringToObject(j,"result",e.result==1?"restored":e.result==-2?"exhausted":"retry_failed");cJSON_AddNumberToObject(j,"generation",e.seq);cJSON_AddNumberToObject(j,"at_ms",(double)e.at);lora_ref_status(j);}
 return j;
}
#endif

/* Values the frame builder can read without touching the radio. */
void lora_ref_health(uint16_t* vbat_mv, int16_t* temp_c, int32_t* tx_power_dbm, uint8_t* sf) {
	if (vbat_mv) *vbat_mv = __atomic_load_n(&health_vbat_mv, __ATOMIC_RELAXED);
	if (temp_c) *temp_c = __atomic_load_n(&health_temp_c, __ATOMIC_RELAXED);
	if (tx_power_dbm) *tx_power_dbm = cfg.power;
	if (sf) *sf = (uint8_t)cfg.sf;
}
