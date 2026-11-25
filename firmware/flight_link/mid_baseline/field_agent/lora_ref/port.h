#ifndef MID_LORA_PORT_H
#define MID_LORA_PORT_H
#include <stdint.h>
#include "lr11xx_radio.h"
#include "lr11xx_system.h"
typedef struct {uint32_t magic,role,period,jitter,frequency,bw,sf,cr,preamble,sync,start;int32_t power;} lref_config;
int lref_port_apply(const lref_config*);
/* Fast band/parameter change without chip bring-up. */
int lref_port_switch(const lref_config*);
int lref_port_active(void);
extern uint32_t lref_switch_last_us,lref_apply_last_us;
void lref_port_off(void);
int lref_port_rx(uint8_t*,unsigned*,int*,int*);
/* Resume continuous RX after an RX event or completed TX. Worker-only. */
int lref_port_listen(void);
int lref_port_tx(const uint8_t*,unsigned,uint32_t*);
int lref_port_tx_done(void);
uint32_t lref_toa(const lref_config*,unsigned);
/* Worker-only: returns the radio's own supply voltage and die temperature. */
int lref_port_health(uint16_t* vbat_mv,int16_t* temp_c);
extern uint32_t lref_chip_fw,lref_chip_type,lref_chip_errors;
#endif
