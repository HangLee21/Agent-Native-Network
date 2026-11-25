/* MID bounded candidate execution adapter, ESP-IDF 5.5.1. No ANN/ACK logic. */
#include "mid.h"
#include "lrn1_frame.h"
#include "deployment.h"
#include "neighbors.h"
#include "source_route.h"
#include "telemetry.h"
#include "field.h"
#include "bridge.h"
#include "field_ip.h"
#include "node_identity.h"
#include "reliable.h"
#include "reliable_route.h"
#include "peer_manager.h"
#include "boot_catalog.h"
#include "route_config_store.h"
#include "progress_health.h"
#include "lora_ref/lora_ref.h"
#include <math.h>
#include "mid_display.h"
#include <stdio.h>
#include <string.h>
#include <limits.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_attr.h"
#include "esp_task_wdt.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "cJSON.h"
#include "driver/uart.h"
#include "driver/uart_vfs.h"
static uint8_t channel=6;
#define CHANNEL channel
#define SERIAL_MAX 1024
typedef struct {int type,len,ok,rssi_valid,rssi,channel_valid,rx_channel;uint32_t radio_epoch;uint64_t rx_at_ms;uint8_t mac[6];union {uint8_t data[250];char line[SERIAL_MAX+1];};} input;
typedef struct {mid_packet packet;mid_id next;uint64_t queued;} transmission;
static QueueHandle_t inputs,uart_events;
static volatile unsigned uart_fifo_overflows,uart_ring_overflows,uart_received_bytes;
static mid_node node;
static mid_id self;
static uint32_t boot,sequence,node_number;
static const char *node_number_source="unset";
static int active,radio,wifi_ready,waiting,stopping,locked;

/* Link-layer radio selection. Persisted so a flashed board can be switched by the Pi
 * without reflashing. "espnow" is the only implemented backend for now; "lora24" is
 * accepted and stored, and reports as pending until that backend is built. */
static char link_mode[8]="espnow";
static int link_mode_loaded;
static void link_mode_load(void){
 if(link_mode_loaded)return;
 link_mode_loaded=1;
 nvs_handle_t h;if(nvs_open("link",NVS_READONLY,&h)!=ESP_OK)return;
 char v[8]={0};size_t n=sizeof(v);
 if(nvs_get_str(h,"mode",v,&n)==ESP_OK&&(!strcmp(v,"espnow")||!strcmp(v,"lora24")))snprintf(link_mode,sizeof(link_mode),"%s",v);
 nvs_close(h);
}
static int link_mode_save(const char*v){
 nvs_handle_t h;if(nvs_open("link",NVS_READWRITE,&h)!=ESP_OK)return -1;
 esp_err_t r=nvs_set_str(h,"mode",v);if(r==ESP_OK)r=nvs_commit(h);nvs_close(h);return r==ESP_OK?0:-1;
}
static const char*link_mode_active(void){return "espnow";}
static uint32_t radio_epoch;
static RTC_NOINIT_ATTR hg_record health_record;
static uint32_t main_progress,health_restarts;static int health_state,health_started,main_wdt_registered,health_wdt_registered,task_wdt_configured,task_wdt_panic;static uint64_t health_start_due,task_wdt_retry_due;
static pm_state radio_peers;
static bc_catalog observed_boots;
_Static_assert(PM_UNICAST_SLOTS+1<=ESP_NOW_MAX_TOTAL_PEER_NUM,"ESP-NOW peer limit");
static volatile unsigned callback_drops;
static transmission pending,txq[16];static unsigned head,count;
static uint64_t submitted,last_publish;static int applied_pending;
static mid_display_snapshot screen;
static mid_deployment deployment;
static int have_deployment, deployment_fault;
static nd_node neighbors;
static int have_discovery, discovery_autostart, discovery_fault,discovery_from_backup;
static unsigned discovery_backup_write_failures;
static int discovery_backup_confirmed;static uint64_t discovery_backup_retry;
static uint32_t discovery_group;
static uint64_t hello_due, probe_after;
/* Bounded radio self-heal. A send callback that never arrives used to latch
 * `locked` until a physical reset, which is fatal for an unattended mobile node.
 * stop_all() has already deinited ESP-NOW before this runs, so no stale callback
 * can be matched to a later send; HEAL_MAX caps a genuinely broken radio. */
#define HEAL_MAX 3u
/* The budget must refill: a bursty minute was measured to burn all three attempts and
 * leave a healthy board locked until a physical reset. */
#define HEAL_WINDOW_MS 120000u
#define HEAL_DELAY_MS 3000u
static unsigned heal_attempts;static uint64_t heal_at;static uint64_t heal_window;static unsigned input_overflow_total;static uint64_t last_rx_ms;static unsigned callback_timeouts;
static unsigned control_submitted,control_link_ok,control_link_fail;
static sr_node router;static sr_out route_pending;static int route_mode,route_waiting;
static unsigned route_submitted,route_link_ok,route_link_fail;
static uint64_t route_process_us,route_process_max_us;
static mt_node mobile;static int telemetry_enabled=0,telemetry_waiting;static uint32_t telemetry_period=10000;
static uint64_t telemetry_due;static unsigned telemetry_generated,telemetry_submitted,telemetry_link_ok,telemetry_link_fail,telemetry_deferred;
static fa_node agent;static fg_node bridge_state;static uint32_t field_last_seq;
typedef struct {uint32_t magic,pc_id,report_period_ms;int agent_to_pc;} gateway_cfg;
typedef struct {uint32_t magic,boot,segment;uint64_t uptime;uint32_t totals[5],segment_counts[5],overwritten,late,origins_full;char note[32];} field_summary;
typedef struct {int used;uint32_t transaction,session;mid_id dst;uint64_t until;} field_query;
typedef struct {int used;mid_id id;uint64_t at;} field_catalog_row;
static field_catalog_row observed_ids[8];static unsigned observed_full;
static gateway_cfg gateway;static field_query ip_queries[8];static uint64_t checkpoint_due,checkpoint_attempt,report_due;static unsigned checkpoint_writes,checkpoint_failures,report_sequence,report_row,gateway_control_submitted,gateway_control_received,gateway_control_bytes,ip_direct_generated,gateway_rejected;
static void field_observe(const char*,const mid_packet*);static void field_display(void);static void field_gateway_receive(const sr_event*);static void field_route_event(const sr_event*);
static void route_events(void);
static void route_tick(void);
static int filter_enabled;static mid_id filter_allow[8];static unsigned filter_count;
static int allowed(mid_id id){if(!filter_enabled||id.mac[0]==255)return 1;for(unsigned i=0;i<filter_count;i++)if(mid_equal(id,filter_allow[i]))return 1;return 0;}
static uint64_t millis(void){return (uint64_t)esp_timer_get_time()/1000;}
static int task_watchdog_config(int panic_enabled){uint32_t mask=0;
#if CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU0
 mask|=1u;
#endif
#if CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU1
 mask|=2u;
#endif
 esp_task_wdt_config_t c={.timeout_ms=30000,.idle_core_mask=mask,.trigger_panic=panic_enabled!=0};esp_err_t r=esp_task_wdt_reconfigure(&c);if(r==ESP_ERR_INVALID_STATE)r=esp_task_wdt_init(&c);if(r!=ESP_OK)return -1;__atomic_store_n(&task_wdt_configured,1,__ATOMIC_RELEASE);__atomic_store_n(&task_wdt_panic,panic_enabled!=0,__ATOMIC_RELEASE);return 0;}
static void startup_wait(uint32_t duration){while(duration){uint32_t chunk=duration>5000?5000:duration;vTaskDelay(pdMS_TO_TICKS(chunk));if(main_wdt_registered)(void)esp_task_wdt_reset();duration-=chunk;}}
static void health_worker(void*unused){(void)unused;hg_state state={0};uint64_t retry=0;for(;;){uint64_t now=millis();if(!__atomic_load_n(&health_wdt_registered,__ATOMIC_ACQUIRE)&&now>=retry){if(esp_task_wdt_add(NULL)==ESP_OK||esp_task_wdt_status(NULL)==ESP_OK)__atomic_store_n(&health_wdt_registered,1,__ATOMIC_RELEASE);else retry=now+5000;}int result=hg_tick(&state,&health_record,now,__atomic_load_n(&main_progress,__ATOMIC_ACQUIRE),lora_ref_progress(),lora_ref_watch_enabled());__atomic_store_n(&health_state,result,__ATOMIC_RELEASE);__atomic_store_n(&health_restarts,health_record.count,__ATOMIC_RELEASE);if(!health_record.count&&!__atomic_load_n(&task_wdt_panic,__ATOMIC_ACQUIRE)&&__atomic_load_n(&task_wdt_configured,__ATOMIC_ACQUIRE))(void)task_watchdog_config(1);if(result==HG_RESTART_MAIN){hg_mark_restart(&health_record);esp_restart();}if(__atomic_load_n(&health_wdt_registered,__ATOMIC_ACQUIRE))(void)esp_task_wdt_reset();vTaskDelay(pdMS_TO_TICKS(1000));}}
static void health_start_tick(void){uint64_t now=millis();if(now>=task_wdt_retry_due&&(!__atomic_load_n(&task_wdt_configured,__ATOMIC_ACQUIRE)||!main_wdt_registered)){if(!__atomic_load_n(&task_wdt_configured,__ATOMIC_ACQUIRE))(void)task_watchdog_config(__atomic_load_n(&health_restarts,__ATOMIC_ACQUIRE)<HG_MAX_RESTARTS);if(__atomic_load_n(&task_wdt_configured,__ATOMIC_ACQUIRE)&&!main_wdt_registered)main_wdt_registered=esp_task_wdt_add(NULL)==ESP_OK||esp_task_wdt_status(NULL)==ESP_OK;task_wdt_retry_due=now+10000;}if(health_started||now<health_start_due)return;if(xTaskCreate(health_worker,"mid_health",4096,NULL,2,NULL)==pdPASS)health_started=1;else health_start_due=now+10000;}
static void mac_text(mid_id id,char out[18]){snprintf(out,18,"%02x:%02x:%02x:%02x:%02x:%02x",id.mac[0],id.mac[1],id.mac[2],id.mac[3],id.mac[4],id.mac[5]);}
static void field_id(cJSON*j,const char*key,mid_id id){char s[18];mac_text(id,s);cJSON_AddStringToObject(j,key,s);}
static void node_number_load(void){
 node_number=node_identity_default(self.mac);node_number_source=node_number?"factory_map":"unset";
 nvs_handle_t h;esp_err_t r=nvs_open("node_ident",NVS_READONLY,&h);if(r==ESP_ERR_NVS_NOT_FOUND)return;
 if(r!=ESP_OK){node_number=0;node_number_source="nvs_error";return;}
 uint32_t saved=0;r=nvs_get_u32(h,"id",&saved);nvs_close(h);
 if(r==ESP_ERR_NVS_NOT_FOUND)return;
 if(r!=ESP_OK||!saved){node_number=0;node_number_source="nvs_error";return;}
 node_number=saved;node_number_source="nvs";
}
static int node_number_store(uint32_t value){
 nvs_handle_t h;esp_err_t r=nvs_open("node_ident",NVS_READWRITE,&h);if(r!=ESP_OK)return -1;
 r=nvs_set_u32(h,"id",value);if(r==ESP_OK)r=nvs_commit(h);nvs_close(h);if(r!=ESP_OK)return -1;
 node_number=value;node_number_source="nvs";screen.identity.node_id=value;return 0;
}
static void node_number_json(cJSON*j){
 field_id(j,"node_mac",self);if(node_number)cJSON_AddNumberToObject(j,"node_number",node_number);else cJSON_AddNullToObject(j,"node_number");
 cJSON_AddStringToObject(j,"node_number_source",node_number_source);cJSON_AddStringToObject(j,"node_number_schema","node.number.v1");
}
/* Strong definition of the hook the LRN1 builder asks for: the node number travels in the
 * air so the gateway can name a node without any roster file or Pi being reachable. */
