/* LR1121 SWDR001 v2.4.1 HAL, adapted from official EBytes BSP.
 * Pin/TCXO/RF switch/0dBm PA provenance is in SOURCES.md and upstream notices.
 * Unlike reference HAL, BUSY waits are bounded and yield to Wi-Fi/main tasks. */
#include "port.h"
#include "lr11xx_hal.h"
#include "lr11xx_regmem.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
#include <string.h>
static spi_device_handle_t spi;
static int opened,active;
static lref_config applied;
uint32_t lref_chip_fw,lref_chip_type,lref_chip_errors;

/* PA output mapping generated from the EBytes reference tables
 * (vendor/reference/ebytes_esp32_lr1121.c): one entry per dBm, contiguous.
 * power==0 selects the same LP/VREG/duty0/hp0 + register 3 combination this file
 * hard-coded before, so the default configuration is bit-for-bit unchanged. */
typedef struct{int8_t dbm;uint8_t sel,supply,duty,hp;int8_t reg;}lref_pa_step;
#define LREF_PA_LP LR11XX_RADIO_PA_SEL_LP
#define LREF_PA_HP LR11XX_RADIO_PA_SEL_HP
#define LREF_PA_HF LR11XX_RADIO_PA_SEL_HF
#define LREF_SUPPLY_VREG LR11XX_RADIO_PA_REG_SUPPLY_VREG
#define LREF_SUPPLY_VBAT LR11XX_RADIO_PA_REG_SUPPLY_VBAT
static const lref_pa_step LREF_PA_LF_TABLE[]={
 {-17,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-15},
 {-16,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-14},
 {-15,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-13},
 {-14,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-12},
 {-13,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-11},
 {-12,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-9},
 {-11,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-8},
 {-10,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-7},
 {-9,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-6},
 {-8,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-5},
 {-7,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-4},
 {-6,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-3},
 {-5,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-2},
 {-4,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,-1},
 {-3,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,0},
 {-2,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,1},
 {-1,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,2},
 {0,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,3},
 {1,LREF_PA_LP,LREF_SUPPLY_VREG,1,0,3},
 {2,LREF_PA_LP,LREF_SUPPLY_VREG,1,0,4},
 {3,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,7},
 {4,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,8},
 {5,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,9},
 {6,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,10},
 {7,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,12},
 {8,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,13},
 {9,LREF_PA_LP,LREF_SUPPLY_VREG,0,0,14},
 {10,LREF_PA_LP,LREF_SUPPLY_VREG,1,0,13},
 {11,LREF_PA_LP,LREF_SUPPLY_VREG,2,0,13},
 {12,LREF_PA_LP,LREF_SUPPLY_VREG,2,0,14},
 {13,LREF_PA_LP,LREF_SUPPLY_VREG,3,0,14},
 {14,LREF_PA_LP,LREF_SUPPLY_VREG,4,0,14},
 {15,LREF_PA_LP,LREF_SUPPLY_VREG,7,0,14},
 {16,LREF_PA_HP,LREF_SUPPLY_VBAT,1,4,22},
 {17,LREF_PA_HP,LREF_SUPPLY_VBAT,2,4,22},
 {18,LREF_PA_HP,LREF_SUPPLY_VBAT,1,6,22},
 {19,LREF_PA_HP,LREF_SUPPLY_VBAT,3,5,22},
 {20,LREF_PA_HP,LREF_SUPPLY_VBAT,3,7,22},
 {21,LREF_PA_HP,LREF_SUPPLY_VBAT,4,6,22},
 {22,LREF_PA_HP,LREF_SUPPLY_VBAT,4,7,22},
};
static const lref_pa_step LREF_PA_HF_TABLE[]={
 {-18,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-18},
 {-17,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-18},
 {-16,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-17},
 {-15,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-16},
 {-14,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-15},
 {-13,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-14},
 {-12,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-14},
 {-11,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-12},
 {-10,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-10},
 {-9,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-9},
 {-8,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-8},
 {-7,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-7},
 {-6,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-6},
 {-5,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-5},
 {-4,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-4},
 {-3,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-3},
 {-2,LREF_PA_HF,LREF_SUPPLY_VREG,3,0,-2},
 {-1,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,-1},
 {0,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,0},
 {1,LREF_PA_HF,LREF_SUPPLY_VREG,0,0,1},
 {2,LREF_PA_HF,LREF_SUPPLY_VREG,0,0,2},
 {3,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,4},
 {4,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,5},
 {5,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,6},
 {6,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,7},
 {7,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,8},
 {8,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,9},
 {9,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,10},
 {10,LREF_PA_HF,LREF_SUPPLY_VREG,4,0,11},
 {11,LREF_PA_HF,LREF_SUPPLY_VREG,3,0,12},
 {12,LREF_PA_HF,LREF_SUPPLY_VREG,1,0,13},
 {13,LREF_PA_HF,LREF_SUPPLY_VREG,0,0,13},
};

