#ifndef MOCK_PLATFORM_H
#define MOCK_PLATFORM_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL 1
#define ESP_ERR_INVALID_STATE 2
#define CONFIG_IDF_TARGET_ESP32S3 1
typedef int BaseType_t;
typedef unsigned TickType_t;
#define pdTRUE 1
#define pdFALSE 0
#define pdPASS 1
#define pdMS_TO_TICKS(ms) (ms)
typedef struct mock_queue *QueueHandle_t;
QueueHandle_t xQueueCreate(unsigned length,unsigned bytes);
int xQueueOverwrite(QueueHandle_t queue,const void *data);
int xQueueReceive(QueueHandle_t queue,void *data,unsigned ticks);
void vQueueDelete(QueueHandle_t queue);
int xTaskCreate(void (*function)(void *),const char *name,unsigned stack,void *arg,unsigned priority,void *handle);
void vTaskDelay(unsigned ticks);
void vTaskDelete(void *task);
typedef struct {uint64_t pin_bit_mask;int mode,pull_up_en;} gpio_config_t;
#define GPIO_MODE_OUTPUT 1
#define GPIO_MODE_INPUT 2
#define GPIO_PULLUP_ENABLE 1
#define GPIO_NUM_36 36
#define GPIO_NUM_21 21
#define GPIO_NUM_0 0
int gpio_config(const gpio_config_t *config);
int gpio_set_level(int pin,int level);
int gpio_get_level(int pin);
typedef void *i2c_master_bus_handle_t;
typedef void *i2c_master_dev_handle_t;
typedef struct {int i2c_port,sda_io_num,scl_io_num,clk_source,glitch_ignore_cnt;struct {bool enable_internal_pullup;} flags;} i2c_master_bus_config_t;
typedef struct {int dev_addr_length;uint16_t device_address;uint32_t scl_speed_hz;} i2c_device_config_t;
#define I2C_CLK_SRC_DEFAULT 0
#define I2C_ADDR_BIT_LEN_7 0
int i2c_new_master_bus(const i2c_master_bus_config_t *config,i2c_master_bus_handle_t *bus);
int i2c_master_probe(i2c_master_bus_handle_t bus,uint16_t address,int timeout);
int i2c_master_bus_add_device(i2c_master_bus_handle_t bus,const i2c_device_config_t *config,i2c_master_dev_handle_t *dev);
int i2c_master_transmit(i2c_master_dev_handle_t dev,const uint8_t *bytes,size_t size,int timeout);
int i2c_master_bus_rm_device(i2c_master_dev_handle_t dev);
int i2c_del_master_bus(i2c_master_bus_handle_t bus);
int64_t esp_timer_get_time(void);
const char *esp_err_to_name(int error);
void mock_log(const char *format,...);
#define ESP_LOGI(tag,...) ((void)(tag),mock_log(__VA_ARGS__))
#define ESP_LOGW(tag,...) ((void)(tag),mock_log(__VA_ARGS__))
#endif