uint32_t lrn1_node_number(void){return node_number;}
/* Health that the node can answer on its own. Reset reason is what distinguishes "the bench
 * lost power" from "the firmware died", and until now it only reached a serial log. */
void lrn1_platform_status(lrn1_status* s){
 if(!s)return;
 esp_reset_reason_t r=esp_reset_reason();
 s->reset_reason = r==ESP_RST_POWERON?LRN1_RST_POWERON
                 : r==ESP_RST_BROWNOUT?LRN1_RST_BROWNOUT
                 : (r==ESP_RST_TASK_WDT||r==ESP_RST_INT_WDT||r==ESP_RST_WDT)?LRN1_RST_WATCHDOG
                 : r==ESP_RST_PANIC?LRN1_RST_PANIC
                 : r==ESP_RST_SW?LRN1_RST_SOFTWARE:LRN1_RST_UNKNOWN;
 { uint32_t kb=esp_get_free_heap_size()/1024u; s->heap_free_kb=(uint8_t)(kb>255u?255u:kb); }
 /* The ESP-NOW channel the mesh actually runs on. The driver does not report a per-packet
  * channel for ESP-NOW, so this is the only reliable channel value we have. */
 s->wifi_channel=channel;
 /* Routing health: an operator asking "is the mesh keeping up" wants these three. */
 { unsigned used=0;for(unsigned i=0;i<SR_ROUTES;i++)if(router.routes[i].used)used++;
   s->routes=(uint8_t)(used>255u?255u:used); }
 { uint32_t q=router.count; s->queue_depth=(uint8_t)(q>255u?255u:q); }
 { uint32_t d=router.overflows; s->tx_drops=(uint8_t)(d>255u?255u:d); }
 /* Supply and die temperature come from the radio itself (worker sampled them). */
 { uint16_t mv=0;int16_t tc=-128;int32_t pwr=0;uint8_t sf=0;
   lora_ref_health(&mv,&tc,&pwr,&sf);
   s->supply_mv=mv; s->die_temp_c=(int8_t)tc; s->lora_sf=sf;
   s->lora_tx_power_dbm=(int8_t)(pwr<-128?(-128):(pwr>127?127:pwr)); }
 /* Cumulative-style flags: brownout at boot, and a neighbour table that is full right now. */
 s->fault_flags=(uint8_t)((s->reset_reason==LRN1_RST_BROWNOUT?LRN1_FAULT_UNDERVOLTAGE:0u)
                        | (neighbors.full?LRN1_FAULT_TABLE_FULL:0u));
}

static cJSON* event(const char*kind){cJSON*j=cJSON_CreateObject();cJSON_AddStringToObject(j,"schema","mid.serial.v1");cJSON_AddStringToObject(j,"event",kind);field_id(j,"node_id",self);cJSON_AddNumberToObject(j,"boot_id",boot);cJSON_AddStringToObject(j,"build_id",MID_BUILD_ID);cJSON_AddNumberToObject(j,"monotonic_ms",(double)millis());return j;}
/* A host that stops reading the UART must never stall the mesh: puts() blocks once the
 * 4 KB TX ring is full, which starved the input queue and (before the overflow fix) could
 * latch the radio. Events are therefore dropped - and counted - when the ring is nearly
 * full, instead of blocking the receive path. */
static unsigned uart_tx_drops;
static int uart_can_write(size_t need){
 size_t free_tx=0;
 if(uart_get_tx_buffer_free_size(UART_NUM_0,&free_tx)!=ESP_OK)return 1;
 return free_tx>=need;
}
static void output(cJSON*j){char*s=cJSON_PrintUnformatted(j);if(s){size_t n=strlen(s)+2;if(!uart_can_write(n)){uart_tx_drops++;cJSON_free(s);cJSON_Delete(j);return;}puts(s);cJSON_free(s);}cJSON_Delete(j);}
static unsigned flow_of(const mid_packet*p){mid_id dst;if(p->kind!=2||p->size<6)return UINT_MAX;memcpy(dst.mac,p->body,6);for(unsigned f=0;f<node.table.k;f++)if(mid_equal(p->origin,node.table.nodes[node.table.src[f]])&&mid_equal(dst,node.table.nodes[node.table.dst[f]]))return f;return UINT_MAX;}
static void observation(const char*name,mid_display_event_kind kind,const mid_packet*p,const mid_id*next,int code){
 mid_display_event d={.kind=kind,.at_ms=millis(),.code=code};cJSON*j=event(name);cJSON_AddNumberToObject(j,"code",code);
 if(p){field_id(j,"origin",p->origin);cJSON_AddNumberToObject(j,"origin_boot",p->boot);cJSON_AddNumberToObject(j,"seq",p->seq);
  if(p->kind==1){memcpy(d.cfg_origin,p->origin.mac,6);d.cfg_seq=p->seq;d.cfg_valid=3;}
  else if(p->size>=6){mid_id dst;memcpy(dst.mac,p->body,6);field_id(j,"dst",dst);memcpy(d.dst,dst.mac,6);memcpy(d.ref.origin,p->origin.mac,6);d.ref.boot=p->boot;d.ref.seq=p->seq;d.ref.valid=7;unsigned f=flow_of(p);if(f!=UINT_MAX){d.ref.flow=f;d.ref.valid|=8;cJSON_AddNumberToObject(j,"flow",f);}if(kind==MID_DISPLAY_EV_RX_DEST){char hex[321];unsigned n=p->size-6;for(unsigned i=0;i<n;i++)snprintf(hex+2*i,3,"%02x",p->body[6+i]);hex[2*n]=0;cJSON_AddStringToObject(j,"payload_hex",hex);}}
 }
 if(next){field_id(j,"next_hop",*next);memcpy(d.next_hop,next->mac,6);}
 cJSON_AddBoolToObject(j,"destination_confirmed",false);output(j);
 if(kind){(void)mid_display_model_apply(&screen,&d);}
 field_observe(name,p);
}
static void status_display(void){field_display();mid_display_event d={.kind=MID_DISPLAY_EV_STATUS,.at_ms=millis(),.mode=active?((have_discovery||node.have_table)?MID_DISPLAY_ACTIVE:MID_DISPLAY_WAIT_CONFIG):MID_DISPLAY_IDLE,.routes=0};if(node.have_table)for(unsigned f=0;f<node.table.k;f++)if(node.next[f]>=0)d.routes++;(void)mid_display_model_apply(&screen,&d);if(millis()-last_publish>=250){(void)mid_display_publish(&screen);last_publish=millis();}}
static void receive_cb(const esp_now_recv_info_t*info,const uint8_t*data,int len){if(!info||!data||len<1)return;input e={.type=1,.len=len,.radio_epoch=__atomic_load_n(&radio_epoch,__ATOMIC_ACQUIRE),.rx_at_ms=(uint64_t)esp_timer_get_time()/1000};if(info->rx_ctrl){e.rssi_valid=1;e.rssi=info->rx_ctrl->rssi;e.rx_channel=info->rx_ctrl->channel;e.channel_valid=e.rx_channel>=1&&e.rx_channel<=14;}memcpy(e.mac,info->src_addr,6);memcpy(e.data,data,(size_t)(len>250?250:len));if(xQueueSend(inputs,&e,0)!=pdTRUE)__atomic_fetch_add(&callback_drops,1,__ATOMIC_RELAXED);}
static void send_cb(const esp_now_send_info_t*info,esp_now_send_status_t s){if(!info)return;input e={.type=2,.ok=s==ESP_NOW_SEND_SUCCESS,.radio_epoch=__atomic_load_n(&radio_epoch,__ATOMIC_ACQUIRE)};memcpy(e.mac,info->des_addr,6);if(xQueueSend(inputs,&e,0)!=pdTRUE)__atomic_fetch_add(&callback_drops,1,__ATOMIC_RELAXED);}
static int pm_exists(void*ctx,const uint8_t mac[6]){(void)ctx;return esp_now_is_peer_exist(mac);}
static int pm_add(void*ctx,const uint8_t mac[6]){(void)ctx;esp_now_peer_info_t p={.channel=CHANNEL,.ifidx=WIFI_IF_STA,.encrypt=false};memcpy(p.peer_addr,mac,6);return esp_now_add_peer(&p);}
static int pm_del(void*ctx,const uint8_t mac[6]){(void)ctx;return esp_now_del_peer(mac);}
static esp_err_t ensure_peer(const uint8_t mac[6]){const pm_ops ops={pm_exists,pm_add,pm_del,NULL};return pm_ensure(&radio_peers,&ops,mac,waiting)?ESP_FAIL:ESP_OK;}
/* Link-layer backends. Protocol code only calls link->send(); the radio that carries
 * the mesh is chosen at runtime from the persisted link_mode. */
static unsigned link_send_ok,link_send_fail,link_send_oversize;
typedef struct{const char*name;int(*send)(const uint8_t mac[6],const uint8_t*data,unsigned len);}link_backend;
static int espnow_link_send(const uint8_t mac[6],const uint8_t*data,unsigned len){
 if(len>208){link_send_oversize++;return -1;}
 esp_err_t r=ensure_peer(mac);
 if(r==ESP_OK)r=esp_now_send(mac,data,(size_t)len);
 if(r==ESP_OK)link_send_ok++;else link_send_fail++;
 return r==ESP_OK?0:-1;
}
static int lora24_link_send(const uint8_t mac[6],const uint8_t*data,unsigned len){
 (void)mac;
 if(len>208){link_send_oversize++;return -1;}
 if(lora_ref_link_send(data,len)){link_send_fail++;return -1;}
 link_send_ok++;
 return 0;
}
static const link_backend LINK_LORA24={"lora24",lora24_link_send};
static const link_backend LINK_ESPNOW={"espnow",espnow_link_send};
static const link_backend*link=&LINK_ESPNOW;
static esp_err_t radio_start(void){esp_err_t r;if(locked)return ESP_ERR_INVALID_STATE;
 /* lora24: the mesh rides on the LR1121 at 2.4 GHz instead of Wi-Fi/ESP-NOW, so the
  * Wi-Fi stack is deliberately not started. Link RX wiring is the next stage. */
 if(!strcmp(link_mode,"lora24")){link=&LINK_LORA24;radio=1;return ESP_OK;}if(!wifi_ready){wifi_init_config_t c=WIFI_INIT_CONFIG_DEFAULT();r=esp_netif_init();if(r!=ESP_OK)return r;r=esp_event_loop_create_default();if(r!=ESP_OK&&r!=ESP_ERR_INVALID_STATE)return r;field_ip_netif();r=esp_wifi_init(&c);if(r!=ESP_OK)return r;ESP_ERROR_CHECK_WITHOUT_ABORT(esp_wifi_set_storage(WIFI_STORAGE_RAM));r=esp_wifi_set_mode(WIFI_MODE_STA);if(r!=ESP_OK)return r;wifi_ready=1;}r=esp_wifi_start();if(r!=ESP_OK)return r;r=esp_wifi_set_ps(WIFI_PS_NONE);if(r==ESP_OK)(void)field_ip_pin(CHANNEL);if(r==ESP_OK)r=esp_wifi_set_channel(CHANNEL,WIFI_SECOND_CHAN_NONE);if(r==ESP_OK)r=esp_now_init();if(r!=ESP_OK){esp_wifi_stop();return r;}pm_init(&radio_peers);r=esp_now_register_recv_cb(receive_cb);if(r==ESP_OK)r=esp_now_register_send_cb(send_cb);if(r!=ESP_OK){esp_now_deinit();esp_wifi_stop();return r;}radio=1;return ESP_OK;}
