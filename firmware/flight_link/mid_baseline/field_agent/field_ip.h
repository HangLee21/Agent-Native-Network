#ifndef FIELD_IP_H
#define FIELD_IP_H
#include "mid.h"
#include "cJSON.h"
#include "esp_err.h"
typedef struct {uint32_t magic,pc_id;uint8_t enabled,channel,bssid[6];char ssid[33],password[65],pc_ip[16];uint16_t listen_port,pc_port;} field_ip_config;
esp_err_t field_ip_load(void);
esp_err_t field_ip_store(const field_ip_config*);
esp_err_t field_ip_clear(void);
void field_ip_netif(void);
int field_ip_pin(uint8_t);
void field_ip_unpin(void);
void field_ip_suspend(uint64_t);
void field_ip_tick(uint64_t,int,uint8_t,mid_id,uint32_t);
int field_ip_read(char*,size_t);
int field_ip_live(uint64_t);
uint32_t field_ip_pc_id(void);
uint32_t field_ip_session(void);
uint64_t field_ip_until(void);
int field_ip_lease(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint64_t);
void field_ip_emit(cJSON*,int);
void field_ip_poll(uint64_t);
void field_ip_status(cJSON*,uint64_t);
void field_ip_export(cJSON*,uint64_t);
void field_ip_base(cJSON*,const char*);
#endif
