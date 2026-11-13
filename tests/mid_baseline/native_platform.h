#ifndef E2_NATIVE_PLATFORM_H
#define E2_NATIVE_PLATFORM_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#define pdTRUE 1
#define pdFALSE 0
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
typedef void *QueueHandle_t;
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_STATE 2
#define ESP_ERR_INVALID_ARG 3
#define ESP_MAC_WIFI_STA 0
#define WIFI_STORAGE_RAM 0
#define WIFI_MODE_STA 0
#define WIFI_PS_NONE 0
#define WIFI_SECOND_CHAN_NONE 0
#define WIFI_IF_STA 0
#define ESP_NOW_SEND_SUCCESS 0
#define ESP_ERROR_CHECK_WITHOUT_ABORT(x) ((void)(x))
typedef struct {int unused;} wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() ((wifi_init_config_t){0})
typedef struct {uint8_t src_addr[6];} esp_now_recv_info_t;
typedef struct {uint8_t des_addr[6];} esp_now_send_info_t;
typedef int esp_now_send_status_t;
typedef struct {uint8_t peer_addr[6];int channel,ifidx,encrypt;} esp_now_peer_info_t;
QueueHandle_t xQueueCreate(unsigned,unsigned);
int xQueueSend(QueueHandle_t,const void *,unsigned);
int xQueueReceive(QueueHandle_t,void *,unsigned);
int xTaskCreate(void (*)(void *),const char *,unsigned,void *,unsigned,void *);
void vTaskDelay(unsigned);
void vTaskPrioritySet(void *,unsigned);
int64_t esp_timer_get_time(void);
uint32_t esp_random(void);
int esp_netif_init(void);
int esp_event_loop_create_default(void);
int esp_wifi_init(const wifi_init_config_t *);
int esp_wifi_set_storage(int);
int esp_wifi_set_mode(int);
int esp_wifi_start(void);
int esp_wifi_set_ps(int);
int esp_wifi_set_channel(int,int);
int esp_now_init(void);
int esp_now_register_recv_cb(void (*)(const esp_now_recv_info_t *,const uint8_t *,int));
int esp_now_register_send_cb(void (*)(const esp_now_send_info_t *,esp_now_send_status_t));
int esp_now_deinit(void);
int esp_wifi_stop(void);
int esp_now_is_peer_exist(const uint8_t *);
int esp_now_add_peer(const esp_now_peer_info_t *);
int esp_now_send(const uint8_t *,const uint8_t *,size_t);
int esp_read_mac(uint8_t *,int);
int nvs_flash_init(void);
#endif
