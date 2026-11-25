/* Extracted/adapted from H-004's physically confirmed OLED driver. EoRa-HUB-400TB only. */
#include "mid_display.h"
#include <stdatomic.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "sdkconfig.h"
#if !CONFIG_IDF_TARGET_ESP32S3
#error "mid_display backend is scoped to ESP32-S3 / EoRa-HUB-400TB"
#endif

static QueueHandle_t snapshots;
static mid_display_identity identity;
static atomic_int state=ATOMIC_VAR_INIT(MID_DISPLAY_HW_OFF);
static const char *TAG="mid_display";
mid_display_hw_state mid_display_hardware_state(void) {
    return (mid_display_hw_state)atomic_load(&state);
}
static void worker(void *unused) {
    (void)unused;
    i2c_master_bus_handle_t bus=NULL;i2c_master_dev_handle_t dev=NULL;
    esp_err_t error;
    uint8_t transfer[1+MID_DISPLAY_FRAME_BYTES];mid_display_snapshot view;
    unsigned page=0;int previous=1,stable=1,ready=0;
    int64_t changed=0,next_draw=0,manual_until=0,hold_until=0;
    mid_display_snapshot visible;int have_visible=0;
    /* start() has already queued a complete immutable snapshot. */
    if(xQueueReceive(snapshots,&view,0)!=pdTRUE){error=ESP_ERR_INVALID_STATE;goto done;}
    gpio_config_t outputs={.pin_bit_mask=(1ULL<<36)|(1ULL<<21),.mode=GPIO_MODE_OUTPUT};
    error=gpio_config(&outputs);if(error!=ESP_OK)goto done;
    error=gpio_set_level(GPIO_NUM_36,1);if(error!=ESP_OK)goto done;
    error=gpio_set_level(GPIO_NUM_21,0);if(error!=ESP_OK)goto done;
    vTaskDelay(pdMS_TO_TICKS(20));
    error=gpio_set_level(GPIO_NUM_21,1);if(error!=ESP_OK)goto done;
    vTaskDelay(pdMS_TO_TICKS(30));
    gpio_config_t button={.pin_bit_mask=1ULL<<0,.mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE};
    error=gpio_config(&button);if(error!=ESP_OK)goto done;
    i2c_master_bus_config_t cfg={.i2c_port=0,.sda_io_num=18,.scl_io_num=17,
        .clk_source=I2C_CLK_SRC_DEFAULT,.glitch_ignore_cnt=7,.flags.enable_internal_pullup=true};
    error=i2c_new_master_bus(&cfg,&bus);if(error!=ESP_OK)goto done;
    uint16_t address=0x3c;error=i2c_master_probe(bus,address,50);
    if(error!=ESP_OK){address=0x3d;error=i2c_master_probe(bus,address,50);}
    if(error!=ESP_OK)goto done;
    i2c_device_config_t device={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=address,.scl_speed_hz=400000};
    error=i2c_master_bus_add_device(bus,&device,&dev);if(error!=ESP_OK)goto done;
    const uint8_t init[]={0x00,0xae,0xd5,0x80,0xa8,0x3f,0xd3,0x00,0x40,
        0x8d,0x14,0x20,0x00,0xa1,0xc8,0xda,0x12,0x81,0x7f,0xd9,0xf1,0xdb,0x40,0xa4,0xa6,0x2e,0xaf};
    error=i2c_master_transmit(dev,init,sizeof(init),50);if(error!=ESP_OK)goto done;
    for(;;){
        (void)xQueueReceive(snapshots,&view,pdMS_TO_TICKS(20));
        int64_t now=esp_timer_get_time();int level=gpio_get_level(GPIO_NUM_0);
        if(level!=previous){previous=level;changed=now;}
        if(level!=stable&&now-changed>=40000){
            stable=level;if(!stable){page=(page+1)%MID_DISPLAY_PAGE_COUNT;manual_until=now+5000000;next_draw=0;ESP_LOGI(TAG,"page=%u",page);}
        }
        if(page&&now>=manual_until){page=0;next_draw=0;}
        int same=have_visible&&visible.business_ref.valid==view.business_ref.valid&&visible.business_ref.seq==view.business_ref.seq&&visible.business_ref.boot==view.business_ref.boot&&!memcmp(visible.business_ref.origin,view.business_ref.origin,6);
        if(!have_visible||!visible.business_ref.valid||same||now>=hold_until){
            if(!have_visible||!same)hold_until=now+1500000;
            visible=view;have_visible=1;
        }
        if(now>=next_draw){
            next_draw=now+250000;transfer[0]=0x40;mid_display_render(page?&view:&visible,page,transfer+1);
            const uint8_t window[]={0x00,0x21,0,127,0x22,0,7};
            error=i2c_master_transmit(dev,window,sizeof(window),50);if(error!=ESP_OK)goto done;
            error=i2c_master_transmit(dev,transfer,sizeof(transfer),50);if(error!=ESP_OK)goto done;
            if(!ready){
                ready=1;atomic_store(&state,MID_DISPLAY_HW_READY);
                ESP_LOGI(TAG,"ready: api=%u label=%c address=0x%02x first-frame=1024 PRG=page-only",MID_DISPLAY_API_VERSION,view.identity.label,address);
            }
        }
    }
done:
    atomic_store(&state,MID_DISPLAY_HW_FAILED);
    ESP_LOGW(TAG,"display stopped: %s; protocol unaffected",esp_err_to_name(error));
    if(dev)i2c_master_bus_rm_device(dev);
    if(bus)i2c_del_master_bus(bus);
    /* Never disable the shared GPIO36 peripheral supply on an OLED failure.
       Keep the one-slot queue allocated: publisher/worker never race a delete. */
    vTaskDelete(NULL);
}
int mid_display_start(const mid_display_snapshot *initial) {
    if(mid_display_validate(initial))return -1;
    int expected=MID_DISPLAY_HW_OFF;
    if(!atomic_compare_exchange_strong(&state,&expected,MID_DISPLAY_HW_STARTING))return -1;
    identity=initial->identity;snapshots=xQueueCreate(1,sizeof(*initial));
    if(!snapshots){atomic_store(&state,MID_DISPLAY_HW_FAILED);return -1;}
    xQueueOverwrite(snapshots,initial);
    if(xTaskCreate(worker,"mid_oled",6144,NULL,1,NULL)!=pdPASS){
        vQueueDelete(snapshots);snapshots=NULL;atomic_store(&state,MID_DISPLAY_HW_FAILED);return -1;
    }
    return 0;
}
int mid_display_publish(const mid_display_snapshot *snapshot) {
    mid_display_hw_state status=mid_display_hardware_state();
    if((status!=MID_DISPLAY_HW_STARTING&&status!=MID_DISPLAY_HW_READY)||!snapshots||mid_display_validate(snapshot))return -1;
    if(memcmp(snapshot->identity.mac,identity.mac,6)||snapshot->identity.label!=identity.label||
       snapshot->identity.protocol!=identity.protocol||snapshot->identity.channel!=identity.channel)return -1;
    return xQueueOverwrite(snapshots,snapshot)==pdTRUE?0:-1;
}
