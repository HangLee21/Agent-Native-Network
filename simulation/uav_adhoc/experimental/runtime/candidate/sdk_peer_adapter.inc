
static e1_peer_cache e1_peers;
/* This adapter is built only in the isolated engineering candidate. */
static esp_err_t e1_ensure_peer(const uint8_t mac[6]){
 e1_peer_cache next=e1_peers;uint8_t evicted[6];
 int step=e1_peer_access(&next,mac,millis(),1,evicted);
 if(step<0)return ESP_ERR_NO_MEM;
 if(step==1){esp_err_t r=esp_now_del_peer(evicted);if(r!=ESP_OK)return r;}
 if(!esp_now_is_peer_exist(mac)){
  esp_now_peer_info_t p={.channel=CHANNEL,.ifidx=WIFI_IF_STA,.encrypt=false};
  memcpy(p.peer_addr,mac,6);esp_err_t r=esp_now_add_peer(&p);
  if(r!=ESP_OK){if(step==1)e1_peer_remove(&e1_peers,evicted);return r;}
 }
 e1_peers=next;return ESP_OK;
}
