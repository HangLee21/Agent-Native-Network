/* ESP-IDF v5.5.1 adapter. No board pin or LoRa assumptions; UART0 console must be verified on arrival. */
#include "ann.h"
#include "ann_console.h"
#include "ann_log.h"
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "cJSON.h"
typedef struct {int type,len,ok;uint8_t mac[6],data[250];char command[514];} input_event;
static QueueHandle_t inputs;
static volatile unsigned callback_drops;
static ann_node node;
static ann_console console;
static int wifi_ready,radio,waiting;
static uint64_t submitted_ms;
static uint32_t tx_attempt;
static ann_out inflight;
static ann_id from_mac(const uint8_t*m){ann_id x=0;unsigned i;for(i=0;i<6;i++)x=(x<<8)|m[i];return x;}
static void to_mac(ann_id x,uint8_t*m){int i;for(i=5;i>=0;i--){m[i]=(uint8_t)x;x>>=8;}}
static uint64_t millis(void){return (uint64_t)esp_timer_get_time()/1000;}
static void send_cb(const esp_now_send_info_t*info,esp_now_send_status_t status){input_event e={0};if(!info)return;e.type=2;e.ok=status==ESP_NOW_SEND_SUCCESS;memcpy(e.mac,info->des_addr,6);if(xQueueSend(inputs,&e,0)!=pdTRUE)callback_drops++;}
static void receive_cb(const esp_now_recv_info_t*info,const uint8_t*data,int len){input_event e={0};if(!info||!data||len<112||len>250)return;e.type=1;e.len=len;memcpy(e.mac,info->src_addr,6);memcpy(e.data,data,len);if(xQueueSend(inputs,&e,0)!=pdTRUE)callback_drops++;}
static esp_err_t radio_start(void){esp_err_t r;if(radio)return ESP_OK;if(!wifi_ready){wifi_init_config_t cfg=WIFI_INIT_CONFIG_DEFAULT();r=esp_netif_init();if(r!=ESP_OK)return r;r=esp_event_loop_create_default();if(r!=ESP_OK&&r!=ESP_ERR_INVALID_STATE)return r;r=esp_wifi_init(&cfg);if(r!=ESP_OK)return r;r=esp_wifi_set_storage(WIFI_STORAGE_RAM);if(r!=ESP_OK)return r;r=esp_wifi_set_mode(WIFI_MODE_STA);if(r!=ESP_OK)return r;wifi_ready=1;}r=esp_wifi_start();if(r!=ESP_OK)return r;r=esp_wifi_set_channel(CONFIG_ANN_CHANNEL,WIFI_SECOND_CHAN_NONE);if(r!=ESP_OK){esp_wifi_stop();return r;}r=esp_now_init();if(r!=ESP_OK){esp_wifi_stop();return r;}r=esp_now_register_recv_cb(receive_cb);if(r==ESP_OK)r=esp_now_register_send_cb(send_cb);if(r!=ESP_OK){esp_now_deinit();esp_wifi_stop();return r;}radio=1;return ESP_OK;}
static void radio_stop(void){waiting=0;if(radio){esp_now_deinit();esp_wifi_stop();radio=0;}}
static esp_err_t ensure_peer(ann_id id,uint8_t*mac){esp_now_peer_info_t peer={0};if(id)to_mac(id,mac);else memset(mac,255,6);if(esp_now_is_peer_exist(mac))return ESP_OK;memcpy(peer.peer_addr,mac,6);peer.channel=CONFIG_ANN_CHANNEL;peer.ifidx=WIFI_IF_STA;peer.encrypt=false;return esp_now_add_peer(&peer);}
static void serial_reader(void*unused){input_event e={0};unsigned n=0;int overflow=0;(void)unused;for(;;){int ch=getchar();if(ch==EOF){clearerr(stdin);vTaskDelay(pdMS_TO_TICKS(10));continue;}if(ch=='\n'){e.type=3;e.len=overflow?513:(int)n;e.command[n]=0;if(xQueueSend(inputs,&e,pdMS_TO_TICKS(100))!=pdTRUE)callback_drops++;n=0;overflow=0;}else if(ch!='\r'){if(n<512)e.command[n++]=(char)ch;else overflow=1;}}}
static void adapter_error(const char*reason){printf("{\"schema\":\"ann.serial.v1\",\"event\":\"error\",\"nonce\":null,\"error\":\"%s\",\"ok\":false}\n",reason);ann_stop(&node,millis());console.armed=console.bench=0;radio_stop();}
void app_main(void){uint8_t mac[6];input_event e;char output[1200];ann_event event;uint8_t bytes[250];esp_err_t r=nvs_flash_init();/* Deliberately no automatic nvs_flash_erase. */
 if(r!=ESP_OK){printf("ANN NVS init failed (%d); no erase or radio start\n",(int)r);return;}
 if(esp_read_mac(mac,ESP_MAC_WIFI_STA)!=ESP_OK)return;
 ann_init(&node,from_mac(mac),esp_random()|1u);ann_console_init(&console,&node,"esp32s3","ann-v1-idf5.5.1");
 inputs=xQueueCreate(32,sizeof(input_event));if(!inputs)return;
 if(xTaskCreate(serial_reader,"ann_uart",4096,NULL,4,NULL)!=pdPASS){vQueueDelete(inputs);return;}
 for(;;){uint64_t now=millis();if(callback_drops){callback_drops=0;adapter_error("adapter_queue_overflow");}
  if(xQueueReceive(inputs,&e,pdMS_TO_TICKS(10))==pdTRUE){now=millis();if(e.type==3){int command_ok=ann_command(&console,e.command,(size_t)e.len,output,sizeof(output),now);if(command_ok==0&&node.active&&!radio){r=radio_start();if(r!=ESP_OK){cJSON*j=cJSON_Parse(output);ann_stop(&node,now);console.armed=console.bench=0;if(j){cJSON_ReplaceItemInObject(j,"event",cJSON_CreateString("error"));cJSON_ReplaceItemInObject(j,"ok",cJSON_CreateBool(false));cJSON_AddStringToObject(j,"error","radio_start_failed");char*s=cJSON_PrintUnformatted(j);if(s){snprintf(output,sizeof(output),"%s",s);cJSON_free(s);}cJSON_Delete(j);}}}if(!node.active)radio_stop();puts(output);}
   else if(e.type==1&&node.active){ann_packet p;uint32_t before=node.delivered;ann_receive(&node,from_mac(e.mac),e.data,(size_t)e.len,now);if(node.delivered>before&&!ann_decode(&p,e.data,(size_t)e.len)&&p.kind==ANN_ECHO&&p.dst==node.id){ann_log_echo(&console,&p,now,output,sizeof(output));puts(output);}}
   else if(e.type==2&&waiting){uint8_t expected[6];if(inflight.next)to_mac(inflight.next,expected);else memset(expected,255,6);if(!memcmp(expected,e.mac,6)){ann_tx_result(&node,&inflight,e.ok,now);ann_log_tx(&console,&inflight,"tx_result",e.ok,now,tx_attempt,output,sizeof(output));puts(output);waiting=0;}}
  }
  now=millis();ann_console_tick(&console,now);if(!node.active)radio_stop();
  if(waiting&&now-submitted_ms>=1000){ann_log_tx(&console,&inflight,"tx_result",-1,now,tx_attempt,output,sizeof(output));puts(output);adapter_error("send_callback_timeout");}
  if(radio&&!waiting&&ann_next_tx(&node,&inflight,now)){uint8_t peer[6];int z=ann_encode(&inflight.packet,bytes,sizeof(bytes));ann_log_tx(&console,&inflight,"tx_submit",0,now,++tx_attempt,output,sizeof(output));puts(output);r=z<0?ESP_ERR_INVALID_ARG:ensure_peer(inflight.next,peer);if(r==ESP_OK)r=esp_now_send(peer,bytes,(size_t)z);if(r==ESP_OK){waiting=1;submitted_ms=now;}else{ann_tx_result(&node,&inflight,0,now);ann_log_tx(&console,&inflight,"tx_result",-(int)r,now,tx_attempt,output,sizeof(output));puts(output);}}
  while(ann_next_event(&node,&event)){ann_log_event(&console,&event,output,sizeof(output));puts(output);}fflush(stdout);
 }
}
