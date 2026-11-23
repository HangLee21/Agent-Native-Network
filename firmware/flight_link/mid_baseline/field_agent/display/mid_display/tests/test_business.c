#include "mid_display.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static const uint8_t A[6]={0x90,0xda,0x72,0x48,0xa4,0xf8},B[6]={0x90,0xda,0x72,0x48,0xa5,0xcc},C[6]={0x90,0xda,0x72,0x48,0xa4,0xe0};
static mid_display_event event(mid_display_event_kind kind,unsigned seq,unsigned t){
 mid_display_event e={.kind=kind,.at_ms=t,.ref={.valid=7,.boot=0x1234,.seq=seq}};
 memcpy(e.ref.origin,A,6);memcpy(e.dst,C,6);memcpy(e.next_hop,C,6);return e;
}
static void apply(mid_display_snapshot*s,mid_display_event_kind kind,unsigned seq,unsigned t){mid_display_event e=event(kind,seq,t);assert(!mid_display_model_apply(s,&e));}
static void show(mid_display_snapshot*s,const char*expected){char lines[8][MID_DISPLAY_COLS+1];mid_display_lines(s,0,lines);assert(strstr(lines[5],expected));for(int i=0;i<8;i++)puts(lines[i]);}
int main(void){
 mid_display_snapshot s;mid_display_identity id={.channel=6,.label='B',.protocol=MID_DISPLAY_MID};memcpy(id.mac,B,6);assert(!mid_display_model_init(&s,&id));
 apply(&s,MID_DISPLAY_EV_RX_RELAY,42,1);show(&s,"RELAY RX (not TX)");
 apply(&s,MID_DISPLAY_EV_TX_QUEUED,42,2);show(&s,"RX -> TX QUEUED");
 apply(&s,MID_DISPLAY_EV_TX_SUBMITTED,42,3);show(&s,"RX -> TX SUBMITTED");
 apply(&s,MID_DISPLAY_EV_TX_LINK_OK,42,4);show(&s,"RX -> TX LINK OK");
 assert(s.business_ref.seq==42&&s.business_ref.boot==0x1234);
 mid_display_event status={.kind=MID_DISPLAY_EV_STATUS,.at_ms=1000,.mode=MID_DISPLAY_IDLE};assert(!mid_display_model_apply(&s,&status));show(&s,"RX -> TX LINK OK");
 apply(&s,MID_DISPLAY_EV_RX_RELAY,43,1001);apply(&s,MID_DISPLAY_EV_TX_LINK_FAIL,42,1002);show(&s,"RELAY RX (not TX)");assert(s.business_ref.seq==43);
 apply(&s,MID_DISPLAY_EV_TX_QUEUED,43,1003);apply(&s,MID_DISPLAY_EV_TX_LOCAL_FAIL,43,1004);show(&s,"RX -> LOCAL FAIL");
 id.label='C';memcpy(id.mac,C,6);assert(!mid_display_model_init(&s,&id));apply(&s,MID_DISPLAY_EV_RX_DEST,42,1);show(&s,"DEST RX (local)");
 char lines[8][MID_DISPLAY_COLS+1];mid_display_lines(&s,0,lines);assert(strstr(lines[2],"A -> C")&&strstr(lines[3],"0000002a")&&strstr(lines[4],"00001234"));
 assert(s.business_flags==32);
 id.label='A';id.protocol=MID_DISPLAY_ANN;memcpy(id.mac,A,6);assert(!mid_display_model_init(&s,&id));apply(&s,MID_DISPLAY_EV_TX_QUEUED,7,1);apply(&s,MID_DISPLAY_EV_ANN_CONFIRMED,7,2);show(&s,"ANN ACKED");mid_display_lines(&s,0,lines);assert(strstr(lines[7],"ANN CONFIRMED"));
 puts("PASS business identity, relay receive versus transmit, delayed callback, local failure, destination and legacy ANN distinction");
}
