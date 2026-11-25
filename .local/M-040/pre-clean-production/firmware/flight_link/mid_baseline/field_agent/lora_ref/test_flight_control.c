#include "flight_control.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void put16(uint8_t*p,uint16_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void put32(uint8_t*p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
static uint32_t get32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void sign_frame(uint8_t*p){put32(p+44,fc_crc32(p,44));}
static void command(uint8_t*p,const uint8_t*mac,uint32_t id){memset(p,0,48);memcpy(p,"LRC2",4);p[4]=1;p[5]=1;put16(p+6,48);memcpy(p+8,mac,6);put32(p+16,7);put32(p+20,10);put32(p+24,id);put32(p+32,5000);put32(p+36,0x12345678);sign_frame(p);}
int main(void){
 const uint8_t mac[6]={0x90,0xda,0x72,0x48,0xa5,0x20};uint8_t b[48],out[48];fc_state s;
 assert(fc_crc32((const uint8_t*)"123456789",9)==0xcbf43926u);fc_init(&s,mac,7);fc_report_sent(&s,10,1000);command(b,mac,1);
 assert(fc_receive(&s,b,48,1001,3,out)==1);assert(!memcmp(out,"LRA2",4)&&get32(out+32)==2&&get32(out+36)==0x12345678&&get32(out+44)==fc_crc32(out,44));
 assert(fc_receive(&s,b,48,1002,3,out)==2&&out[14]==1&&s.executed==1&&s.duplicates==1);
 b[36]^=1;sign_frame(b);assert(fc_receive(&s,b,48,1003,3,out)==0&&s.executed==1);
 command(b,mac,2);assert(!fc_receive(&s,b,47,1004,3,out));b[44]^=1;assert(!fc_receive(&s,b,48,1004,3,out));
 command(b,mac,2);put32(b+16,8);sign_frame(b);assert(!fc_receive(&s,b,48,1004,3,out));
 command(b,mac,2);put32(b+20,11);sign_frame(b);assert(!fc_receive(&s,b,48,1004,3,out));
 command(b,mac,2);assert(!fc_receive(&s,b,48,6001,3,out));
 fc_init(&s,mac,7);fc_report_sent(&s,10,1000);for(unsigned i=1;i<=16;i++){command(b,mac,i);assert(fc_receive(&s,b,48,1001,3,out)==1);}command(b,mac,17);assert(!fc_receive(&s,b,48,1001,3,out)&&s.full==1);assert(!fc_receive(&s,b,48,6001,3,out));
 fc_report_sent(&s,11,6001);command(b,mac,17);put32(b+20,11);sign_frame(b);assert(fc_receive(&s,b,48,6001,3,out)==1);
 command(b,mac,18);b[5]=2;put32(b+20,11);put32(b+36,0);sign_frame(b);assert(fc_receive(&s,b,48,6002,3,out)==1&&get32(out+36)==3);
 command(b,mac,19);b[5]=3;put32(b+20,11);sign_frame(b);assert(!fc_receive(&s,b,48,6003,3,out));
 puts("PASS CRC, targeting, boot, freshness, duplicate/conflict, capacity, expiry, status and command whitelist");return 0;
}
