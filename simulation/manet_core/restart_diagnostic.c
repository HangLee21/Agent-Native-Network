#include "aodv.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static ma_node relay;
static void p32(uint8_t*p,uint32_t x){p[0]=x;p[1]=x>>8;p[2]=x>>16;p[3]=x>>24;}
int main(void){uint8_t b[MA_HEADER];ma_init(&relay,1,1);relay.route[0]=(ma_route){1,1,2,2,50,10000};memset(b,0,sizeof(b));b[0]=MA_MAGIC;b[1]=MA_VERSION;b[2]=MA_RREQ;b[3]=MA_HEADER;b[4]=4;b[5]=0;b[6]=4;p32(b+8,2);p32(b+16,1);p32(b+24,1);ma_receive(&relay,3,b,sizeof(b),1);assert(relay.route[0].valid&&relay.route[0].next==2&&relay.route[0].seq==50);puts("OBSERVED LIMITATION: new boot with reset origin sequence did not replace old reverse route; route table does not bind origin boot");return 0;}