static const lref_pa_step*lref_pa_for(const lref_config*c){
 const lref_pa_step*t;unsigned n;int32_t p=c->power;
 if(c->frequency<1000000000u){t=LREF_PA_LF_TABLE;n=(unsigned)(sizeof(LREF_PA_LF_TABLE)/sizeof(LREF_PA_LF_TABLE[0]));}
 else{t=LREF_PA_HF_TABLE;n=(unsigned)(sizeof(LREF_PA_HF_TABLE)/sizeof(LREF_PA_HF_TABLE[0]));}
 if(p<t[0].dbm)p=t[0].dbm;
 if(p>(int32_t)t[n-1].dbm)p=(int32_t)t[n-1].dbm;
 return &t[p-(int32_t)t[0].dbm];
}
static uint64_t now_ms(void){return (uint64_t)esp_timer_get_time()/1000;}
static int idle(void){uint64_t until=now_ms()+200;/* BUSY is normally deasserted within microseconds. Polling straight into a
 * 2-tick (20 ms at 100 Hz) delay made every SPI command pay a full tick and a
 * band switch cost ~100 ms. Spin briefly first, then yield only for long waits. */for(int spin=0;spin<400;spin++){if(!gpio_get_level(GPIO_NUM_13))return 0;esp_rom_delay_us(5);}while(gpio_get_level(GPIO_NUM_13)){if(now_ms()>=until)return -1;vTaskDelay(pdMS_TO_TICKS(1)+1);}return 0;}
static int transfer(const uint8_t*tx,uint8_t*rx,unsigned n){spi_transaction_t t={.length=n*8,.tx_buffer=tx,.rx_buffer=rx};return !spi||n>512||spi_device_polling_transmit(spi,&t)!=ESP_OK?-1:0;}
lr11xx_hal_status_t lr11xx_hal_write(const void*c,const uint8_t*cmd,uint16_t cn,const uint8_t*data,uint16_t dn){
 (void)c;uint8_t tx[512];if((unsigned)cn+dn>sizeof(tx)||idle())return LR11XX_HAL_STATUS_ERROR;
 memcpy(tx,cmd,cn);if(dn)memcpy(tx+cn,data,dn);gpio_set_level(GPIO_NUM_8,0);int r=transfer(tx,NULL,cn+dn);gpio_set_level(GPIO_NUM_8,1);return r?LR11XX_HAL_STATUS_ERROR:LR11XX_HAL_STATUS_OK;
}
lr11xx_hal_status_t lr11xx_hal_read(const void*c,const uint8_t*cmd,uint16_t cn,uint8_t*data,uint16_t dn){
 uint8_t tx[512]={0},rx[512];if((unsigned)dn+1>sizeof(tx)||lr11xx_hal_write(c,cmd,cn,NULL,0)!=LR11XX_HAL_STATUS_OK||idle())return LR11XX_HAL_STATUS_ERROR;
 if(!dn)return LR11XX_HAL_STATUS_OK;
 gpio_set_level(GPIO_NUM_8,0);int r=transfer(tx,rx,dn+1);gpio_set_level(GPIO_NUM_8,1);if(!r)memcpy(data,rx+1,dn);return r?LR11XX_HAL_STATUS_ERROR:LR11XX_HAL_STATUS_OK;
}
lr11xx_hal_status_t lr11xx_hal_direct_read(const void*c,uint8_t*data,uint16_t n){(void)c;uint8_t tx[512]={0};if(n>512||idle())return LR11XX_HAL_STATUS_ERROR;gpio_set_level(GPIO_NUM_8,0);int r=transfer(tx,data,n);gpio_set_level(GPIO_NUM_8,1);return r?LR11XX_HAL_STATUS_ERROR:LR11XX_HAL_STATUS_OK;}
lr11xx_hal_status_t lr11xx_hal_reset(const void*c){(void)c;gpio_set_level(GPIO_NUM_12,0);vTaskDelay(pdMS_TO_TICKS(5)+1);gpio_set_level(GPIO_NUM_12,1);vTaskDelay(pdMS_TO_TICKS(5)+1);return idle()?LR11XX_HAL_STATUS_ERROR:LR11XX_HAL_STATUS_OK;}
lr11xx_hal_status_t lr11xx_hal_wakeup(const void*c){(void)c;gpio_set_level(GPIO_NUM_8,0);vTaskDelay(pdMS_TO_TICKS(1)+1);gpio_set_level(GPIO_NUM_8,1);return idle()?LR11XX_HAL_STATUS_ERROR:LR11XX_HAL_STATUS_OK;}
lr11xx_hal_status_t lr11xx_hal_abort_blocking_cmd(const void*c){return lr11xx_hal_wakeup(c);}
static lr11xx_radio_mod_params_lora_t modulation(const lref_config*c){
 lr11xx_radio_mod_params_lora_t m={.sf=(lr11xx_radio_lora_sf_t)c->sf,.bw=c->bw==125000?LR11XX_RADIO_LORA_BW_125:c->bw==250000?LR11XX_RADIO_LORA_BW_250:c->bw==500000?LR11XX_RADIO_LORA_BW_500:c->bw==203000?LR11XX_RADIO_LORA_BW_200:c->bw==406000?LR11XX_RADIO_LORA_BW_400:LR11XX_RADIO_LORA_BW_800,.cr=(lr11xx_radio_lora_cr_t)(c->cr-4)};
 m.ldro=((1u<<c->sf)*1000u/c->bw)>=16;return m;
}
static lr11xx_radio_pkt_params_lora_t packet(const lref_config*c,unsigned n){lr11xx_radio_pkt_params_lora_t p={.preamble_len_in_symb=(uint16_t)c->preamble,.header_type=LR11XX_RADIO_LORA_PKT_EXPLICIT,.pld_len_in_bytes=(uint8_t)n,.crc=LR11XX_RADIO_LORA_CRC_ON,.iq=LR11XX_RADIO_LORA_IQ_STANDARD};return p;}
uint32_t lref_toa(const lref_config*c,unsigned n){lr11xx_radio_mod_params_lora_t m=modulation(c);lr11xx_radio_pkt_params_lora_t p=packet(c,n);return lr11xx_radio_get_lora_time_on_air_in_ms(&p,&m);}
void lref_port_off(void){if(active)(void)lr11xx_system_set_standby(NULL,LR11XX_SYSTEM_STANDBY_CFG_RC);active=0;}
#define CHECK(call) do{if((call)!=LR11XX_STATUS_OK){active=0;return -1;}}while(0)
/* Shared programming path: everything that depends only on frequency, bandwidth
 * and PA settings. Full apply does chip bring-up first, then calls this; a band
 * switch calls this alone, which is what makes switching cheap. */
