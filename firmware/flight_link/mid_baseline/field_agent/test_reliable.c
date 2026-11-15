#include "reliable.h"
#include "lora_ref/flight_control.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct {uint8_t wire[160],dst[6];size_t len;unsigned sends,timeouts,reject_left,last_submissions,last_rejections;} capture;
static int send_cb(void*ctx,const uint8_t dst[6],const uint8_t*b,size_t n){capture*c=ctx;if(c->reject_left){c->reject_left--;return -1;}memcpy(c->wire,b,n);memcpy(c->dst,dst,6);c->len=n;c->sends++;return 0;}
static void timeout_cb(void*ctx,const fr_message*m){capture*c=ctx;assert(m->id);c->timeouts++;c->last_submissions=m->submissions;c->last_rejections=m->local_rejections;}
static void put32(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
int main(void){
 const uint8_t a[6]={2,0,0,0,0,1},b[6]={2,0,0,0,0,2};fr_state src,dst;fr_init(&src,a,11);fr_init(&dst,b,22);capture c={0};uint32_t id=0;const uint8_t payload[]={1,2,3};
 assert(!fr_start(&src,b,22,payload,sizeof(payload),0,&id)&&id==1);fr_tick(&src,0,send_cb,timeout_cb,&c);assert(c.sends==1&&c.len==39);
 uint8_t ack[160],again[160];size_t n=0,n2=0;fr_message m;
 assert(fr_receive(&dst,a,11,c.wire,c.len,10,&m,ack,&n)==1&&n==36&&m.len==3&&!memcmp(m.payload,payload,3));
 assert(fr_receive(&dst,a,11,c.wire,c.len,11,&m,again,&n2)==2&&n2==n&&!memcmp(ack,again,n));
 assert(fr_receive(&src,b,22,ack,n,12,&m,again,&n2)==3&&src.delivered==1);fr_tick(&src,3000,send_cb,timeout_cb,&c);assert(c.sends==1&&!c.timeouts);
 assert(fr_receive(&src,b,22,ack,n,13,&m,again,&n2)==4); /* duplicate ACK */
 assert(!fr_start(&src,b,22,payload,sizeof(payload),4000,&id));fr_tick(&src,4000,send_cb,timeout_cb,&c);assert(fr_receive(&dst,a,12,c.wire,c.len,4001,&m,ack,&n)<0); /* stale origin boot */
 fr_state reboot;fr_init(&reboot,b,23);assert(fr_receive(&reboot,a,11,c.wire,c.len,4001,&m,ack,&n)<0); /* destination reboot */
 c.wire[32]^=1;assert(fr_receive(&dst,a,11,c.wire,c.len,4001,&m,ack,&n)<0);c.wire[32]^=1;put32(c.wire+c.len-4,fc_crc32(c.wire,c.len-4));
 fr_tick(&src,4350,send_cb,timeout_cb,&c);fr_tick(&src,4700,send_cb,timeout_cb,&c);fr_tick(&src,5050,send_cb,timeout_cb,&c);assert(c.sends==4&&c.timeouts==1&&src.timeouts==1&&c.last_submissions==3);
 fr_state blocked;fr_init(&blocked,a,11);capture z={.reject_left=2};assert(!fr_start(&blocked,b,22,payload,sizeof(payload),0,&id));fr_tick(&blocked,0,send_cb,timeout_cb,&z);fr_tick(&blocked,100,send_cb,timeout_cb,&z);assert(z.sends==0&&blocked.pending[0].attempts==0&&blocked.local_submit_failures==2);fr_tick(&blocked,200,send_cb,timeout_cb,&z);assert(z.sends==1&&blocked.pending[0].attempts==1);fr_tick(&blocked,1050,send_cb,timeout_cb,&z);assert(z.timeouts==1&&z.last_submissions==1&&z.last_rejections==2);
 for(unsigned i=0;i<FR_PENDING;i++){assert(!fr_start(&src,b,22,payload,sizeof(payload),11000,&id));}
 assert(fr_start(&src,b,22,payload,sizeof(payload),11000,&id)<0);
 puts("PASS bounded retries, destination ACK, duplicate suppression, boot binding, CRC and capacity");return 0;
}