static void close_radio(void){if(radio){__atomic_add_fetch(&radio_epoch,1,__ATOMIC_RELEASE);field_ip_unpin();esp_now_deinit();esp_wifi_stop();radio=0;}stopping=0;}
static void stop_all(void){if(route_mode){sr_stop(&router);route_events();}active=0;applied_pending=0;while(count){transmission*t=&txq[head];if(t->packet.kind==2)observation("tx_cancelled",MID_DISPLAY_EV_TX_LOCAL_FAIL,&t->packet,&t->next,-2);head=(head+1)%16;count--;}stopping=1;if(!waiting)close_radio();}
static int enqueue(mid_packet p,mid_id next){if(count==16){if(p.kind==2)observation("tx_queue_full",MID_DISPLAY_EV_TX_LOCAL_FAIL,&p,&next,-3);else observation("control_queue_full",0,&p,&next,-3);return -1;}txq[(head+count)%16]=(transmission){p,next,millis()};count++;if(p.kind==2)observation("tx_queued",MID_DISPLAY_EV_TX_QUEUED,&p,&next,0);return 0;}
/* A failed route send means the next hop is probably gone. Probe it immediately
 * instead of waiting for its next 2-3s HELLO (or the 9s ACK window) to demote it,
 * so a moved node is re-confirmed or demoted in milliseconds. Bounded by the same
 * 1/s gate as the explicit neighbor_probe command. */
static int neighbor_demand(mid_id id){
 if(!active||!have_discovery||!mid_unicast(id)||sequence==UINT32_MAX||count>=16||millis()<probe_after)return 0;
 if(!nd_find(&neighbors,id))return 0;
 mid_packet p;nd_hello(&neighbors,&p,++sequence);
 if(enqueue(p,id))return 0;
 probe_after=millis()+1000;return 1;
}
static int config_packet(mid_packet*p){int r;if(have_discovery||have_deployment||deployment_fault){observation("config_rejected_offline",MID_DISPLAY_EV_CFG_REJECTED,p,NULL,-1);return -1;}observation("config_rx",MID_DISPLAY_EV_CFG_RECEIVED,p,NULL,0);r=mid_config(&node,p);if(r==1){applied_pending=1;if(p->ttl>1){mid_packet forward=*p;mid_id broadcast={{255,255,255,255,255,255}};forward.ttl--;enqueue(forward,broadcast);}}
 else {observation(r==0?"config_stale":"config_rejected",r==0?MID_DISPLAY_EV_CFG_STALE:MID_DISPLAY_EV_CFG_REJECTED,p,NULL,r);}
 return r;}
static int data_packet(mid_packet*p,int received){mid_id next={{0}},dst;memcpy(dst.mac,p->body,6);int r;
 if(have_discovery){
  r=-1;if(!received&&nd_direct(&neighbors,dst,0,millis())){next=dst;r=1;}
  else if(received&&mid_equal(dst,self)){r=2;for(unsigned i=0;i<64;i++)if(node.seen[i].used&&mid_equal(node.seen[i].origin,p->origin)&&node.seen[i].boot==p->boot&&node.seen[i].seq==p->seq)r=0;if(r==2){node.seen[node.cursor]=(mid_seen){p->origin,p->boot,p->seq,1};node.cursor=(node.cursor+1)%64;}}
 }else r=mid_data(&node,p,&next);if(r==2)observation("rx_local",MID_DISPLAY_EV_RX_DEST,p,NULL,0);else if(r==0){if(mid_equal(dst,self))observation("rx_duplicate",MID_DISPLAY_EV_RX_DUPLICATE,p,NULL,0);}else if(r==1){if(received)observation("rx_relay",MID_DISPLAY_EV_RX_RELAY,p,NULL,0);if(received)p->ttl--;return enqueue(*p,next);}else observation("data_drop",0,p,NULL,-1);return r<0?-1:0;}
