#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "peer_cache_mac.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_NO_MEM -10
#define WIFI_IF_STA 0
#define CHANNEL 11
typedef struct {uint8_t peer_addr[6];int channel,ifidx,encrypt;} esp_now_peer_info_t;
static uint8_t peers[20][6];static unsigned used;static int fail_add,fail_del;static uint64_t clock_ms;
static uint64_t millis(void){return ++clock_ms;}
static int esp_now_is_peer_exist(const uint8_t mac[6]){for(unsigned i=0;i<used;i++)if(!memcmp(mac,peers[i],6))return 1;return 0;}
static esp_err_t esp_now_del_peer(const uint8_t mac[6]){
 if(fail_del)return -11;
 for(unsigned i=0;i<used;i++)if(!memcmp(mac,peers[i],6)){used--;memcpy(peers[i],peers[used],6);return ESP_OK;}
 return -12;
}
static esp_err_t esp_now_add_peer(const esp_now_peer_info_t*p){
 if(fail_add)return -13;
 if(used==20)return -14;
 memcpy(peers[used++],p->peer_addr,6);return ESP_OK;
}
#include "sdk_peer_adapter.inc"
static void addr(uint8_t out[6],unsigned i){memset(out,0,6);out[0]=2;out[5]=(uint8_t)(i+1);}
int main(void){
 uint8_t mac[6],broadcast[6]={255,255,255,255,255,255};
 assert(e1_ensure_peer(broadcast)==ESP_OK);
 for(unsigned i=0;i<19;i++){addr(mac,i);assert(e1_ensure_peer(mac)==ESP_OK);}
 assert(used==20 && e1_peers.count==20);
 addr(mac,19);fail_del=1;assert(e1_ensure_peer(mac)==-11);fail_del=0;
 assert(used==20 && e1_peers.count==20 && esp_now_is_peer_exist(broadcast));
 fail_add=1;assert(e1_ensure_peer(mac)==-13);fail_add=0;
 assert(used==19 && e1_peers.count==19 && esp_now_is_peer_exist(broadcast));
 assert(e1_ensure_peer(mac)==ESP_OK && used==20 && e1_peers.count==20);
 for(unsigned i=20;i<120;i++){addr(mac,i%30);assert(e1_ensure_peer(mac)==ESP_OK);assert(used==20 && e1_peers.count==20);}
 assert(esp_now_is_peer_exist(broadcast));
 puts("PASS SDK adapter, bounded churn, delete/add failure rollback");
 return 0;
}
