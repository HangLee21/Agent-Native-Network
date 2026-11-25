/* MID bounded candidate execution adapter, ESP-IDF 5.5.1. No ANN/ACK logic. */
#include "mid.h"
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
#include "nvs_flash.h"
#include "cJSON.h"
#define CHANNEL 6
#define SERIAL_MAX 1024
typedef struct {int type,len,ok;uint8_t mac[6];union {uint8_t data[250];char line[SERIAL_MAX+1];};} input;
typedef struct {mid_packet packet;mid_id next;uint64_t queued;} transmission;
static QueueHandle_t inputs;
static mid_node node;
static mid_id self;
static uint32_t boot,sequence;
static int active,radio,wifi_ready,waiting,stopping,locked;
static volatile unsigned callback_drops;
static transmission pending,txq[16];static unsigned head,count;
static uint64_t submitted,last_publish;static int applied_pending;
static mid_display_snapshot screen;
static uint64_t millis(void){return (uint64_t)esp_timer_get_time()/1000;}
static void mac_text(mid_id id,char out[18]){snprintf(out,18,"%02x:%02x:%02x:%02x:%02x:%02x",id.mac[0],id.mac[1],id.mac[2],id.mac[3],id.mac[4],id.mac[5]);}
static void field_id(cJSON*j,const char*key,mid_id id){char s[18];mac_text(id,s);cJSON_AddStringToObject(j,key,s);}
static cJSON* event(const char*kind){cJSON*j=cJSON_CreateObject();cJSON_AddStringToObject(j,"schema","mid.serial.v1");cJSON_AddStringToObject(j,"event",kind);field_id(j,"node_id",self);cJSON_AddNumberToObject(j,"boot_id",boot);cJSON_AddStringToObject(j,"build_id",MID_BUILD_ID);cJSON_AddNumberToObject(j,"monotonic_ms",(double)millis());return j;}
static void output(cJSON*j){char*s=cJSON_PrintUnformatted(j);if(s){puts(s);cJSON_free(s);}cJSON_Delete(j);}
static unsigned flow_of(const mid_packet*p){mid_id dst;if(p->kind!=2||p->size<6)return UINT_MAX;memcpy(dst.mac,p->body,6);for(unsigned f=0;f<node.table.k;f++)if(mid_equal(p->origin,node.table.nodes[node.table.src[f]])&&mid_equal(dst,node.table.nodes[node.table.dst[f]]))return f;return UINT_MAX;}
static void observation(const char*name,mid_display_event_kind kind,const mid_packet*p,const mid_id*next,int code){
 mid_display_event d={.kind=kind,.at_ms=millis(),.code=code};cJSON*j=event(name);cJSON_AddNumberToObject(j,"code",code);
 if(p){field_id(j,"origin",p->origin);cJSON_AddNumberToObject(j,"origin_boot",p->boot);cJSON_AddNumberToObject(j,"seq",p->seq);
  if(p->kind==1){memcpy(d.cfg_origin,p->origin.mac,6);d.cfg_seq=p->seq;d.cfg_valid=3;}
  else if(p->size>=6){mid_id dst;memcpy(dst.mac,p->body,6);field_id(j,"dst",dst);memcpy(d.dst,dst.mac,6);memcpy(d.ref.origin,p->origin.mac,6);d.ref.boot=p->boot;d.ref.seq=p->seq;d.ref.valid=7;unsigned f=flow_of(p);if(f!=UINT_MAX){d.ref.flow=f;d.ref.valid|=8;cJSON_AddNumberToObject(j,"flow",f);}if(kind==MID_DISPLAY_EV_RX_DEST){char hex[321];unsigned n=p->size-6;for(unsigned i=0;i<n;i++)snprintf(hex+2*i,3,"%02x",p->body[6+i]);hex[2*n]=0;cJSON_AddStringToObject(j,"payload_hex",hex);}}
 }
 if(next){field_id(j,"next_hop",*next);memcpy(d.next_hop,next->mac,6);}
 cJSON_AddBoolToObject(j,"destination_confirmed",false);output(j);
 if(kind)(void)mid_display_model_apply(&screen,&d);
}
static void status_display(void){mid_display_event d={.kind=MID_DISPLAY_EV_STATUS,.at_ms=millis(),.mode=active?(node.have_table?MID_DISPLAY_ACTIVE:MID_DISPLAY_WAIT_CONFIG):MID_DISPLAY_IDLE,.routes=0};if(node.have_table)for(unsigned f=0;f<node.table.k;f++)if(node.next[f]>=0)d.routes++;(void)mid_display_model_apply(&screen,&d);if(millis()-last_publish>=250){(void)mid_display_publish(&screen);last_publish=millis();}}
static void receive_cb(const esp_now_recv_info_t*info,const uint8_t*data,int len){if(!info||!data||len<24||len>250)return;input e={.type=1,.len=len};memcpy(e.mac,info->src_addr,6);memcpy(e.data,data,(size_t)len);if(xQueueSend(inputs,&e,0)!=pdTRUE)__atomic_fetch_add(&callback_drops,1,__ATOMIC_RELAXED);}
static void send_cb(const esp_now_send_info_t*info,esp_now_send_status_t s){if(!info)return;input e={.type=2,.ok=s==ESP_NOW_SEND_SUCCESS};memcpy(e.mac,info->des_addr,6);if(xQueueSend(inputs,&e,0)!=pdTRUE)__atomic_fetch_add(&callback_drops,1,__ATOMIC_RELAXED);}
static esp_err_t radio_start(void){esp_err_t r;if(locked)return ESP_ERR_INVALID_STATE;if(!wifi_ready){wifi_init_config_t c=WIFI_INIT_CONFIG_DEFAULT();r=esp_netif_init();if(r!=ESP_OK)return r;r=esp_event_loop_create_default();if(r!=ESP_OK&&r!=ESP_ERR_INVALID_STATE)return r;r=esp_wifi_init(&c);if(r!=ESP_OK)return r;ESP_ERROR_CHECK_WITHOUT_ABORT(esp_wifi_set_storage(WIFI_STORAGE_RAM));r=esp_wifi_set_mode(WIFI_MODE_STA);if(r!=ESP_OK)return r;wifi_ready=1;}r=esp_wifi_start();if(r!=ESP_OK)return r;r=esp_wifi_set_ps(WIFI_PS_NONE);if(r==ESP_OK)r=esp_wifi_set_channel(CHANNEL,WIFI_SECOND_CHAN_NONE);if(r==ESP_OK)r=esp_now_init();if(r!=ESP_OK){esp_wifi_stop();return r;}r=esp_now_register_recv_cb(receive_cb);if(r==ESP_OK)r=esp_now_register_send_cb(send_cb);if(r!=ESP_OK){esp_now_deinit();esp_wifi_stop();return r;}radio=1;return ESP_OK;}
static void close_radio(void){if(radio){esp_now_deinit();esp_wifi_stop();radio=0;}stopping=0;}
static void stop_all(void){active=0;applied_pending=0;while(count){transmission*t=&txq[head];if(t->packet.kind==2)observation("tx_cancelled",MID_DISPLAY_EV_TX_LOCAL_FAIL,&t->packet,&t->next,-2);head=(head+1)%16;count--;}stopping=1;if(!waiting)close_radio();}
static int enqueue(mid_packet p,mid_id next){if(count==16){if(p.kind==2)observation("tx_queue_full",MID_DISPLAY_EV_TX_LOCAL_FAIL,&p,&next,-3);else observation("control_queue_full",0,&p,&next,-3);return -1;}txq[(head+count)%16]=(transmission){p,next,millis()};count++;if(p.kind==2)observation("tx_queued",MID_DISPLAY_EV_TX_QUEUED,&p,&next,0);return 0;}
static int config_packet(mid_packet*p){int r;observation("config_rx",MID_DISPLAY_EV_CFG_RECEIVED,p,NULL,0);r=mid_config(&node,p);if(r==1){applied_pending=1;if(p->ttl>1){mid_packet forward=*p;mid_id broadcast={{255,255,255,255,255,255}};forward.ttl--;enqueue(forward,broadcast);}}
 else {observation(r==0?"config_stale":"config_rejected",r==0?MID_DISPLAY_EV_CFG_STALE:MID_DISPLAY_EV_CFG_REJECTED,p,NULL,r);}
 return r;}