uint32_t lref_switch_last_us,lref_apply_last_us;
int lref_port_active(void){return active;}
static int program(const lref_config*c){
 /* Sub-GHz image calibration. The in-MHz helper encodes 4 MHz steps into a uint8
  * and cannot express 2400 MHz (600 steps), so it is skipped for 2.4 GHz; the
  * full calibrate(0x3f) above still runs. That gap is unverified on hardware. */
 if(c->frequency<1000000000u)CHECK(lr11xx_system_calibrate_image_in_mhz(NULL,(uint16_t)(c->frequency/1000000-4),(uint16_t)(c->frequency/1000000+4)));
 lr11xx_system_rfswitch_cfg_t sw={.enable=7,.standby=0,.rx=2,.tx=3,.tx_hp=1,.tx_hf=0,.gnss=4,.wifi=0};CHECK(lr11xx_system_set_dio_as_rf_switch(NULL,&sw));
 CHECK(lr11xx_radio_set_pkt_type(NULL,LR11XX_RADIO_PKT_TYPE_LORA));CHECK(lr11xx_radio_set_rf_freq(NULL,c->frequency));
 lr11xx_radio_mod_params_lora_t m=modulation(c);CHECK(lr11xx_radio_set_lora_mod_params(NULL,&m));
 /* SWDR001 documents opcode0x022B only for firmware>=0x0303.
  * Legacy transceivers keep the documented private/public opcode0x0208. */
 if(lref_chip_fw>=0x0303){CHECK(lr11xx_radio_set_lora_sync_word(NULL,(uint8_t)c->sync));}
 else{CHECK(lr11xx_radio_set_lora_public_network(NULL,c->sync==18?LR11XX_RADIO_LORA_NETWORK_PRIVATE:LR11XX_RADIO_LORA_NETWORK_PUBLIC));}
 const lref_pa_step*ps=lref_pa_for(c);
 lr11xx_radio_pa_cfg_t pa={.pa_sel=ps->sel,.pa_reg_supply=ps->supply,.pa_duty_cycle=ps->duty,.pa_hp_sel=ps->hp};CHECK(lr11xx_radio_set_pa_cfg(NULL,&pa));
 CHECK(lr11xx_radio_set_tx_params(NULL,ps->reg,LR11XX_RADIO_RAMP_48_US));
 CHECK(lr11xx_radio_set_rx_tx_fallback_mode(NULL,LR11XX_RADIO_FALLBACK_STDBY_RC));
 CHECK(lr11xx_system_set_dio_irq_params(NULL,LR11XX_SYSTEM_IRQ_TX_DONE|LR11XX_SYSTEM_IRQ_RX_DONE|LR11XX_SYSTEM_IRQ_TIMEOUT|LR11XX_SYSTEM_IRQ_CRC_ERROR|LR11XX_SYSTEM_IRQ_HEADER_ERROR,0));
 CHECK(lr11xx_system_clear_irq_status(NULL,LR11XX_SYSTEM_IRQ_ALL_MASK));
 lr11xx_radio_pkt_params_lora_t p=packet(c,208);CHECK(lr11xx_radio_set_lora_pkt_params(NULL,&p));
 return 0;
}

