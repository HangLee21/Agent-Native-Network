#ifndef MID_LORA_PORT_H
#define MID_LORA_PORT_H
#include <stdint.h>
#include "lr11xx_radio.h"
#include "lr11xx_system.h"
typedef struct {uint32_t magic,role,period,jitter,frequency,bw,sf,cr,preamble,sync,start;int32_t power;} lref_config;
int lref_port_apply(const lref_config*);
void lref_port_off(void);
int lref_port_rx(uint8_t*,unsigned*,int*,int*);
int lref_port_tx(const uint8_t*,unsigned,uint32_t*);
int lref_port_tx_done(void);
uint32_t lref_toa(const lref_config*,unsigned);
extern uint32_t lref_chip_fw,lref_chip_type,lref_chip_errors;
#endif