static int hexval(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
static int unhex(const char*s,uint8_t*out,size_t cap){if(!s)return -1;size_t n=strlen(s);if(n%2||n/2>cap)return -1;for(size_t i=0;i<n/2;i++){int a=hexval(s[2*i]),b=hexval(s[2*i+1]);if(a<0||b<0)return -1;out[i]=(uint8_t)((a<<4)|b);}return (int)(n/2);}
static int parse_id(const char*s,mid_id*out){char plain[13];if(!s||strlen(s)!=17)return -1;for(unsigned i=0;i<6;i++){plain[2*i]=s[3*i];plain[2*i+1]=s[3*i+1];if(i<5&&s[3*i+2]!=':')return -1;}plain[12]=0;return unhex(plain,out->mac,6)==6&&mid_unicast(*out)?0:-1;}
static const char*str(cJSON*j,const char*k){cJSON*v=cJSON_GetObjectItemCaseSensitive(j,k);return cJSON_IsString(v)?v->valuestring:NULL;}
static int u32(cJSON*j,const char*k,uint32_t*out){cJSON*v=cJSON_GetObjectItemCaseSensitive(j,k);if(!cJSON_IsNumber(v)||v->valuedouble<1||v->valuedouble>4294967295.0)return -1;*out=(uint32_t)v->valuedouble;return v->valuedouble==*out?0:-1;}
static int printable(const char*s){if(!s)return 0;size_t n=strlen(s);if(!n||n>64)return 0;for(size_t i=0;i<n;i++)if((unsigned char)s[i]<32||(unsigned char)s[i]>126)return 0;return 1;}
/* Only this namespace/key is written; never erase the NVS partition. */
static esp_err_t deployment_store(const mid_deployment*p){
 uint8_t blob[MID_DEPLOYMENT_BYTES];int n=mid_deployment_encode(p,self,blob,sizeof(blob));if(n<0)return ESP_ERR_INVALID_ARG;
 nvs_handle_t h;esp_err_t r=nvs_open("mid_deploy",NVS_READWRITE,&h);if(r!=ESP_OK)return r;
 r=nvs_set_blob(h,"profile",blob,(size_t)n);if(r==ESP_OK)r=nvs_commit(h);nvs_close(h);return r;
}
static esp_err_t deployment_delete(void){
 nvs_handle_t h;esp_err_t r=nvs_open("mid_deploy",NVS_READWRITE,&h);if(r!=ESP_OK)return r;
 r=nvs_erase_key(h,"profile");if(r==ESP_ERR_NVS_NOT_FOUND)r=ESP_OK;if(r==ESP_OK)r=nvs_commit(h);nvs_close(h);return r;
}
static esp_err_t deployment_load(void){
 nvs_handle_t h;esp_err_t r=nvs_open("mid_deploy",NVS_READONLY,&h);if(r==ESP_ERR_NVS_NOT_FOUND)return ESP_OK;if(r!=ESP_OK)return r;
 uint8_t blob[MID_DEPLOYMENT_BYTES];size_t n=sizeof(blob);r=nvs_get_blob(h,"profile",blob,&n);nvs_close(h);
 if(r==ESP_ERR_NVS_NOT_FOUND)return ESP_OK;
 if(r!=ESP_OK)return r;
 if(mid_deployment_decode(&deployment,self,blob,n))return ESP_ERR_INVALID_ARG;
 have_deployment=1;return ESP_OK;
}
static esp_err_t deployment_start(void){
 if(!have_deployment||deployment_fault||active||radio||waiting||locked)return ESP_ERR_INVALID_STATE;
 if(mid_deployment_install(&node,&deployment,self,millis()))return ESP_ERR_INVALID_ARG;
 link_mode_load();esp_err_t r=radio_start();if(r!=ESP_OK){node.have_table=0;return r;}active=1;
 cJSON*j=event("deployment_applied");cJSON_AddStringToObject(j,"deployment_mode","offline_table");cJSON_AddStringToObject(j,"profile_id",deployment.profile_id);cJSON_AddBoolToObject(j,"autostart",deployment.autostart);output(j);return ESP_OK;
}
static esp_err_t load_mode(const char*ns){
 nvs_handle_t h;esp_err_t r=nvs_open(ns,NVS_READONLY,&h);if(r==ESP_ERR_NVS_NOT_FOUND)return ESP_OK;if(r!=ESP_OK)return r;
 uint8_t primary[12]={0},backup[16]={0},b[12];size_t n=sizeof(primary),bn=sizeof(backup);r=nvs_get_blob(h,"cfg",primary,&n);int ps=r==ESP_OK?0:r==ESP_ERR_NVS_NOT_FOUND?1:2;esp_err_t br=nvs_get_blob(h,"lastgood",backup,&bn);int bs=br==ESP_OK?0:br==ESP_ERR_NVS_NOT_FOUND?1:2;nvs_close(h);int selected=rc_choose(ps,primary,n,bs,backup,bn,b);if(selected==2)return ESP_OK;if(selected<0)return ESP_ERR_INVALID_ARG;discovery_from_backup=selected==1;
 discovery_group=(uint32_t)b[4]|((uint32_t)b[5]<<8)|((uint32_t)b[6]<<16)|((uint32_t)b[7]<<24);if(!discovery_group)return ESP_ERR_INVALID_ARG;
 channel=b[8];discovery_autostart=b[9];have_discovery=1;return ESP_OK;
}
static esp_err_t discovery_load(void){esp_err_t r=load_mode("mid_route");if(r!=ESP_OK||have_discovery){route_mode=1;return r;}return load_mode("mid_neighbor");}
/* Called only after a peer confirms bidirectionally in this group/channel.
 * This is one-hop evidence, not proof of end-to-end reachability. */
static int discovery_checkpoint(void){uint8_t b[12]={'N','D','c','1',0,0,0,0,channel,(uint8_t)discovery_autostart,0,0},packed[16],old[16];for(unsigned i=0;i<4;i++)b[4+i]=(uint8_t)(discovery_group>>(8*i));if(rc_pack(b,packed))return -1;nvs_handle_t h;esp_err_t r=nvs_open(route_mode?"mid_route":"mid_neighbor",NVS_READWRITE,&h);if(r!=ESP_OK){discovery_backup_write_failures++;return -1;}size_t n=sizeof(old);r=nvs_get_blob(h,"lastgood",old,&n);if(r==ESP_OK&&n==sizeof(old)&&!memcmp(old,packed,sizeof(old))){nvs_close(h);return 0;}r=nvs_set_blob(h,"lastgood",packed,sizeof(packed));if(r==ESP_OK)r=nvs_commit(h);nvs_close(h);if(r!=ESP_OK){discovery_backup_write_failures++;return -1;}return 0;}
static esp_err_t discovery_start(void){
 if(!have_discovery||discovery_fault||have_deployment||deployment_fault||active||radio||waiting||locked)return ESP_ERR_INVALID_STATE;
 route_submitted=route_link_ok=route_link_fail=0;route_process_us=route_process_max_us=0;sr_init(&router,self,boot,discovery_group);bc_init(&observed_boots);if(mobile.group!=discovery_group){memset(mobile.rf,0,sizeof(mobile.rf));memset(mobile.peers,0,sizeof(mobile.peers));}mobile.group=discovery_group;telemetry_due=millis()+1000+esp_random()%1001;control_submitted=control_link_ok=control_link_fail=0;nd_init(&neighbors,self,boot,discovery_group);mid_init(&node,self,self,0);screen.identity.channel=channel;
 esp_err_t r=radio_start();if(r!=ESP_OK)return r;active=1;hello_due=millis()+esp_random()%501;discovery_backup_confirmed=0;discovery_backup_retry=0;return ESP_OK;
}
static void neighbor_fields(cJSON*j,nd_peer*p){
 if(!p){cJSON_AddStringToObject(j,"state","unknown");return;}
 field_id(j,"node_id",p->id);cJSON_AddNumberToObject(j,"boot_id",p->boot);int state=nd_state(p,millis());
 cJSON_AddStringToObject(j,"state",state==2?"bidirectional":state==1?"heard":"lost");cJSON_AddNumberToObject(j,"last_seen_ms",(double)p->seen);cJSON_AddNumberToObject(j,"age_ms",(double)(millis()-p->seen));
 if(p->confirmed)cJSON_AddNumberToObject(j,"last_confirmed_ms",(double)p->ack);else cJSON_AddNullToObject(j,"last_confirmed_ms");
 cJSON_AddStringToObject(j,"scope","one_hop");
}
static void discovery_tick(void){
 if(!discovery_backup_confirmed&&millis()>=discovery_backup_retry){for(unsigned i=0;i<ND_PEERS;i++)if(neighbors.peers[i].used&&nd_state(&neighbors.peers[i],millis())==2){if(!discovery_checkpoint())discovery_backup_confirmed=1;else discovery_backup_retry=millis()+5000;break;}}
 if(millis()>=hello_due&&sequence<UINT32_MAX&&count<16){mid_packet p;mid_id broadcast={{255,255,255,255,255,255}};nd_hello(&neighbors,&p,++sequence);enqueue(p,broadcast);hello_due=millis()+2000+esp_random()%1001;}
}
static const char*position_source(unsigned source){return source==1?"gnss":source==2?"simulated":"unavailable";}
static void position_fields(cJSON*j,mt_position p){
 if(p.boot){cJSON_AddNumberToObject(j,"position_boot",p.boot);cJSON_AddNumberToObject(j,"position_seq",p.seq);}else{cJSON_AddNullToObject(j,"position_boot");cJSON_AddNullToObject(j,"position_seq");}cJSON_AddStringToObject(j,"position_source",position_source(p.source));cJSON_AddBoolToObject(j,"fix",p.fix);cJSON_AddBoolToObject(j,"stale",p.boot&&p.age_ms>MT_STALE_MS);
 if(p.boot)cJSON_AddNumberToObject(j,"position_age_ms",p.age_ms);else cJSON_AddNullToObject(j,"position_age_ms");
 if(!p.fix){cJSON_AddNullToObject(j,"position");return;}cJSON*x=cJSON_AddObjectToObject(j,"position");cJSON_AddNumberToObject(x,"lat",p.lat_e7/1e7);cJSON_AddNumberToObject(x,"lon",p.lon_e7/1e7);cJSON_AddStringToObject(x,"source",position_source(p.source));cJSON_AddNumberToObject(x,"age_ms",p.age_ms);if(p.accuracy_mm==UINT32_MAX)cJSON_AddNullToObject(x,"accuracy_m");else cJSON_AddNumberToObject(x,"accuracy_m",p.accuracy_mm/1000.0);
}
static void telemetry_fields(cJSON*j){
 position_fields(j,mid_mt_local(&mobile,millis()));cJSON_AddBoolToObject(j,"telemetry_enabled",telemetry_enabled);cJSON_AddNumberToObject(j,"telemetry_period_ms",telemetry_period);
 cJSON_AddNumberToObject(j,"telemetry_generated",telemetry_generated);cJSON_AddNumberToObject(j,"telemetry_submitted",telemetry_submitted);cJSON_AddNumberToObject(j,"telemetry_link_ok",telemetry_link_ok);cJSON_AddNumberToObject(j,"telemetry_link_fail",telemetry_link_fail);cJSON_AddNumberToObject(j,"telemetry_deferred",telemetry_deferred);cJSON_AddNumberToObject(j,"telemetry_rejected",mobile.rejected);cJSON_AddNumberToObject(j,"telemetry_duplicates",mobile.duplicates);cJSON_AddNumberToObject(j,"rf_table_full",mobile.rf_full);cJSON_AddNumberToObject(j,"position_table_full",mobile.peer_full);
 cJSON*a=cJSON_AddArrayToObject(j,"rf_neighbors");for(unsigned i=0;i<MT_ROWS;i++){mt_rf*r=&mobile.rf[i];if(!r->used)continue;cJSON*x=cJSON_CreateObject();field_id(x,"peer_id",r->peer);field_id(x,"receiver_id",self);cJSON_AddStringToObject(x,"direction","peer_to_receiver");cJSON_AddStringToObject(x,"rf_source",r->rssi_valid?"measured":"unavailable");if(r->rssi_valid)cJSON_AddNumberToObject(x,"rssi_dbm",r->rssi);else cJSON_AddNullToObject(x,"rssi_dbm");if(r->channel_valid)cJSON_AddNumberToObject(x,"channel",r->channel);else cJSON_AddNullToObject(x,"channel");cJSON_AddNumberToObject(x,"sample_age_ms",(double)(millis()-r->at));cJSON_AddNumberToObject(x,"sample_count",r->count);if(r->count){cJSON_AddNumberToObject(x,"rssi_mean_dbm",(double)r->sum/r->count);cJSON_AddNumberToObject(x,"rssi_min_dbm",r->minimum);cJSON_AddNumberToObject(x,"rssi_max_dbm",r->maximum);cJSON_AddNumberToObject(x,"aggregate_last_valid_age_ms",(double)(millis()-r->valid_at));}else{cJSON_AddNullToObject(x,"rssi_mean_dbm");cJSON_AddNullToObject(x,"rssi_min_dbm");cJSON_AddNullToObject(x,"rssi_max_dbm");cJSON_AddNullToObject(x,"aggregate_last_valid_age_ms");}nd_peer*peer=nd_find(&neighbors,r->peer);int state=peer?nd_state(peer,millis()):0;cJSON_AddStringToObject(x,"state",state==2?"bidirectional":state==1?"heard":"lost");cJSON_AddItemToArray(a,x);}
 a=cJSON_AddArrayToObject(j,"peer_positions");for(unsigned i=0;i<MT_ROWS;i++){mt_peer*r=&mobile.peers[i];if(!r->used)continue;cJSON*x=cJSON_CreateObject();field_id(x,"peer_id",r->peer);cJSON_AddNumberToObject(x,"peer_boot",r->board_boot);cJSON_AddNumberToObject(x,"announcement_seq",r->announcement_seq);cJSON_AddNumberToObject(x,"received_age_ms",(double)(millis()-r->at));mt_position observed=mid_mt_aged(r->position,millis()-r->at);nd_peer*known=nd_find(&neighbors,r->peer);int boot_matches=known&&known->boot==r->board_boot;cJSON_AddBoolToObject(x,"peer_boot_matches",boot_matches);if(!boot_matches){observed.fix=0;observed.lat_e7=observed.lon_e7=0;observed.accuracy_mm=UINT32_MAX;}position_fields(x,observed);cJSON_AddItemToArray(a,x);}
}
static int zero_u32(cJSON*j,const char*name,uint32_t*out,uint32_t max){cJSON*v=cJSON_GetObjectItemCaseSensitive(j,name);if(!cJSON_IsNumber(v)||!isfinite(v->valuedouble)||v->valuedouble<0||v->valuedouble>max)return -1;*out=(uint32_t)v->valuedouble;return v->valuedouble==*out?0:-1;}
static int position_parse(cJSON*j,mt_position*p){
 memset(p,0,sizeof(*p));p->accuracy_mm=UINT32_MAX;if(u32(j,"position_boot",&p->boot)||u32(j,"position_seq",&p->seq)||zero_u32(j,"age_ms",&p->age_ms,MT_AGE_MAX))return -1;
 const char*source=str(j,"source");if(!source)return -1;if(!strcmp(source,"gnss"))p->source=1;else if(!strcmp(source,"simulated"))p->source=2;else if(strcmp(source,"unavailable"))return -1;
 cJSON*f=cJSON_GetObjectItemCaseSensitive(j,"fix"),*lat=cJSON_GetObjectItemCaseSensitive(j,"lat"),*lon=cJSON_GetObjectItemCaseSensitive(j,"lon"),*acc=cJSON_GetObjectItemCaseSensitive(j,"accuracy_m");if(!cJSON_IsBool(f))return -1;p->fix=cJSON_IsTrue(f);
 if(!p->fix)return cJSON_IsNull(lat)&&cJSON_IsNull(lon)&&(!acc||cJSON_IsNull(acc))?0:-1;
 if(!p->source||!cJSON_IsNumber(lat)||!cJSON_IsNumber(lon)||!isfinite(lat->valuedouble)||!isfinite(lon->valuedouble)||lat->valuedouble< -90||lat->valuedouble>90||lon->valuedouble< -180||lon->valuedouble>180)return -1;
 p->lat_e7=(int32_t)llround(lat->valuedouble*1e7);p->lon_e7=(int32_t)llround(lon->valuedouble*1e7);
 if(acc&&!cJSON_IsNull(acc)){if(!cJSON_IsNumber(acc)||!isfinite(acc->valuedouble)||acc->valuedouble<0||acc->valuedouble>1000000)return -1;p->accuracy_mm=(uint32_t)llround(acc->valuedouble*1000.0);}return 0;
}
static void rf_observation(const input*e,int filtered){mid_id peer;memcpy(peer.mac,e->mac,6);cJSON*j=event("rf_rx");field_id(j,"peer_id",peer);field_id(j,"receiver_id",self);cJSON_AddStringToObject(j,"direction","peer_to_receiver");if(e->rssi_valid)cJSON_AddNumberToObject(j,"rssi_dbm",e->rssi);else cJSON_AddNullToObject(j,"rssi_dbm");if(e->channel_valid)cJSON_AddNumberToObject(j,"channel",e->rx_channel);else cJSON_AddNullToObject(j,"channel");cJSON_AddStringToObject(j,"rf_source",e->rssi_valid?"measured":"unavailable");cJSON_AddNumberToObject(j,"sample_at_ms",(double)e->rx_at_ms);cJSON_AddNumberToObject(j,"sample_age_ms",(double)(millis()-e->rx_at_ms));cJSON_AddNumberToObject(j,"frame_bytes",e->len);cJSON_AddStringToObject(j,"frame_kind",!memcmp(e->data,"MT01",4)?"MT01":!memcmp(e->data,"SR01",4)?"SR01":!memcmp(e->data,"MID1",4)?"MID1":"unknown");cJSON_AddBoolToObject(j,"filtered",filtered);int nd=!memcmp(e->data,"ND01",4);if(!nd)output(j);if(!filtered)mid_mt_sample(&mobile,peer,e->rssi_valid,e->rssi,e->channel_valid,e->rx_channel,e->rx_at_ms);}
#include "field_runtime.inc"
static int target_boot_find(mid_id dst,uint32_t*value,uint32_t*age,const char**source){uint64_t now=millis();nd_peer*p=nd_find(&neighbors,dst);if(p&&nd_state(p,now)==2){*value=p->boot;*age=(uint32_t)(now-p->ack);*source="direct_confirmed";return 0;}if(!bc_get(&observed_boots,dst.mac,now,value,age)){*source="observed_origin";return 0;}return -1;}
static void command(const char*line,int len){if(!link_mode_loaded)link_mode_load();
 cJSON*j=NULL,*res=NULL;const char*cmd=NULL,*nonce=NULL,*why="invalid_command",*boot_source=NULL;int ok=0;uint32_t submitted_seq=0,reliable_id=0,reliable_dst_boot=0,boot_age=0;mid_id submitted_dst={{0}};const char*end=NULL;
 if(len>0&&len<=SERIAL_MAX)j=cJSON_ParseWithLengthOpts(line,(size_t)len+1,&end,true);
 if(!cJSON_IsObject(j))goto reply;
 for(cJSON*a=j->child;a;a=a->next)for(cJSON*b=a->next;b;b=b->next)if(!strcmp(a->string,b->string))goto reply;
 cmd=str(j,"cmd");nonce=str(j,"nonce");if(!cmd||!printable(nonce))goto reply;
 {int handled=field_command(j,cmd,&why);if(handled>=0){ok=handled;goto reply;}}
 if(!strcmp(cmd,"info")||!strcmp(cmd,"stats")||!strcmp(cmd,"telemetry")||!strcmp(cmd,"node_id_get")){ok=1;}
 else if(!strcmp(cmd,"node_id_set")){mid_id target;uint32_t requested=0,target_boot=0;if(parse_id(str(j,"target_mac"),&target)||!mid_equal(target,self)||u32(j,"target_boot",&target_boot)||target_boot!=boot||u32(j,"node_number",&requested)||!requested){why="node_identity_or_number_invalid";goto reply;}if(node_number_store(requested)){why="node_id_nvs_write_failed";goto reply;}ok=1;}
 else if(!strcmp(cmd,"position_set")){mt_position proposed;if(position_parse(j,&proposed)||mid_mt_set(&mobile,&proposed,millis())){why="invalid_or_stale_position";goto reply;}ok=1;}
 else if(!strcmp(cmd,"telemetry_config")){cJSON*v=cJSON_GetObjectItemCaseSensitive(j,"enabled");uint32_t period;if(!cJSON_IsBool(v)||u32(j,"period_ms",&period)||period<10000||period>60000){why="invalid_telemetry_config";goto reply;}telemetry_enabled=cJSON_IsTrue(v);telemetry_period=period;telemetry_due=millis()+period;ok=1;}
 else if(!strcmp(cmd,"stop")){stop_all();ok=1;}
 else if(!strcmp(cmd,"discover_config")||!strcmp(cmd,"route_config")){
  int selected_route=!strcmp(cmd,"route_config");if(have_discovery&&selected_route!=route_mode){why="clear_other_mode_first";goto reply;}
  uint32_t group,ch;cJSON*a=cJSON_GetObjectItemCaseSensitive(j,"autostart");
  if(active||radio||waiting||locked||have_deployment||deployment_fault){why="busy_or_static_profile";goto reply;}
  if(u32(j,"group",&group)||u32(j,"channel",&ch)||ch>13||!cJSON_IsBool(a)){why="invalid_discovery_config";goto reply;}
  uint8_t b[12]={'N','D','c','1',0,0,0,0,(uint8_t)ch,(uint8_t)cJSON_IsTrue(a),0,0};for(unsigned i=0;i<4;i++)b[4+i]=(uint8_t)(group>>(8*i));
  nvs_handle_t h;esp_err_t r=nvs_open(selected_route?"mid_route":"mid_neighbor",NVS_READWRITE,&h);if(r!=ESP_OK){why="save_failed";goto reply;}r=nvs_set_blob(h,"cfg",b,sizeof(b));if(r==ESP_OK)r=nvs_commit(h);nvs_close(h);if(r!=ESP_OK){why="save_failed";goto reply;}
  route_mode=selected_route;channel=(uint8_t)ch;discovery_group=group;discovery_autostart=cJSON_IsTrue(a);have_discovery=1;discovery_fault=0;discovery_from_backup=0;
  if(discovery_autostart&&discovery_start()!=ESP_OK){why="saved_but_start_failed";goto reply;}ok=1;
 }else if(!strcmp(cmd,"discover_start")||!strcmp(cmd,"route_start")){ok=discovery_start()==ESP_OK;if(!ok)why="no_config_busy_or_fault";
 }else if(!strcmp(cmd,"discover_clear")||!strcmp(cmd,"route_clear")){
  if(active||radio||waiting||locked){why="busy_or_locked";goto reply;}nvs_handle_t h;esp_err_t r=nvs_open(route_mode?"mid_route":"mid_neighbor",NVS_READWRITE,&h);if(r!=ESP_OK){why="clear_failed";goto reply;}r=nvs_erase_key(h,"lastgood");if(r==ESP_ERR_NVS_NOT_FOUND)r=ESP_OK;if(r==ESP_OK)r=nvs_commit(h);if(r==ESP_OK){r=nvs_erase_key(h,"cfg");if(r==ESP_ERR_NVS_NOT_FOUND)r=ESP_OK;}if(r==ESP_OK)r=nvs_commit(h);nvs_close(h);if(r!=ESP_OK){why="clear_failed";goto reply;}have_discovery=discovery_fault=route_mode=discovery_from_backup=0;channel=6;ok=1;
 }else if(!strcmp(cmd,"routes")){ok=1;
 }else if(!strcmp(cmd,"link_mode")){
 cJSON*m=cJSON_GetObjectItemCaseSensitive(j,"mode");
 if(!m){ok=1;}
 else if(!cJSON_IsString(m)){why="invalid_link_mode";}
 else if(strcmp(m->valuestring,"espnow")&&strcmp(m->valuestring,"lora24")){why="unsupported_link_mode";}
 else if(link_mode_save(m->valuestring)){why="link_mode_nvs_failed";}
 else{snprintf(link_mode,sizeof(link_mode),"%s",m->valuestring);ok=1;}
}else if(!strcmp(cmd,"link_filter")){
  cJSON*clear=cJSON_GetObjectItemCaseSensitive(j,"clear"),*a=cJSON_GetObjectItemCaseSensitive(j,"allow");mid_id proposed[8];unsigned num=0;
  if(cJSON_IsTrue(clear)){filter_enabled=0;filter_count=0;ok=1;}else{if(!cJSON_IsArray(a)||cJSON_GetArraySize(a)>8){why="invalid_filter";goto reply;}cJSON*v=NULL;cJSON_ArrayForEach(v,a){if(!cJSON_IsString(v)||parse_id(v->valuestring,&proposed[num])){why="invalid_filter_mac";goto reply;}num++;}memcpy(filter_allow,proposed,num*sizeof(mid_id));filter_count=num;filter_enabled=1;ok=1;}
 }else if(!strcmp(cmd,"neighbors")||!strcmp(cmd,"neighbor")){ok=1;
 }else if(!strcmp(cmd,"neighbor_probe")){
  mid_id id;if(!active||!have_discovery||parse_id(str(j,"node_id"),&id)||!nd_find(&neighbors,id)){why="unknown_or_inactive";goto reply;}if(millis()<probe_after||count==16||sequence==UINT32_MAX){why="probe_rate_limit_or_queue";goto reply;}mid_packet p;nd_hello(&neighbors,&p,++sequence);ok=enqueue(p,id)==0;probe_after=millis()+1000;
 }else if(!strcmp(cmd,"deploy")){
  if(have_discovery||discovery_fault){why="discovery_present_clear_first";goto reply;}
  if(active||radio||waiting||locked){why="busy_or_locked";goto reply;}
  mid_deployment proposed={0};uint8_t bytes[MID_DEPLOYMENT_BYTES];const char*id=str(j,"profile_id");cJSON*auto_value=cJSON_GetObjectItemCaseSensitive(j,"autostart");
  int n=unhex(str(j,"table_hex"),bytes,sizeof(bytes));if(!printable(id)||!cJSON_IsBool(auto_value)||n<0){why="invalid_deployment";goto reply;}
  snprintf(proposed.profile_id,sizeof(proposed.profile_id),"%s",id);proposed.autostart=cJSON_IsTrue(auto_value);
  if(mid_table_decode(&proposed.table,bytes,(size_t)n)||mid_deployment_validate(&proposed,self)){why="invalid_offline_table";goto reply;}
  if(deployment_store(&proposed)!=ESP_OK){why="deployment_save_failed";goto reply;}deployment=proposed;have_deployment=1;deployment_fault=0;
  if(deployment.autostart&&deployment_start()!=ESP_OK){why="saved_but_start_failed";goto reply;}ok=1;
 }else if(!strcmp(cmd,"local_start")){
  if(!have_deployment||deployment_fault){why="no_valid_deployment";goto reply;}if(deployment_start()!=ESP_OK){why="busy_locked_or_radio_failed";goto reply;}ok=1;
 }else if(!strcmp(cmd,"deployment_clear")){
  if(active||radio||waiting||locked){why="busy_or_locked";goto reply;}if(deployment_delete()!=ESP_OK){why="deployment_clear_failed";goto reply;}
  have_deployment=deployment_fault=0;memset(&deployment,0,sizeof(deployment));mid_init(&node,self,self,0);ok=1;
 }
 else if(!strcmp(cmd,"start")){
  if(have_discovery||discovery_fault||have_deployment||deployment_fault){why="deployment_present_clear_first";goto reply;}
  mid_id publisher;uint32_t publisher_boot;if(active||radio||waiting||locked){why="busy_or_locked";goto reply;}
  if(parse_id(str(j,"publisher"),&publisher)||u32(j,"publisher_boot",&publisher_boot)){why="invalid_publisher";goto reply;}
  mid_init(&node,self,publisher,publisher_boot);esp_err_t r=radio_start();if(r!=ESP_OK){why="radio_start_failed";goto reply;}active=1;ok=1;
 }else if(!strcmp(cmd,"config")){
  if(have_deployment||deployment_fault){why="offline_table_active";goto reply;}
  mid_packet p;uint8_t bytes[250];int n=unhex(str(j,"frame_hex"),bytes,sizeof(bytes));
  if(!active){why="inactive";goto reply;}if(n<0||mid_decode(&p,bytes,(size_t)n)||p.kind!=1||!mid_equal(p.origin,self)||p.boot!=boot){why="invalid_local_config";goto reply;}ok=config_packet(&p)==1;if(!ok)why="config_rejected_or_stale";
 }else if(!strcmp(cmd,"target_boot_get")){
  if(!active||!route_mode||parse_id(str(j,"dst"),&submitted_dst)){why="inactive_route_or_destination";goto reply;}
  if(target_boot_find(submitted_dst,&reliable_dst_boot,&boot_age,&boot_source)){why="target_boot_unavailable_or_conflict";goto reply;}ok=1;
 }else if(!strcmp(cmd,"send_reliable")){
  mid_id dst;uint8_t bytes[FR_MAX_PAYLOAD];uint32_t db=0;int n;
  if(!active||!route_mode||parse_id(str(j,"dst"),&dst)){why="inactive_route_or_destination";goto reply;}
  nd_peer*peer=nd_find(&neighbors,dst);if(cJSON_GetObjectItemCaseSensitive(j,"dst_boot")){if(u32(j,"dst_boot",&db)){why="invalid_target_boot";goto reply;}boot_source="caller";}else if(target_boot_find(dst,&db,&boot_age,&boot_source)){why="target_boot_required";goto reply;}
  if(!db||(peer&&nd_state(peer,millis())==2&&peer->boot!=db)){why="target_boot_mismatch";goto reply;}
  n=unhex(str(j,"payload_hex"),bytes,sizeof(bytes));if(n<0||fr_start(&reliable,dst.mac,db,bytes,(size_t)n,millis(),&reliable_id)){why="reliable_queue_full_or_payload";goto reply;}reliable_dst_boot=db;submitted_dst=dst;ok=1;
 }else if(!strcmp(cmd,"send")){
  mid_packet p={.kind=2,.ttl=8,.origin=self,.boot=boot};mid_id dst;int n;
  if(!active||(!have_discovery&&!node.have_table)){why="inactive_or_no_config";goto reply;}if(parse_id(str(j,"dst"),&dst)){why="invalid_destination";goto reply;}
  n=unhex(str(j,"payload_hex"),p.body+6,MID_PAYLOAD);if(n<0||sequence==UINT32_MAX){why="payload_or_sequence";goto reply;}memcpy(p.body,dst.mac,6);p.size=(uint16_t)(n+6);p.seq=++sequence;if(route_mode){route_tick();ok=sr_submit(&router,dst,p.seq,p.body+6,(size_t)n,millis())==0;if(ok)observation("tx_queued",0,&p,NULL,0);}else ok=data_packet(&p,0)==0;if(!ok)why="no_route_or_queue_full";else{submitted_seq=p.seq;submitted_dst=dst;}
 }else {why="unknown_command";}
reply:
 {mid_display_event d={.kind=MID_DISPLAY_EV_COMMAND,.at_ms=millis(),.command_ok=(uint8_t)ok};snprintf(d.command,sizeof(d.command),"%.11s",cmd?cmd:"invalid");(void)mid_display_model_apply(&screen,&d);}
 res=event("command_result");if(nonce&&printable(nonce))cJSON_AddStringToObject(res,"nonce",nonce);else cJSON_AddNullToObject(res,"nonce");cJSON_AddStringToObject(res,"cmd",cmd?cmd:"invalid");cJSON_AddBoolToObject(res,"ok",ok);if(!ok)cJSON_AddStringToObject(res,"error",why);
 cJSON_AddStringToObject(res,"mode",active?((have_discovery||node.have_table)?"active":"wait_config"):"idle");cJSON_AddBoolToObject(res,"radio",radio);cJSON_AddBoolToObject(res,"stopping",stopping);cJSON_AddBoolToObject(res,"locked_until_reset",locked);cJSON_AddNumberToObject(res,"channel",CHANNEL);cJSON_AddNumberToObject(res,"uart_baud",460800);
 cJSON_AddStringToObject(res,"deployment_mode",have_discovery?(route_mode?"autonomous":"discovery"):have_deployment?"offline_table":"mid");cJSON_AddBoolToObject(res,"deployment_saved",have_deployment);cJSON_AddBoolToObject(res,"deployment_fault",deployment_fault);cJSON_AddBoolToObject(res,"display_enabled",MID_DISPLAY_ENABLED);cJSON_AddBoolToObject(res,"route_feedback_experimental",MID_ROUTE_FEEDBACK);cJSON_AddBoolToObject(res,"health_monitor_started",health_started);cJSON_AddNumberToObject(res,"health_state",__atomic_load_n(&health_state,__ATOMIC_ACQUIRE));cJSON_AddNumberToObject(res,"health_restarts",__atomic_load_n(&health_restarts,__ATOMIC_ACQUIRE));cJSON_AddBoolToObject(res,"task_wdt_configured",__atomic_load_n(&task_wdt_configured,__ATOMIC_ACQUIRE));cJSON_AddBoolToObject(res,"task_wdt_reset_enabled",__atomic_load_n(&task_wdt_panic,__ATOMIC_ACQUIRE));cJSON_AddBoolToObject(res,"main_task_wdt_registered",main_wdt_registered);cJSON_AddBoolToObject(res,"health_task_wdt_registered",__atomic_load_n(&health_wdt_registered,__ATOMIC_ACQUIRE));
 if(have_deployment){cJSON_AddStringToObject(res,"profile_id",deployment.profile_id);cJSON_AddBoolToObject(res,"autostart",deployment.autostart);}
 if(ok&&reliable_id){cJSON_AddNumberToObject(res,"message_id",reliable_id);cJSON_AddNumberToObject(res,"origin_boot",boot);cJSON_AddNumberToObject(res,"destination_boot",reliable_dst_boot);field_id(res,"dst",submitted_dst);cJSON_AddBoolToObject(res,"destination_confirmed",false);}
 if(ok&&boot_source){cJSON_AddStringToObject(res,"target_boot_source",boot_source);if(strcmp(boot_source,"caller"))cJSON_AddNumberToObject(res,"target_boot_age_ms",boot_age);if(cmd&&!strcmp(cmd,"target_boot_get")){field_id(res,"dst",submitted_dst);cJSON_AddNumberToObject(res,"destination_boot",reliable_dst_boot);}}
 if(ok&&submitted_seq){cJSON_AddNumberToObject(res,"packet_seq",submitted_seq);cJSON_AddNumberToObject(res,"origin_boot",boot);field_id(res,"origin",self);field_id(res,"dst",submitted_dst);cJSON_AddBoolToObject(res,"destination_confirmed",false);}
 if(ok&&cmd&&(!strcmp(cmd,"info")||!strcmp(cmd,"node_id_get")||!strcmp(cmd,"node_id_set")))node_number_json(res);
 if(ok&&cmd&&!strcmp(cmd,"info")){cJSON_AddStringToObject(res,"firmware","mid-espnow");cJSON_AddStringToObject(res,"chip","esp32s3");cJSON_AddStringToObject(res,"board","EoRa-HUB-400TB");cJSON_AddNumberToObject(res,"display_api",MID_DISPLAY_API_VERSION);cJSON_AddNumberToObject(res,"telemetry_api",1);cJSON_AddNumberToObject(res,"field_api",2);cJSON_AddNumberToObject(res,"lora_ref_api",1);cJSON_AddStringToObject(res,"field_ip_schema","field.ip.v2");cJSON_AddStringToObject(res,"link_mode",link_mode);cJSON_AddStringToObject(res,"link_mode_active",link_mode_active());cJSON_AddBoolToObject(res,"link_mode_pending",strcmp(link_mode,link_mode_active())!=0);cJSON_AddStringToObject(res,"link_backend",link->name);cJSON_AddNumberToObject(res,"link_send_ok",link_send_ok);cJSON_AddNumberToObject(res,"link_send_fail",link_send_fail);cJSON_AddNumberToObject(res,"link_send_oversize",link_send_oversize);char label[2]={screen.identity.label,0};cJSON_AddStringToObject(res,"device_label",label);}
 if(ok&&cmd&&!strcmp(cmd,"stats")){cJSON_AddNumberToObject(res,"uart_rx_bytes",__atomic_load_n(&uart_received_bytes,__ATOMIC_RELAXED));cJSON_AddNumberToObject(res,"uart_fifo_overflows",__atomic_load_n(&uart_fifo_overflows,__ATOMIC_RELAXED));cJSON_AddNumberToObject(res,"uart_ring_overflows",__atomic_load_n(&uart_ring_overflows,__ATOMIC_RELAXED));cJSON_AddNumberToObject(res,"tx_queued",screen.counts.queued);cJSON_AddNumberToObject(res,"tx_submitted",screen.counts.submitted);cJSON_AddNumberToObject(res,"link_ok",screen.counts.link_ok);cJSON_AddNumberToObject(res,"link_fail",screen.counts.link_fail);cJSON_AddNumberToObject(res,"rx_local",screen.counts.rx_dest);cJSON_AddNumberToObject(res,"rx_duplicate",screen.counts.rx_duplicate);cJSON_AddNumberToObject(res,"rx_relay",screen.counts.rx_relay);cJSON_AddNumberToObject(res,"local_fail",screen.counts.local_fail);cJSON_AddNumberToObject(res,"timeouts",screen.counts.timeouts);cJSON_AddNumberToObject(res,"faults",screen.fault_count);cJSON_AddNumberToObject(res,"config_seq",node.config_seq);cJSON_AddNumberToObject(res,"queue_depth",count);cJSON_AddNumberToObject(res,"display_hw",mid_display_hardware_state());cJSON_AddStringToObject(res,"destination_status","unconfirmed");cJSON_AddNumberToObject(res,"route_warm_queries",warm_queries);cJSON_AddNumberToObject(res,"route_warm_hits",warm_hits);cJSON_AddNumberToObject(res,"route_warm_misses",warm_misses);cJSON_AddNumberToObject(res,"route_retries",router.retries);cJSON_AddNumberToObject(res,"route_rreq_denied",router.rreq_denied);cJSON_AddNumberToObject(res,"send_callback_timeouts",callback_timeouts);cJSON_AddNumberToObject(res,"uart_tx_drops",uart_tx_drops);cJSON_AddNumberToObject(res,"radio_heal_attempts",heal_attempts);cJSON_AddBoolToObject(res,"radio_heal_pending",heal_at!=0);cJSON_AddNumberToObject(res,"input_overflow_total",input_overflow_total);}
 if(ok&&cmd&&!strcmp(cmd,"stats")){cJSON_AddNumberToObject(res,"reliable_delivered",reliable.delivered);cJSON_AddNumberToObject(res,"reliable_timeouts",reliable.timeouts);cJSON_AddNumberToObject(res,"reliable_duplicates",reliable.duplicates);cJSON_AddNumberToObject(res,"reliable_rejected",reliable.rejected);cJSON_AddNumberToObject(res,"reliable_seen_full",reliable.seen_full);cJSON_AddNumberToObject(res,"reliable_ack_queue_full",reliable_ack_full);cJSON_AddNumberToObject(res,"reliable_ack_failed",reliable_ack_failed);}
 cJSON_AddBoolToObject(res,"link_filter_enabled",filter_enabled);
 if(route_mode){cJSON_AddNumberToObject(res,"route_core_bytes",sizeof(router));cJSON_AddNumberToObject(res,"route_control_frames",router.control_frames);cJSON_AddNumberToObject(res,"route_control_bytes",router.control_bytes);cJSON_AddNumberToObject(res,"route_data_frames",router.data_frames);cJSON_AddNumberToObject(res,"route_data_bytes",router.data_bytes);cJSON_AddNumberToObject(res,"route_submitted",route_submitted);cJSON_AddNumberToObject(res,"route_link_ok",route_link_ok);cJSON_AddNumberToObject(res,"route_link_fail",route_link_fail);cJSON_AddNumberToObject(res,"route_overflows",router.overflows);cJSON_AddNumberToObject(res,"route_rejected",router.rejected);cJSON_AddNumberToObject(res,"route_event_overflows",router.event_overflows);cJSON_AddNumberToObject(res,"route_pending_high",router.pending_high);cJSON_AddNumberToObject(res,"route_out_high",router.out_high);cJSON_AddNumberToObject(res,"route_candidates_high",router.candidate_high);cJSON_AddNumberToObject(res,"route_process_total_us",(double)route_process_us);cJSON_AddNumberToObject(res,"route_process_max_us",(double)route_process_max_us);cJSON_AddNumberToObject(res,"free_heap_bytes",esp_get_free_heap_size());cJSON_AddNumberToObject(res,"minimum_free_heap_bytes",esp_get_minimum_free_heap_size());}
 if(ok&&cmd&&!strcmp(cmd,"routes")){cJSON*a=cJSON_AddArrayToObject(res,"routes");for(unsigned i=0;i<SR_ROUTES;i++)if(router.routes[i].used){sr_route*r=&router.routes[i];cJSON*x=cJSON_CreateObject();field_id(x,"dst",r->dst);cJSON_AddNumberToObject(x,"expires_ms",(double)r->until);cJSON_AddNumberToObject(x,"request",r->request);cJSON*p=cJSON_AddArrayToObject(x,"path");for(unsigned k=0;k<r->path.n;k++){char text[18];mac_text(r->path.path[k],text);cJSON_AddItemToArray(p,cJSON_CreateString(text));}cJSON_AddItemToArray(a,x);}}
 cJSON_AddBoolToObject(res,"discovery_saved",have_discovery);cJSON_AddBoolToObject(res,"discovery_fault",discovery_fault);cJSON_AddBoolToObject(res,"discovery_from_backup",discovery_from_backup);cJSON_AddBoolToObject(res,"discovery_backup_confirmed",discovery_backup_confirmed);cJSON_AddNumberToObject(res,"discovery_backup_write_failures",discovery_backup_write_failures);
 if(have_discovery){cJSON_AddBoolToObject(res,"discovery_autostart",discovery_autostart);cJSON_AddNumberToObject(res,"control_submitted",control_submitted);cJSON_AddNumberToObject(res,"control_link_ok",control_link_ok);cJSON_AddNumberToObject(res,"control_link_fail",control_link_fail);cJSON_AddNumberToObject(res,"group",discovery_group);cJSON_AddNumberToObject(res,"hello_period_min_ms",2000);cJSON_AddNumberToObject(res,"hello_period_max_ms",3000);cJSON_AddNumberToObject(res,"confirm_timeout_ms",ND_CONFIRM_MS);cJSON_AddNumberToObject(res,"lost_timeout_ms",ND_LOST_MS);cJSON_AddNumberToObject(res,"control_hello_generated",neighbors.tx_hello);cJSON_AddNumberToObject(res,"control_ack_generated",neighbors.tx_ack);cJSON_AddNumberToObject(res,"control_hello_received",neighbors.rx_hello);cJSON_AddNumberToObject(res,"control_ack_received",neighbors.rx_ack);cJSON_AddNumberToObject(res,"control_rejected",neighbors.rejected);cJSON_AddNumberToObject(res,"neighbor_table_full",neighbors.full);}
 if(ok&&cmd&&!strcmp(cmd,"neighbors")){cJSON*a=cJSON_AddArrayToObject(res,"neighbors");for(unsigned i=0;i<ND_PEERS;i++)if(neighbors.peers[i].used){cJSON*x=cJSON_CreateObject();neighbor_fields(x,&neighbors.peers[i]);cJSON_AddItemToArray(a,x);}}
 if(ok&&cmd&&!strcmp(cmd,"neighbor")){mid_id id;if(parse_id(str(j,"node_id"),&id)){cJSON_ReplaceItemInObject(res,"ok",cJSON_CreateBool(false));cJSON_AddStringToObject(res,"error","invalid_node_id");}else{cJSON*x=cJSON_AddObjectToObject(res,"neighbor");neighbor_fields(x,nd_find(&neighbors,id));}}
 if(ok&&cmd&&!strcmp(cmd,"telemetry"))telemetry_fields(res);else if(ok&&cmd&&!strcmp(cmd,"position_set"))position_fields(res,mid_mt_local(&mobile,millis()));else if(ok&&cmd&&!strcmp(cmd,"telemetry_config")){cJSON_AddBoolToObject(res,"telemetry_enabled",telemetry_enabled);cJSON_AddNumberToObject(res,"telemetry_period_ms",telemetry_period);}
 if(ok&&cmd&&!strcmp(cmd,"field_status"))field_counters(res);
 if(ok&&cmd&&(!strcmp(cmd,"lora_ref_status")||!strcmp(cmd,"lora_ref_config")))lora_ref_status(res);
 if(ok&&cmd&&!strcmp(cmd,"field_records"))field_records(res,j);
 if(ok&&cmd&&!strcmp(cmd,"field_ip_records")){cJSON*a=cJSON_GetObjectItemCaseSensitive(j,"after");uint64_t after=cJSON_IsNumber(a)&&a->valuedouble>=0&&a->valuedouble<=9007199254740991.0?(uint64_t)a->valuedouble:0;field_ip_export(res,after);}
 if(ok&&cmd&&!strcmp(cmd,"field_saved_summary")){field_summary saved;size_t n=sizeof(saved);if(field_nvs_read("summary",&saved,&n)==ESP_OK&&n==sizeof(saved)&&saved.magic==0x32534646&&memchr(saved.note,0,sizeof(saved.note))){cJSON*x=cJSON_AddObjectToObject(res,"saved_summary");cJSON_AddNumberToObject(x,"boot_id",saved.boot);cJSON_AddNumberToObject(x,"segment",saved.segment);cJSON_AddNumberToObject(x,"uptime_ms",(double)saved.uptime);cJSON_AddStringToObject(x,"manual_note",saved.note);for(unsigned i=0;i<5;i++)cJSON_AddNumberToObject(x,field_kind(i),saved.totals[i]);cJSON_AddNumberToObject(x,"record_overwritten",saved.overwritten);cJSON_AddStringToObject(x,"scope","checkpoint only; raw bytes volatile; never merged across boot");}else cJSON_AddNullToObject(res,"saved_summary");}
 output(res);cJSON_Delete(j);
}
static void uart_reader(void*unused){
 (void)unused;input e={.type=3};unsigned n=0;int overflow=0,discard=0;uint8_t block[128];uart_event_t notice;
 for(;;){
  while(xQueueReceive(uart_events,&notice,0)==pdTRUE){
   if(notice.type==UART_FIFO_OVF||notice.type==UART_BUFFER_FULL){
    if(notice.type==UART_FIFO_OVF)__atomic_fetch_add(&uart_fifo_overflows,1,__ATOMIC_RELAXED);else __atomic_fetch_add(&uart_ring_overflows,1,__ATOMIC_RELAXED);
    n=0;overflow=0;discard=1;input fault={.type=4};if(xQueueSend(inputs,&fault,0)!=pdTRUE)__atomic_fetch_add(&callback_drops,1,__ATOMIC_RELAXED);
   }
  }
  int got=uart_read_bytes(UART_NUM_0,block,sizeof(block),pdMS_TO_TICKS(20));
  if(got<=0)continue;
  __atomic_fetch_add(&uart_received_bytes,(unsigned)got,__ATOMIC_RELAXED);
  for(int i=0;i<got;i++){
   int c=block[i];if(discard){if(c=='\n')discard=0;continue;}
   if(c=='\n'){if(n&&e.line[n-1]=='\r')n--;e.line[n]=0;e.len=overflow?SERIAL_MAX+1:(int)n;if(xQueueSend(inputs,&e,0)!=pdTRUE)__atomic_fetch_add(&callback_drops,1,__ATOMIC_RELAXED);n=0;overflow=0;}
   else if(n<SERIAL_MAX)e.line[n++]=(char)c;else overflow=1;
  }
 }
}
static void route_observation(const char*name,mid_display_event_kind kind,const sr_packet*p,const mid_id*next,int code){mid_packet m={.kind=2,.origin=p->path[0],.boot=p->boot,.seq=p->seq,.ttl=8,.size=(uint16_t)(p->len+6)};mid_id actual=sr_service_id(p->dst)?p->path[p->n-1]:p->dst;memcpy(m.body,actual.mac,6);memcpy(m.body+6,p->payload,p->len);observation(name,kind,&m,next,code);}
static void route_events(void){sr_event e;static const char*names[]={"invalid","route_accepted","route_waiting","route_request","route_candidate","route_selected","rx_local","route_no_route","route_invalidated","delivery_unknown","route_drop"};while(sr_next_event(&router,&e)){field_route_event(&e);if(e.type==SR_DELIVERED){field_gateway_receive(&e);field_reliable_receive(&e);}if(e.type==SR_DELIVERED||e.type==SR_RELAY){sr_packet p={.n=e.path.n,.boot=e.boot,.seq=e.seq,.dst=e.dst,.len=e.len};memcpy(p.path,e.path.path,sizeof(p.path));memcpy(p.payload,e.payload,e.len);route_observation(e.type==SR_DELIVERED?"rx_local":"rx_relay",e.type==SR_DELIVERED?MID_DISPLAY_EV_RX_DEST:MID_DISPLAY_EV_RX_RELAY,&p,NULL,0);}else{cJSON*j=event(e.type<=10?names[e.type]:"route_invalid");field_id(j,"origin",e.origin);field_id(j,"dst",e.dst);cJSON_AddNumberToObject(j,"origin_boot",e.boot);cJSON_AddNumberToObject(j,"seq",e.seq);cJSON_AddNumberToObject(j,"request",e.request);cJSON_AddNumberToObject(j,"reason",e.reason);cJSON*a=cJSON_AddArrayToObject(j,"path");for(unsigned i=0;i<e.path.n;i++){char text[18];mac_text(e.path.path[i],text);cJSON_AddItemToArray(a,cJSON_CreateString(text));}output(j);}}}
static void route_tick(void){uint64_t start=(uint64_t)esp_timer_get_time();for(unsigned i=0;i<ND_PEERS;i++){nd_peer*p=&neighbors.peers[i];if(p->used)sr_neighbor(&router,p->id,p->boot,nd_state(p,millis())==2&&allowed(p->id));}sr_tick(&router,millis());uint64_t cost=(uint64_t)esp_timer_get_time()-start;route_process_us+=cost;if(cost>route_process_max_us)route_process_max_us=cost;route_events();}
static void route_pump(void){
 if(!active||waiting||!sr_next_tx(&router,&route_pending,millis()))return;
 uint8_t bytes[250];int len=sr_encode(&route_pending.packet,bytes,sizeof(bytes));esp_err_t r=len<0?ESP_ERR_INVALID_ARG:ESP_OK;
 if(!allowed(route_pending.next))r=ESP_FAIL;
 if(r==ESP_OK)r=(link->send(route_pending.next.mac,bytes,(unsigned)len)==0)?ESP_OK:ESP_FAIL;
 if(r==ESP_OK){waiting=route_waiting=1;submitted=millis();route_submitted++;if(sr_base_type(route_pending.packet.type)==SR_DATA)route_observation("tx_submit",MID_DISPLAY_EV_TX_SUBMITTED,&route_pending.packet,&route_pending.next,0);}
 else{sr_tx_abort(&router,&route_pending,millis());if(sr_base_type(route_pending.packet.type)==SR_DATA)route_observation("tx_api_failed",MID_DISPLAY_EV_TX_LOCAL_FAIL,&route_pending.packet,&route_pending.next,r);}
}
static void telemetry_pump(void){
 if(!telemetry_enabled||!active||!have_discovery||waiting||millis()<telemetry_due)return;
 if(count||router.count){telemetry_deferred++;return;}
 uint8_t bytes[MT_FRAME];int len=mid_mt_encode(&mobile,route_mode?2:1,millis(),bytes,sizeof(bytes));telemetry_due=millis()+telemetry_period;if(len<0)return;telemetry_generated++;
 const uint8_t broadcast[6]={255,255,255,255,255,255};esp_err_t r=(link->send(broadcast,bytes,(unsigned)len)==0)?ESP_OK:ESP_FAIL;
 if(r==ESP_OK){waiting=telemetry_waiting=1;submitted=millis();telemetry_submitted++;}else{telemetry_link_fail++;cJSON*j=event("telemetry_tx_failed");cJSON_AddNumberToObject(j,"code",r);output(j);}
}
static void pump(void){
 if(!active||waiting||!count){return;}
 pending=txq[head];head=(head+1)%16;count--;
 if(millis()-pending.queued>1000){observation("queue_timeout",pending.packet.kind==2?MID_DISPLAY_EV_TX_TIMEOUT:0,&pending.packet,&pending.next,-4);return;}
 uint8_t bytes[250];int len=mid_encode(&pending.packet,bytes,sizeof(bytes));esp_err_t r=len<0?ESP_ERR_INVALID_ARG:ESP_OK;
 if(!allowed(pending.next))r=ESP_FAIL;
 if(r==ESP_OK)r=(link->send(pending.next.mac,bytes,(unsigned)len)==0)?ESP_OK:ESP_FAIL;
 if(r==ESP_OK){if(have_discovery&&pending.packet.kind==1)control_submitted++;waiting=1;submitted=millis();observation("tx_submit",pending.packet.kind==2?MID_DISPLAY_EV_TX_SUBMITTED:0,&pending.packet,&pending.next,0);}else observation("tx_api_failed",pending.packet.kind==2?MID_DISPLAY_EV_TX_LOCAL_FAIL:0,&pending.packet,&pending.next,(int)r);
}
/* Re-arm the radio after a bounded, self-clearing lock. Every fail-closed path that
 * stops the radio schedules this: the three callback timeouts and the two input
 * overflow paths. A stuck in-flight send defers the heal instead of failing it, and
 * the ESP-NOW session is torn down before the restart so no stale callback can be
 * matched to a later send. HEAL_MAX caps a genuinely broken board. */
static void radio_heal(void){
 if(!locked||!heal_at||millis()<heal_at)return;
 if(waiting){heal_at=millis()+HEAL_DELAY_MS;return;}
 if(radio)close_radio();
 if(millis()-heal_window>HEAL_WINDOW_MS){heal_attempts=0;heal_window=millis();}
 if(heal_attempts>=HEAL_MAX){heal_at=heal_window+HEAL_WINDOW_MS+1;output(event("radio_heal_cooldown"));return;}
 heal_attempts++;locked=0;heal_at=0;
 esp_err_t r=have_discovery?discovery_start():have_deployment?deployment_start():ESP_ERR_INVALID_STATE;
 cJSON*j=event(r==ESP_OK?"radio_healed":"radio_heal_failed");cJSON_AddNumberToObject(j,"attempt",heal_attempts);
 if(r!=ESP_OK){cJSON_AddNumberToObject(j,"code",(int)r);locked=1;heal_at=millis()+HEAL_DELAY_MS;}
 output(j);
}
void app_main(void){
 vTaskPrioritySet(NULL,5);esp_reset_reason_t reason=esp_reset_reason();hg_boot(&health_record,reason==ESP_RST_TASK_WDT?2:reason==ESP_RST_SW?1:0);__atomic_store_n(&health_restarts,health_record.count,__ATOMIC_RELEASE);if(!task_watchdog_config(health_record.count<HG_MAX_RESTARTS))main_wdt_registered=esp_task_wdt_add(NULL)==ESP_OK||esp_task_wdt_status(NULL)==ESP_OK;
 esp_err_t u=uart_driver_install(UART_NUM_0,4096,4096,16,&uart_events,0);if(u!=ESP_OK){printf("MID UART driver failure %d; no radio\n",(int)u);return;}if(uart_set_baudrate(UART_NUM_0,460800)!=ESP_OK){printf("MID UART baud failure; no radio\n");return;}uart_set_hw_flow_ctrl(UART_NUM_0,UART_HW_FLOWCTRL_DISABLE,0);uart_vfs_dev_use_driver(UART_NUM_0);esp_err_t r;unsigned nvs_failures=0;while((r=nvs_flash_init())!=ESP_OK){printf("MID NVS failure %d; retry without erase/radio\n",(int)r);fflush(stdout);nvs_failures++;uint32_t wait_ms=nvs_failures>=3?60000u:(1000u<<nvs_failures);if(nvs_failures>=3)nvs_failures=0;startup_wait(wait_ms);}if(esp_read_mac(self.mac,ESP_MAC_WIFI_STA)!=ESP_OK)return;boot=esp_random()|1u;node_number_load();mid_mt_init(&mobile,self,boot,0);field_boot();lora_ref_init(self,boot);
 mid_display_identity identity={.channel=CHANNEL,.protocol=MID_DISPLAY_MID,.label='?',.node_id=node_number};memcpy(identity.mac,self.mac,6);
 const uint8_t registered[5][6]={{0x90,0xda,0x72,0x48,0xa4,0xf8},{0x90,0xda,0x72,0x48,0xa5,0xcc},{0x90,0xda,0x72,0x48,0xa4,0xe0},{0x90,0xda,0x72,0x48,0xa5,0x20},{0x90,0xda,0x72,0x48,0xa6,0x98}};for(unsigned i=0;i<5;i++)if(!memcmp(self.mac,registered[i],6)){identity.label=(char)('A'+i);break;}
 (void)mid_display_model_init(&screen,&identity);const char*help[5]={"JSON + nonce required","info / stats / stop","deploy / local_start","deployment_clear","send dst payload_hex"};(void)mid_display_set_help(&screen,help);(void)mid_display_start(&screen);
 inputs=xQueueCreate(16,sizeof(input));if(!inputs){output(event("input_queue_alloc_failed"));return;}if(xTaskCreate(uart_reader,"mid_uart",6144,NULL,4,NULL)!=pdPASS){output(event("uart_task_failed"));return;}output(event("boot"));
 r=discovery_load();if(r!=ESP_OK){discovery_fault=1;output(event("discovery_load_failed"));}
 r=deployment_load();if(have_discovery&&(have_deployment||r!=ESP_OK)){discovery_fault=deployment_fault=1;output(event("mode_conflict"));}
 if(have_discovery&&!discovery_fault&&discovery_autostart){if(discovery_start()!=ESP_OK){locked=1;heal_at=millis()+HEAL_DELAY_MS;output(event("discovery_start_failed"));}}
 if(r!=ESP_OK){deployment_fault=1;cJSON*j=event("deployment_load_failed");cJSON_AddNumberToObject(j,"code",r);output(j);}else if(!have_discovery&&!discovery_fault&&have_deployment&&deployment.autostart){r=deployment_start();if(r!=ESP_OK){locked=1;heal_at=millis()+HEAL_DELAY_MS;cJSON*j=event("deployment_start_failed");cJSON_AddNumberToObject(j,"code",r);output(j);}}
 health_start_tick();input e;
 for(;;){
  radio_heal();field_tick();cJSON*lora_event=lora_ref_tick(&neighbors,&mobile,millis(),allowed);if(lora_event)output(lora_event);
  if(__atomic_exchange_n(&callback_drops,0,__ATOMIC_RELAXED)){input_overflow_total++;output(event("input_queue_overflow"));}
  if(xQueueReceive(inputs,&e,pdMS_TO_TICKS(10))==pdTRUE){
   if((e.type==1||e.type==2)&&e.radio_epoch!=__atomic_load_n(&radio_epoch,__ATOMIC_ACQUIRE))goto input_done;
   if(e.type==3)command(e.line,e.len);
   else if(e.type==4){input_overflow_total++;output(event("uart_rx_overflow"));}
   else if(e.type==1&&active){last_rx_ms=millis();mid_id physical;memcpy(physical.mac,e.mac,6);int filtered=!allowed(physical);rf_observation(&e,filtered);if(filtered)goto input_done;
    if(e.len>=4&&!memcmp(e.data,"MT01",4)){if(have_discovery){nd_peer*peer=nd_find(&neighbors,physical);uint32_t received_boot=(uint32_t)e.data[14]|((uint32_t)e.data[15]<<8)|((uint32_t)e.data[16]<<16)|((uint32_t)e.data[17]<<24);int accepted=-2;if(peer&&peer->boot==received_boot&&nd_state(peer,millis())>0)accepted=mid_mt_receive(&mobile,physical,e.data,(size_t)e.len,e.rx_at_ms);if(accepted==1){mt_peer*r=NULL;for(unsigned i=0;i<MT_ROWS;i++)if(mobile.peers[i].used&&mid_equal(mobile.peers[i].peer,physical))r=&mobile.peers[i];if(r){cJSON*j=event("peer_position");field_id(j,"peer_id",physical);cJSON_AddNumberToObject(j,"peer_boot",r->board_boot);cJSON_AddNumberToObject(j,"announcement_seq",r->announcement_seq);position_fields(j,mid_mt_aged(r->position,millis()-r->at));output(j);}}else if(accepted==-2)mobile.rejected++;}goto input_done;}
    if(route_mode&&e.len>=4&&!memcmp(e.data,"SR01",4)){route_tick();uint64_t start=(uint64_t)esp_timer_get_time();int observed_result=sr_receive(&router,physical,e.data,(size_t)e.len,millis());if(!observed_result){sr_packet seen;if(!sr_decode(&seen,e.data,(size_t)e.len))field_catalog(&seen);}uint64_t cost=(uint64_t)esp_timer_get_time()-start;route_process_us+=cost;if(cost>route_process_max_us)route_process_max_us=cost;route_events();goto input_done;}
    mid_packet p;if(mid_decode(&p,e.data,(size_t)e.len)==0){if(have_discovery){mid_id source;memcpy(source.mac,e.mac,6);if(p.kind==1){mid_packet reply;int r=nd_receive(&neighbors,source,&p,e.rx_at_ms,&reply);if(r==1)enqueue(reply,source);}else if(!route_mode&&p.size>=6&&p.size<=6+MID_PAYLOAD&&mid_equal(source,p.origin)&&nd_direct(&neighbors,source,p.boot,millis()))(void)data_packet(&p,1);}else if(p.kind==1)(void)config_packet(&p);else if(p.size>=6)(void)data_packet(&p,1);}else output(event("invalid_frame"));}
   else if(e.type==2&&waiting&&telemetry_waiting&&e.mac[0]==255){if(e.ok)telemetry_link_ok++;else telemetry_link_fail++;waiting=telemetry_waiting=0;if(stopping)close_radio();}
   else if(e.type==2&&waiting&&!telemetry_waiting&&route_waiting&&!memcmp(e.mac,route_pending.next.mac,6)){sr_tx_result(&router,&route_pending,e.ok,millis());if(e.ok)route_link_ok++;else{route_link_fail++;neighbor_demand(route_pending.next);}if(sr_base_type(route_pending.packet.type)==SR_DATA)route_observation(e.ok?"tx_link_ok":"tx_link_fail",e.ok?MID_DISPLAY_EV_TX_LINK_OK:MID_DISPLAY_EV_TX_LINK_FAIL,&route_pending.packet,&route_pending.next,e.ok?0:-1);waiting=route_waiting=0;if(stopping)close_radio();}
   else if(e.type==2&&waiting&&!telemetry_waiting&&!route_waiting&&!memcmp(e.mac,pending.next.mac,6)){if(have_discovery&&pending.packet.kind==1){if(e.ok)control_link_ok++;else control_link_fail++;}observation(e.ok?"tx_link_ok":"tx_link_fail",pending.packet.kind==2?(e.ok?MID_DISPLAY_EV_TX_LINK_OK:MID_DISPLAY_EV_TX_LINK_FAIL):0,&pending.packet,&pending.next,e.ok?0:-1);waiting=0;if(stopping)close_radio();}
  }
input_done:
  if(waiting&&telemetry_waiting&&millis()-submitted>=1000){telemetry_link_fail++;waiting=telemetry_waiting=0;callback_timeouts++;locked=1;heal_at=millis()+HEAL_DELAY_MS;stop_all();output(event("telemetry_callback_timeout"));}
  if(waiting&&!telemetry_waiting&&route_waiting&&millis()-submitted>=1000){sr_tx_unknown(&router,&route_pending,millis());waiting=route_waiting=0;callback_timeouts++;locked=1;heal_at=millis()+HEAL_DELAY_MS;stop_all();output(event("route_callback_timeout"));}
  if(waiting&&!telemetry_waiting&&!route_waiting&&millis()-submitted>=1000){observation("callback_timeout",pending.packet.kind==2?MID_DISPLAY_EV_TX_TIMEOUT:0,&pending.packet,&pending.next,-5);waiting=0;callback_timeouts++;locked=1;heal_at=millis()+HEAL_DELAY_MS;stop_all();}
  if(active&&have_discovery){if(route_mode)route_tick();discovery_tick();pump();if(route_mode)route_pump();}
  if(active&&!have_discovery){uint16_t draws[2];for(unsigned f=0;f<2;f++){uint32_t x;do{x=esp_random();}while(x==UINT32_MAX);draws[f]=(uint16_t)(x%65535);}if(mid_tick(&node,millis(),draws)==1){if(applied_pending){mid_packet p={.kind=1,.origin=node.publisher,.boot=node.publisher_boot,.seq=node.config_seq};observation("config_applied",MID_DISPLAY_EV_CFG_APPLIED,&p,NULL,0);applied_pending=0;}for(unsigned f=0;f<node.table.k;f++){cJSON*j=event("route_selected");cJSON_AddNumberToObject(j,"flow",f);field_id(j,"src",node.table.nodes[node.table.src[f]]);field_id(j,"dst",node.table.nodes[node.table.dst[f]]);if(node.next[f]>=0)field_id(j,"next_hop",node.table.nodes[node.next[f]]);else cJSON_AddNullToObject(j,"next_hop");output(j);}}pump();}
  telemetry_pump();status_display();fflush(stdout);health_start_tick();__atomic_fetch_add(&main_progress,1,__ATOMIC_RELEASE);if(main_wdt_registered)(void)esp_task_wdt_reset();
 }
}