int lref_port_apply(const lref_config*c){
 lref_port_off();if(!c->role)return 0;uint64_t t0=(uint64_t)esp_timer_get_time();
 if(!opened){
  gpio_config_t out={.pin_bit_mask=(1ULL<<8)|(1ULL<<12)|(1ULL<<36),.mode=GPIO_MODE_OUTPUT};if(gpio_config(&out)!=ESP_OK)return -1;
  gpio_set_level(GPIO_NUM_36,1);gpio_set_level(GPIO_NUM_8,1);gpio_set_level(GPIO_NUM_12,1);
  gpio_config_t in={.pin_bit_mask=(1ULL<<13)|(1ULL<<14),.mode=GPIO_MODE_INPUT};if(gpio_config(&in)!=ESP_OK)return -1;
  spi_bus_config_t bus={.mosi_io_num=10,.miso_io_num=11,.sclk_io_num=9,.quadwp_io_num=-1,.quadhd_io_num=-1,.max_transfer_sz=512};
  if(spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_CH_AUTO)!=ESP_OK)return -1;
  spi_device_interface_config_t dev={.clock_speed_hz=2000000,.mode=0,.spics_io_num=-1,.queue_size=1};
  if(spi_bus_add_device(SPI2_HOST,&dev,&spi)!=ESP_OK){spi_bus_free(SPI2_HOST);return -1;}opened=1;
 }
 if(lr11xx_hal_reset(NULL)!=LR11XX_HAL_STATUS_OK)return -1;
 lr11xx_system_version_t v;CHECK(lr11xx_system_get_version(NULL,&v));lref_chip_fw=v.fw;lref_chip_type=v.type;
 if(v.type!=LR11XX_SYSTEM_VERSION_TYPE_LR1121)return -1;
 CHECK(lr11xx_system_clear_errors(NULL));lref_chip_errors=0;
 CHECK(lr11xx_system_set_standby(NULL,LR11XX_SYSTEM_STANDBY_CFG_RC));
 CHECK(lr11xx_system_set_reg_mode(NULL,LR11XX_SYSTEM_REG_MODE_LDO));
 CHECK(lr11xx_system_set_tcxo_mode(NULL,LR11XX_SYSTEM_TCXO_CTRL_3_0V,300));
 CHECK(lr11xx_system_calibrate(NULL,0x3f));
 if(program(c))return -1;
 uint16_t errors;CHECK(lr11xx_system_get_errors(NULL,&errors));lref_chip_errors=errors;if(errors)return -1;
 applied=*c;active=1;lref_apply_last_us=(uint32_t)((uint64_t)esp_timer_get_time()-t0);return lref_port_listen();
}
/* Change band/parameters without chip re-bring-up: standby, optional image
 * calibration for sub-GHz, reprogram, resume RX. Measured into switch_us. */
int lref_port_switch(const lref_config*c){
 if(!active||!c->role)return -1;
 uint64_t t0=(uint64_t)esp_timer_get_time();
 CHECK(lr11xx_system_set_standby(NULL,LR11XX_SYSTEM_STANDBY_CFG_RC));
 if(program(c))return -1;
 applied=*c;
 lref_switch_last_us=(uint32_t)((uint64_t)esp_timer_get_time()-t0);
 return lref_port_listen();
}

