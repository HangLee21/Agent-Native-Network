/* Actual app_main included unchanged; SDK/RTOS and radio below are synthetic. */
#include "native_platform.h"
#include "app_main.c"
#include <assert.h>
#include <setjmp.h>
#include <stdlib.h>
static uint64_t probe_clock;
static int probe_mode,probe_step,probe_rx_index,probe_rand_calls;
static jmp_buf probe_end;
static input probe_events[64];static unsigned probe_in,probe_out;
static uint8_t probe_frames[8][250];static int probe_lengths[8],probe_count;
static void (*probe_recv)(const esp_now_recv_info_t *,const uint8_t *,int);
static void (*probe_sent)(const esp_now_send_info_t *,esp_now_send_status_t);
static const mid_id probe_A={{0x90,0xda,0x72,0x48,0xa4,0xf8}},probe_B={{0x90,0xda,0x72,0x48,0xa5,0xcc}};
static mid_packet probe_config(void){mid_table t={0};t.n=2;t.k=2;t.nodes[0]=probe_A;t.nodes[1]=probe_B;t.src[0]=0;t.dst[0]=1;t.src[1]=1;t.dst[1]=0;t.w[0][0][1]=65535;t.w[1][1][0]=65535;mid_packet p={.kind=1,.ttl=8,.origin=probe_A,.boot=101,.seq=1};p.size=(uint16_t)mid_table_encode(&t,p.body,sizeof(p.body));return p;}
static int probe_command(input *e,const char *text){e->type=3;e->len=(int)strlen(text);assert((size_t)e->len<sizeof(e->line));strcpy(e->line,text);printf("HOST_TX %s\n",text);return pdTRUE;}
QueueHandle_t xQueueCreate(unsigned n,unsigned bytes){assert(n==16&&bytes==sizeof(input));return (void*)1;}
int xQueueSend(QueueHandle_t q,const void *e,unsigned wait){(void)wait;assert(q==(void*)1&&probe_in<64);probe_events[probe_in++]=*(const input*)e;return pdTRUE;}
int xQueueReceive(QueueHandle_t q,void *ptr,unsigned wait){
 assert(q==(void*)1&&wait==10);probe_clock+=10;input *e=ptr;
 if(probe_out<probe_in){*e=probe_events[probe_out++];return pdTRUE;}
 if(probe_clock>6500)longjmp(probe_end,1);
 if(probe_step==0){probe_step++;return probe_command(e,"{\"cmd\":\"info\",\"nonce\":\"identify\"}");}
 if(probe_step==1){probe_step++;return probe_command(e,"{\"cmd\":\"send\",\"nonce\":\"before-start\",\"dst\":\"90:da:72:48:a5:cc\",\"payload_hex\":\"00\"}");}
 if(probe_step==2){probe_step++;return probe_command(e,"{\"cmd\":\"info\",\"cmd\":\"stop\",\"nonce\":\"duplicate\"}");}
 if(probe_step==3){probe_step++;return probe_command(e,"{\"cmd\":\"start\",\"nonce\":\"start\",\"publisher\":\"90:da:72:48:a4:f8\",\"publisher_boot\":101}");}
 if(probe_step==4&&probe_clock>=100){probe_step++;mid_packet p=probe_config();uint8_t frame[250];int len=mid_encode(&p,frame,sizeof(frame));
  if(probe_mode==1){esp_now_recv_info_t info={0};memcpy(info.src_addr,probe_A.mac,6);probe_recv(&info,frame,len);return pdFALSE;}
  char hex[501],cmd[700];for(int i=0;i<len;i++)snprintf(hex+2*i,3,"%02x",frame[i]);snprintf(cmd,sizeof(cmd),"{\"cmd\":\"config\",\"nonce\":\"config\",\"frame_hex\":\"%s\"}",hex);
  if(probe_mode==2){/* B cannot originate publisher A's config: inject received frame instead. */esp_now_recv_info_t info={0};memcpy(info.src_addr,probe_A.mac,6);probe_recv(&info,frame,len);return pdFALSE;}
  return probe_command(e,cmd);
 }
 if(probe_mode==1&&probe_step==5&&probe_clock>=700&&probe_rx_index<probe_count){esp_now_recv_info_t info={0};memcpy(info.src_addr,probe_A.mac,6);int i=probe_rx_index++;probe_recv(&info,probe_frames[i],probe_lengths[i]);if(probe_rx_index==probe_count)probe_step=10;return pdFALSE;}
 if(probe_mode!=1&&probe_step>=5&&probe_step<10&&probe_clock>=700+(uint64_t)(probe_step-5)*500){
  char cmd[300];const char*dst=probe_mode==2?"90:da:72:48:a4:f8":"90:da:72:48:a5:cc";
  snprintf(cmd,sizeof(cmd),"{\"cmd\":\"send\",\"nonce\":\"pkt-%d\",\"dst\":\"%s\",\"payload_hex\":\"%032x\"}",probe_step-4,dst,probe_step-4);probe_step++;return probe_command(e,cmd);
 }
 if(probe_step==10&&probe_clock>=3500){probe_step++;return probe_command(e,"{\"cmd\":\"stop\",\"nonce\":\"stop\"}");}
 if(probe_step==11&&probe_clock>=3550){probe_step++;return probe_command(e,"{\"cmd\":\"stats\",\"nonce\":\"final\"}");}
 if(probe_mode==3&&probe_step==12){probe_step++;return probe_command(e,"{\"cmd\":\"start\",\"nonce\":\"restart\",\"publisher\":\"90:da:72:48:a4:f8\",\"publisher_boot\":101}");}
 return pdFALSE;
}
int xTaskCreate(void (*f)(void *),const char *n,unsigned stack,void *arg,unsigned priority,void *handle){(void)f;(void)n;(void)stack;(void)arg;(void)priority;(void)handle;return pdPASS;}
void vTaskDelay(unsigned n){probe_clock+=n;}
void vTaskPrioritySet(void*p,unsigned n){(void)p;assert(n==5);}
int64_t esp_timer_get_time(void){return (int64_t)probe_clock*1000;}
uint32_t esp_random(void){if(!probe_rand_calls++)return probe_mode==1||probe_mode==2?203:101;return 0;}
int esp_netif_init(void){return 0;}int esp_event_loop_create_default(void){return 0;}int esp_wifi_init(const wifi_init_config_t*c){assert(c);return 0;}
int esp_wifi_set_storage(int n){(void)n;return 0;}int esp_wifi_set_mode(int n){(void)n;return 0;}int esp_wifi_start(void){return 0;}int esp_wifi_set_ps(int n){(void)n;return 0;}
int esp_wifi_set_channel(int c,int s){(void)s;assert(c==6);return 0;}int esp_now_init(void){return 0;}
int esp_now_register_recv_cb(void (*f)(const esp_now_recv_info_t *,const uint8_t *,int)){probe_recv=f;return 0;}
int esp_now_register_send_cb(void (*f)(const esp_now_send_info_t *,esp_now_send_status_t)){probe_sent=f;return 0;}
int esp_now_deinit(void){return 0;}int esp_wifi_stop(void){return 0;}
int esp_now_is_peer_exist(const uint8_t*m){assert(m);return 1;}int esp_now_add_peer(const esp_now_peer_info_t*p){assert(p);return 0;}
int esp_now_send(const uint8_t*to,const uint8_t*data,size_t size){
 mid_packet p;assert(!mid_decode(&p,data,size));if(p.kind==2){printf("{\"probe_wire_hex\":\"");for(size_t i=0;i<size;i++)printf("%02x",data[i]);puts("\"}");}
 if(probe_mode!=3){esp_now_send_info_t info;memcpy(info.des_addr,to,6);probe_sent(&info,ESP_NOW_SEND_SUCCESS);}return 0;
}
int esp_read_mac(uint8_t*m,int n){(void)n;memcpy(m,probe_mode==1||probe_mode==2?probe_B.mac:probe_A.mac,6);return 0;}int nvs_flash_init(void){return 0;}
int mid_display_start(const mid_display_snapshot*s){assert(!mid_display_validate(s));return 0;}
int mid_display_publish(const mid_display_snapshot*s){assert(!mid_display_validate(s));return 0;}
mid_display_hw_state mid_display_hardware_state(void){return MID_DISPLAY_HW_STARTING;}
int main(int argc,char**argv){assert(argc>=2);probe_mode=atoi(argv[1]);
 if(probe_mode==1){assert(argc==3);FILE*f=fopen(argv[2],"r");assert(f);char hex[502];while(fscanf(f,"%500s",hex)==1){int n=unhex(hex,probe_frames[probe_count],250);assert(n>0&&probe_count<7);probe_lengths[probe_count++]=n;}fclose(f);assert(probe_count==5);}
 if(!setjmp(probe_end))app_main();
 assert(!radio&&!active&&!waiting&&!stopping);assert(!screen.counts.ann_confirmed);assert(!strcmp(mid_display_destination_text(&screen),probe_mode==1?"NO TX":"UNCONFIRMED"));
 if(probe_mode==0||probe_mode==2)assert(screen.counts.queued==5&&screen.counts.link_ok==5);
 if(probe_mode==1)assert(screen.counts.rx_dest==5);
 if(probe_mode==3){assert(locked);}return 0;}
