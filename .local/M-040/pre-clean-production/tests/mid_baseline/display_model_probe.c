#include "mid_display.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static mid_display_snapshot s;
static const uint8_t a[6]={0x90,0xda,0x72,0x48,0xa4,0xf8};
static const uint8_t b[6]={0x90,0xda,0x72,0x48,0xa5,0xcc};
static void init(int ann){mid_display_identity id={.channel=1,.label='A',.protocol=ann?MID_DISPLAY_ANN:MID_DISPLAY_MID};memcpy(id.mac,a,6);assert(!mid_display_model_init(&s,&id));}
static mid_display_event event(mid_display_event_kind kind,unsigned seq){
    mid_display_event e={.kind=kind,.at_ms=s.at_ms+1};e.ref.valid=15;e.ref.boot=0;e.ref.seq=seq;e.ref.flow=0;
    memcpy(e.ref.origin,a,6);memcpy(e.dst,b,6);return e;
}
static void apply(mid_display_event e){assert(!mid_display_model_apply(&s,&e));assert(!mid_display_validate(&s));}
static void lines(unsigned page){char rows[8][22];mid_display_lines(&s,page,rows);for(unsigned i=0;i<8;i++)puts(rows[i]);}
static void semantics(void){
    init(0);assert(!strcmp(mid_display_destination_text(&s),"NO TX"));
    mid_display_event e=event(MID_DISPLAY_EV_COMMAND,0);strcpy(e.command,"bench");e.command_ok=1;apply(e);
    assert(s.command_result==1&&s.tx_state==MID_DISPLAY_TX_NONE);lines(0);
    apply(event(MID_DISPLAY_EV_TX_QUEUED,0));apply(event(MID_DISPLAY_EV_TX_SUBMITTED,0));apply(event(MID_DISPLAY_EV_TX_LINK_OK,0));
    assert(s.tx_state==MID_DISPLAY_TX_LINK_OK&&!strcmp(mid_display_destination_text(&s),"UNCONFIRMED"));
    e=event(MID_DISPLAY_EV_ANN_CONFIRMED,0);assert(mid_display_model_apply(&s,&e)==-1);assert(!s.counts.ann_confirmed);lines(1);
    e=event(MID_DISPLAY_EV_RX_DEST,0);assert(mid_display_model_apply(&s,&e)==-1);
    e=event(MID_DISPLAY_EV_RX_RELAY,0);apply(e);assert(s.rx_state==MID_DISPLAY_RX_RELAY);
    e=event(MID_DISPLAY_EV_RX_DEST,1);memcpy(e.dst,a,6);apply(e);assert(s.counts.rx_dest==1);lines(2);
    e.kind=MID_DISPLAY_EV_RX_DUPLICATE;e.at_ms++;apply(e);assert(s.counts.rx_dest==1&&s.counts.rx_duplicate==1);
}
static void late(void){
    init(0);apply(event(MID_DISPLAY_EV_TX_SUBMITTED,1));apply(event(MID_DISPLAY_EV_TX_SUBMITTED,2));
    apply(event(MID_DISPLAY_EV_TX_LINK_OK,1));assert(s.tx_ref.seq==2&&s.tx_state==MID_DISPLAY_TX_SUBMITTED);
    apply(event(MID_DISPLAY_EV_TX_LINK_FAIL,1));assert(s.tx_ref.seq==2&&s.fault_ref.seq==1&&s.fault_count==1);
    mid_display_event e=event(MID_DISPLAY_EV_TX_LINK_OK,2);e.dst[5]++;assert(mid_display_model_apply(&s,&e)==-1);
    e=event(MID_DISPLAY_EV_TX_LINK_OK,2);e.at_ms=0;assert(mid_display_model_apply(&s,&e)==-1);lines(1);
    init(1);apply(event(MID_DISPLAY_EV_TX_SUBMITTED,0));apply(event(MID_DISPLAY_EV_ANN_CONFIRMED,0));
    apply(event(MID_DISPLAY_EV_TX_LINK_FAIL,0));assert(s.tx_state==MID_DISPLAY_TX_ANN_CONFIRMED&&s.fault_count==1);
    e=event(MID_DISPLAY_EV_ANN_CONFIRMED,0);e.ref.origin[5]++;assert(mid_display_model_apply(&s,&e)==-1);
    e=event(MID_DISPLAY_EV_ANN_CONFIRMED,0);e.ref.valid&=~MID_DISPLAY_REF_BOOT;assert(mid_display_model_apply(&s,&e)==-1);lines(1);
}
static void unknown(void){
    init(0);assert(mid_display_registered_label(b)=='?');apply(event(MID_DISPLAY_EV_TX_LINK_OK,8));
    assert(s.tx_state==MID_DISPLAY_TX_NONE&&!strcmp(mid_display_destination_text(&s),"NO TX"));
    apply(event(MID_DISPLAY_EV_TX_QUEUED,0));char rows[8][22];mid_display_lines(&s,1,rows);assert(strstr(rows[3],"--:--"));
    mid_display_event e=event(MID_DISPLAY_EV_CFG_RECEIVED,0);e.cfg_valid=3;memcpy(e.cfg_origin,a,6);apply(e);assert(s.counts.cfg_applied==0);
    e.kind=MID_DISPLAY_EV_CFG_REJECTED;e.at_ms++;e.cfg_valid=0;apply(e);mid_display_lines(&s,3,rows);assert(strstr(rows[3],"--------"));
    e=event(MID_DISPLAY_EV_COMMAND,0);strcpy(e.command,"info");e.command_ok=1;apply(e);mid_display_lines(&s,0,rows);assert(strchr(rows[0],'!'));lines(0);lines(3);
    s.tx_state=MID_DISPLAY_TX_ANN_CONFIRMED;mid_display_lines(&s,0,rows);assert(strstr(rows[0],"INVALID"));
}
static void rendering(void){
    init(0);s.counts.link_fail=UINT32_MAX;s.fault_count=UINT32_MAX;apply(event(MID_DISPLAY_EV_TX_LINK_FAIL,3));
    assert(s.counts.link_fail==UINT32_MAX&&s.fault_count==UINT32_MAX);
    mid_display_snapshot before=s;struct {uint8_t left[16],frame[1024],right[16];} guarded;
    memset(&guarded,0xa5,sizeof(guarded));
    for(unsigned p=0;p<12;p++){mid_display_render(&s,p,guarded.frame);assert(!memcmp(&s,&before,sizeof(s)));for(unsigned k=0;k<16;k++)assert(guarded.left[k]==0xa5&&guarded.right[k]==0xa5);}
    const char *bad[5]={"1234567890123456789012","a","a","a","a"};assert(mid_display_set_help(&s,bad)==-1);assert(!memcmp(s.help,before.help,sizeof(s.help)));
    lines(4);
}
int main(int argc,char **argv){assert(argc==2);int n=atoi(argv[1]);switch(n){case 0:semantics();break;case 1:late();break;case 2:unknown();break;case 3:rendering();break;default:abort();}printf("PASS independent display model scenario %d\n",n);return 0;}