int lref_port_listen(void){
 if(!active||!applied.role)return -1;
 lr11xx_radio_pkt_params_lora_t p=packet(&applied,208);
 CHECK(lr11xx_system_set_standby(NULL,LR11XX_SYSTEM_STANDBY_CFG_RC));
 CHECK(lr11xx_radio_set_lora_pkt_params(NULL,&p));
 CHECK(lr11xx_system_clear_irq_status(NULL,LR11XX_SYSTEM_IRQ_ALL_MASK));
 CHECK(lr11xx_radio_set_rx_with_timeout_in_rtc_step(NULL,0xffffff));return 0;
}
int lref_port_rx(uint8_t*bytes,unsigned*len,int*rssi,int*snr){
 if(!active||!applied.role)return 0;
 if(!gpio_get_level(GPIO_NUM_14))return 0;
 lr11xx_system_irq_mask_t irq;CHECK(lr11xx_system_get_irq_status(NULL,&irq));CHECK(lr11xx_system_clear_irq_status(NULL,irq));
 if(irq&(LR11XX_SYSTEM_IRQ_CRC_ERROR|LR11XX_SYSTEM_IRQ_HEADER_ERROR|LR11XX_SYSTEM_IRQ_TIMEOUT))return -2;
 if(!(irq&LR11XX_SYSTEM_IRQ_RX_DONE))return 0;
 lr11xx_radio_rx_buffer_status_t b;lr11xx_radio_pkt_status_lora_t status;CHECK(lr11xx_radio_get_rx_buffer_status(NULL,&b));
 if(b.pld_len_in_bytes>208||b.pld_len_in_bytes<48)return -2;
 CHECK(lr11xx_regmem_read_buffer8(NULL,bytes,b.buffer_start_pointer,b.pld_len_in_bytes));CHECK(lr11xx_radio_get_lora_pkt_status(NULL,&status));
 *len=b.pld_len_in_bytes;*rssi=status.rssi_pkt_in_dbm;*snr=status.snr_pkt_in_db;return 1;
}
int lref_port_tx(const uint8_t*bytes,unsigned len,uint32_t*toa){
 if(!active||applied.role!=2||len>208)return -1;
 *toa=lref_toa(&applied,len);lr11xx_radio_pkt_params_lora_t p=packet(&applied,len);CHECK(lr11xx_system_set_standby(NULL,LR11XX_SYSTEM_STANDBY_CFG_RC));CHECK(lr11xx_radio_set_lora_pkt_params(NULL,&p));CHECK(lr11xx_system_clear_irq_status(NULL,LR11XX_SYSTEM_IRQ_ALL_MASK));CHECK(lr11xx_regmem_write_buffer8(NULL,bytes,(uint8_t)len));CHECK(lr11xx_radio_set_tx(NULL,*toa+1000));
 return 0;
}
/* Worker polls completion without busy-waiting and owns all SPI operations. */
int lref_port_tx_done(void){lr11xx_system_irq_mask_t irq;if(!active)return -1;CHECK(lr11xx_system_get_irq_status(NULL,&irq));if(irq&LR11XX_SYSTEM_IRQ_TX_DONE){CHECK(lr11xx_system_clear_irq_status(NULL,irq));return 1;}if(irq&LR11XX_SYSTEM_IRQ_TIMEOUT)return -1;return 0;}

/* Worker-only. The LR1121 measures its own supply rail and die temperature, so no extra
 * hardware is needed for the two values that decide "overheating or undervoltage". */
int lref_port_health(uint16_t* vbat_mv, int16_t* temp_c) {
	uint8_t raw = 0;
	uint16_t t = 0;
	if (!active) return 0;
	if (vbat_mv) {
		if (lr11xx_system_get_vbat(NULL, &raw) == LR11XX_STATUS_OK) {
			/* Datasheet: Vbat = (5 * raw / 255 - 1) * Vana, Vana typ. 1.35 V. */
			int32_t mv = (6750 * (int32_t)raw) / 255 - 1350;
			if (mv < 0) mv = 0;
			if (mv > 6000) mv = 6000;
			*vbat_mv = (uint16_t)mv;
		} else {
			*vbat_mv = 0;
		}
	}
	if (temp_c) {
		if (lr11xx_system_get_temp(NULL, &t) == LR11XX_STATUS_OK) {
			/* Datasheet: T = (raw/2047 * Vana - Vbe25) * 1000/VbeSlope + 25 */
			float c = ((float)(t & 0x7FFu) / 2047.0f * 1.35f - 0.7295f) * (1000.0f / -1.7f) + 25.0f;
			if (c < -40.0f) c = -40.0f;
			if (c > 125.0f) c = 125.0f;
			*temp_c = (int16_t)c;
		} else {
			*temp_c = -128;
		}
	}
	return 1;
}