static int data_packet(mid_packet*p,int received){mid_id next={{0}},dst;memcpy(dst.mac,p->body,6);int r=mid_data(&node,p,&next);if(r==2)observation("rx_local",MID_DISPLAY_EV_RX_DEST,p,NULL,0);else if(r==0){if(mid_equal(dst,self))observation("rx_duplicate",MID_DISPLAY_EV_RX_DUPLICATE,p,NULL,0);}else if(r==1){if(received)observation("rx_relay",MID_DISPLAY_EV_RX_RELAY,p,NULL,0);if(received)p->ttl--;return enqueue(*p,next);}else observation("data_drop",0,p,NULL,-1);return r<0?-1:0;}
static int hexval(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
static int unhex(const char*s,uint8_t*out,size_t cap){if(!s)return -1;size_t n=strlen(s);if(n%2||n/2>cap)return -1;for(size_t i=0;i<n/2;i++){int a=hexval(s[2*i]),b=hexval(s[2*i+1]);if(a<0||b<0)return -1;out[i]=(uint8_t)((a<<4)|b);}return (int)(n/2);}
static int parse_id(const char*s,mid_id*out){char plain[13];if(!s||strlen(s)!=17)return -1;for(unsigned i=0;i<6;i++){plain[2*i]=s[3*i];plain[2*i+1]=s[3*i+1];if(i<5&&s[3*i+2]!=':')return -1;}plain[12]=0;return unhex(plain,out->mac,6)==6&&mid_unicast(*out)?0:-1;}
static const char*str(cJSON*j,const char*k){cJSON*v=cJSON_GetObjectItemCaseSensitive(j,k);return cJSON_IsString(v)?v->valuestring:NULL;}
static int u32(cJSON*j,const char*k,uint32_t*out){cJSON*v=cJSON_GetObjectItemCaseSensitive(j,k);if(!cJSON_IsNumber(v)||v->valuedouble<1||v->valuedouble>4294967295.0)return -1;*out=(uint32_t)v->valuedouble;return v->valuedouble==*out?0:-1;}
static int printable(const char*s){if(!s)return 0;size_t n=strlen(s);if(!n||n>64)return 0;for(size_t i=0;i<n;i++)if((unsigned char)s[i]<32||(unsigned char)s[i]>126)return 0;return 1;}
static void command(const char*line,int len){
 cJSON*j=NULL,*res=NULL;const char*cmd=NULL,*nonce=NULL,*why="invalid_command";int ok=0;const char*end=NULL;
 if(len>0&&len<=SERIAL_MAX)j=cJSON_ParseWithLengthOpts(line,(size_t)len+1,&end,true);
 if(!cJSON_IsObject(j))goto reply;
 for(cJSON*a=j->child;a;a=a->next)for(cJSON*b=a->next;b;b=b->next)if(!strcmp(a->string,b->string))goto reply;
 cmd=str(j,"cmd");nonce=str(j,"nonce");if(!cmd||!printable(nonce))goto reply;
 if(!strcmp(cmd,"info")||!strcmp(cmd,"stats")){ok=1;}
 else if(!strcmp(cmd,"stop")){stop_all();ok=1;}
 else if(!strcmp(cmd,"start")){
  mid_id publisher;uint32_t publisher_boot;if(active||radio||waiting||locked){why="busy_or_locked";goto reply;}
  if(parse_id(str(j,"publisher"),&publisher)||u32(j,"publisher_boot",&publisher_boot)){why="invalid_publisher";goto reply;}
  mid_init(&node,self,publisher,publisher_boot);esp_err_t r=radio_start();if(r!=ESP_OK){why="radio_start_failed";goto reply;}active=1;ok=1;
 }else if(!strcmp(cmd,"config")){
  mid_packet p;uint8_t bytes[250];int n=unhex(str(j,"frame_hex"),bytes,sizeof(bytes));
  if(!active){why="inactive";goto reply;}if(n<0||mid_decode(&p,bytes,(size_t)n)||p.kind!=1||!mid_equal(p.origin,self)||p.boot!=boot){why="invalid_local_config";goto reply;}ok=config_packet(&p)==1;if(!ok)why="config_rejected_or_stale";
 }else if(!strcmp(cmd,"send")){
  mid_packet p={.kind=2,.ttl=8,.origin=self,.boot=boot};mid_id dst;int n;
  if(!active||!node.have_table){why="inactive_or_no_config";goto reply;}if(parse_id(str(j,"dst"),&dst)){why="invalid_destination";goto reply;}
  n=unhex(str(j,"payload_hex"),p.body+6,MID_PAYLOAD);if(n<0||sequence==UINT32_MAX){why="payload_or_sequence";goto reply;}memcpy(p.body,dst.mac,6);p.size=(uint16_t)(n+6);p.seq=++sequence;ok=data_packet(&p,0)==0;if(!ok)why="no_route_or_queue_full";
 }else {why="unknown_command";}
reply:
 {mid_display_event d={.kind=MID_DISPLAY_EV_COMMAND,.at_ms=millis(),.command_ok=(uint8_t)ok};snprintf(d.command,sizeof(d.command),"%.11s",cmd?cmd:"invalid");(void)mid_display_model_apply(&screen,&d);}
 res=event("command_result");if(nonce&&printable(nonce))cJSON_AddStringToObject(res,"nonce",nonce);else cJSON_AddNullToObject(res,"nonce");cJSON_AddStringToObject(res,"cmd",cmd?cmd:"invalid");cJSON_AddBoolToObject(res,"ok",ok);if(!ok)cJSON_AddStringToObject(res,"error",why);
 cJSON_AddStringToObject(res,"mode",active?(node.have_table?"active":"wait_config"):"idle");cJSON_AddBoolToObject(res,"radio",radio);cJSON_AddBoolToObject(res,"stopping",stopping);cJSON_AddBoolToObject(res,"locked_until_reset",locked);cJSON_AddNumberToObject(res,"channel",CHANNEL);
 if(ok&&cmd&&!strcmp(cmd,"info")){cJSON_AddStringToObject(res,"firmware","mid-espnow");cJSON_AddStringToObject(res,"chip","esp32s3");cJSON_AddStringToObject(res,"board","EoRa-HUB-400TB");cJSON_AddNumberToObject(res,"display_api",1);char label[2]={screen.identity.label,0};cJSON_AddStringToObject(res,"device_label",label);}
 if(ok&&cmd&&!strcmp(cmd,"stats")){cJSON_AddNumberToObject(res,"tx_queued",screen.counts.queued);cJSON_AddNumberToObject(res,"tx_submitted",screen.counts.submitted);cJSON_AddNumberToObject(res,"link_ok",screen.counts.link_ok);cJSON_AddNumberToObject(res,"link_fail",screen.counts.link_fail);cJSON_AddNumberToObject(res,"rx_local",screen.counts.rx_dest);cJSON_AddNumberToObject(res,"rx_duplicate",screen.counts.rx_duplicate);cJSON_AddNumberToObject(res,"rx_relay",screen.counts.rx_relay);cJSON_AddNumberToObject(res,"local_fail",screen.counts.local_fail);cJSON_AddNumberToObject(res,"timeouts",screen.counts.timeouts);cJSON_AddNumberToObject(res,"faults",screen.fault_count);cJSON_AddNumberToObject(res,"config_seq",node.config_seq);cJSON_AddNumberToObject(res,"queue_depth",count);cJSON_AddNumberToObject(res,"display_hw",mid_display_hardware_state());cJSON_AddStringToObject(res,"destination_status","unconfirmed");}
 output(res);cJSON_Delete(j);
}
static void uart_reader(void*unused){(void)unused;input e={.type=3};unsigned n=0;int overflow=0;for(;;){int c=getchar();if(c==EOF){clearerr(stdin);vTaskDelay(pdMS_TO_TICKS(10));continue;}if(c=='\n'){if(n&&e.line[n-1]=='\r')n--;e.line[n]=0;e.len=overflow?SERIAL_MAX+1:(int)n;if(xQueueSend(inputs,&e,pdMS_TO_TICKS(50))!=pdTRUE)__atomic_fetch_add(&callback_drops,1,__ATOMIC_RELAXED);n=0;overflow=0;}else if(n<SERIAL_MAX)e.line[n++]=(char)c;else overflow=1;}}
static void pump(void){
 if(!active||waiting||!count){return;}
 pending=txq[head];head=(head+1)%16;count--;
 if(millis()-pending.queued>1000){observation("queue_timeout",pending.packet.kind==2?MID_DISPLAY_EV_TX_TIMEOUT:0,&pending.packet,&pending.next,-4);return;}
 uint8_t bytes[250];int len=mid_encode(&pending.packet,bytes,sizeof(bytes));esp_err_t r=len<0?ESP_ERR_INVALID_ARG:ESP_OK;
 if(r==ESP_OK&&!esp_now_is_peer_exist(pending.next.mac)){esp_now_peer_info_t peer={.channel=CHANNEL,.ifidx=WIFI_IF_STA,.encrypt=false};memcpy(peer.peer_addr,pending.next.mac,6);r=esp_now_add_peer(&peer);}
 if(r==ESP_OK)r=esp_now_send(pending.next.mac,bytes,(size_t)len);
 if(r==ESP_OK){waiting=1;submitted=millis();observation("tx_submit",pending.packet.kind==2?MID_DISPLAY_EV_TX_SUBMITTED:0,&pending.packet,&pending.next,0);}else observation("tx_api_failed",pending.packet.kind==2?MID_DISPLAY_EV_TX_LOCAL_FAIL:0,&pending.packet,&pending.next,(int)r);
}
void app_main(void){
 vTaskPrioritySet(NULL,5);esp_err_t r=nvs_flash_init();if(r!=ESP_OK){printf("MID NVS failure %d; no erase/radio\n",(int)r);return;}if(esp_read_mac(self.mac,ESP_MAC_WIFI_STA)!=ESP_OK)return;boot=esp_random()|1u;
 mid_display_identity identity={.channel=CHANNEL,.protocol=MID_DISPLAY_MID,.label='?'};memcpy(identity.mac,self.mac,6);
 const uint8_t a[6]={0x90,0xda,0x72,0x48,0xa4,0xf8},b[6]={0x90,0xda,0x72,0x48,0xa5,0xcc};if(!memcmp(self.mac,a,6))identity.label='A';else if(!memcmp(self.mac,b,6))identity.label='B';
 (void)mid_display_model_init(&screen,&identity);const char*help[5]={"JSON + nonce required","info / stats / stop","start publisher+boot","config frame_hex","send dst payload_hex"};(void)mid_display_set_help(&screen,help);(void)mid_display_start(&screen);
 inputs=xQueueCreate(16,sizeof(input));if(!inputs){output(event("input_queue_alloc_failed"));return;}if(xTaskCreate(uart_reader,"mid_uart",6144,NULL,4,NULL)!=pdPASS){output(event("uart_task_failed"));return;}output(event("boot"));input e;
 for(;;){
  if(__atomic_exchange_n(&callback_drops,0,__ATOMIC_RELAXED)){output(event("input_queue_overflow"));locked=1;stop_all();}
  if(xQueueReceive(inputs,&e,pdMS_TO_TICKS(10))==pdTRUE){
   if(e.type==3)command(e.line,e.len);
   else if(e.type==1&&active){mid_packet p;if(mid_decode(&p,e.data,(size_t)e.len)==0){if(p.kind==1)(void)config_packet(&p);else if(p.size>=6)(void)data_packet(&p,1);}else output(event("invalid_frame"));}
   else if(e.type==2&&waiting&&!memcmp(e.mac,pending.next.mac,6)){observation(e.ok?"tx_link_ok":"tx_link_fail",pending.packet.kind==2?(e.ok?MID_DISPLAY_EV_TX_LINK_OK:MID_DISPLAY_EV_TX_LINK_FAIL):0,&pending.packet,&pending.next,e.ok?0:-1);waiting=0;if(stopping)close_radio();}
  }
  if(waiting&&millis()-submitted>=1000){observation("callback_timeout",pending.packet.kind==2?MID_DISPLAY_EV_TX_TIMEOUT:0,&pending.packet,&pending.next,-5);waiting=0;locked=1;stop_all();}
  if(active){uint16_t draws[2];for(unsigned f=0;f<2;f++){uint32_t x;do{x=esp_random();}while(x==UINT32_MAX);draws[f]=(uint16_t)(x%65535);}if(mid_tick(&node,millis(),draws)==1){if(applied_pending){mid_packet p={.kind=1,.origin=node.publisher,.boot=node.publisher_boot,.seq=node.config_seq};observation("config_applied",MID_DISPLAY_EV_CFG_APPLIED,&p,NULL,0);applied_pending=0;}for(unsigned f=0;f<node.table.k;f++){cJSON*j=event("route_selected");cJSON_AddNumberToObject(j,"flow",f);field_id(j,"src",node.table.nodes[node.table.src[f]]);field_id(j,"dst",node.table.nodes[node.table.dst[f]]);if(node.next[f]>=0)field_id(j,"next_hop",node.table.nodes[node.next[f]]);else cJSON_AddNullToObject(j,"next_hop");output(j);}}pump();}
  status_display();fflush(stdout);
 }
}
