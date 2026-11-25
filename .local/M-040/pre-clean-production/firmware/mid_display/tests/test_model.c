#include "mid_display.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
static const uint8_t A[6]={0x90,0xda,0x72,0x48,0xa4,0xf8};
static const uint8_t B[6]={2,0,0,0,0,2},C[6]={2,0,0,0,0,3};
static mid_display_snapshot fresh(mid_display_protocol protocol){
    mid_display_snapshot s;mid_display_identity id={.channel=1,.label='A',.protocol=protocol};
    memcpy(id.mac,A,6);assert(!mid_display_model_init(&s,&id));return s;
}
static mid_display_event event(mid_display_event_kind kind,uint32_t seq){
    mid_display_event e={.kind=kind,.at_ms=10,.ref={.valid=15,.boot=7,.seq=seq,.flow=9}};
    memcpy(e.ref.origin,A,6);memcpy(e.dst,C,6);memcpy(e.next_hop,B,6);return e;
}
static void apply(mid_display_snapshot *s,mid_display_event_kind kind,uint32_t seq){mid_display_event e=event(kind,seq);assert(!mid_display_model_apply(s,&e));}
static void dump(const char *name,const mid_display_snapshot *s){
    for(unsigned page=0;page<MID_DISPLAY_PAGE_COUNT;page++){
        char lines[8][MID_DISPLAY_COLS+1];uint8_t frame[MID_DISPLAY_FRAME_BYTES];
        mid_display_lines(s,page,lines);mid_display_render(s,page,frame);
        char file[96];snprintf(file,sizeof(file),"%s-page%u.bin",name,page);FILE *f=fopen(file,"wb");assert(f);assert(fwrite(frame,1,sizeof(frame),f)==sizeof(frame));fclose(f);
        printf("%s page %u\n",name,page);for(unsigned i=0;i<8;i++)printf("|%s|\n",lines[i]);
    }
}
int main(void){
    mid_display_snapshot s=fresh(MID_DISPLAY_MID);
    apply(&s,MID_DISPLAY_EV_TX_QUEUED,1);apply(&s,MID_DISPLAY_EV_TX_SUBMITTED,1);apply(&s,MID_DISPLAY_EV_TX_LINK_OK,1);
    assert(!strcmp(mid_display_destination_text(&s),"UNCONFIRMED"));
    mid_display_event e=event(MID_DISPLAY_EV_ANN_CONFIRMED,1);
    assert(mid_display_model_apply(&s,&e)==-1&&s.counts.ann_confirmed==0&&s.tx_state==MID_DISPLAY_TX_LINK_OK);
    /* An inbound payload for this destination must not confirm a distinct outbound payload. */
    e=event(MID_DISPLAY_EV_RX_DEST,2);memcpy(e.ref.origin,B,6);memcpy(e.dst,A,6);
    assert(!mid_display_model_apply(&s,&e));assert(s.counts.rx_dest==1);
    assert(!strcmp(mid_display_destination_text(&s),"UNCONFIRMED"));
    dump("mid-link-ok-dest-unconfirmed",&s);
    apply(&s,MID_DISPLAY_EV_TX_TIMEOUT,1);
    e=(mid_display_event){.kind=MID_DISPLAY_EV_COMMAND,.at_ms=11,.command="info",.command_ok=1};assert(!mid_display_model_apply(&s,&e));
    e=(mid_display_event){.kind=MID_DISPLAY_EV_CFG_APPLIED,.at_ms=12,.cfg_seq=3,.cfg_valid=3};memcpy(e.cfg_origin,B,6);assert(!mid_display_model_apply(&s,&e));
    assert(s.tx_state==MID_DISPLAY_TX_TIMEOUT&&s.fault_count==1&&s.command_result==1);
    assert(!strcmp(mid_display_destination_text(&s),"UNCONFIRMED"));dump("mid-timeout-sticky",&s);
    /* Late MAC results belong to the old packet and must not change the new packet's state. */
    e=event(MID_DISPLAY_EV_TX_SUBMITTED,20);e.at_ms=13;assert(!mid_display_model_apply(&s,&e));
    e=event(MID_DISPLAY_EV_TX_LINK_FAIL,1);e.at_ms=14;assert(!mid_display_model_apply(&s,&e));
    assert(s.tx_ref.seq==20&&s.tx_state==MID_DISPLAY_TX_SUBMITTED&&s.fault_count==2);
    e=event(MID_DISPLAY_EV_TX_LINK_OK,20);e.at_ms=15;memcpy(e.dst,B,6);assert(mid_display_model_apply(&s,&e)==-1);
    assert(!memcmp(s.tx_dst,C,6));
    /* Relay RX is not local delivery, including when an upstream caller mislabels it. */
    e=event(MID_DISPLAY_EV_RX_RELAY,8);e.at_ms=16;memcpy(e.ref.origin,B,6);assert(!mid_display_model_apply(&s,&e));
    assert(s.counts.rx_dest==1&&s.rx_state==MID_DISPLAY_RX_RELAY);
    e.kind=MID_DISPLAY_EV_RX_DEST;assert(mid_display_model_apply(&s,&e)==-1);
    /* Original ANN confirmation remains supported, using its actual source/boot/sequence. */
    mid_display_snapshot ann=fresh(MID_DISPLAY_ANN);apply(&ann,MID_DISPLAY_EV_TX_SUBMITTED,4);apply(&ann,MID_DISPLAY_EV_ANN_CONFIRMED,4);
    assert(!strcmp(mid_display_destination_text(&ann),"ANN CONFIRMED"));
    apply(&ann,MID_DISPLAY_EV_TX_LINK_OK,4);assert(ann.tx_state==MID_DISPLAY_TX_ANN_CONFIRMED);
    dump("ann-existing-confirmation",&ann);
    mid_display_snapshot forged=fresh(MID_DISPLAY_MID);forged.tx_state=MID_DISPLAY_TX_ANN_CONFIRMED;
    assert(mid_display_validate(&forged)==-1);
    /* Invalid/unknown and complete counter ranges must not overrun the 1KiB framebuffer. */
    struct {uint8_t before[16],frame[MID_DISPLAY_FRAME_BYTES],after[16];} guard;
    memset(&guard,0xa5,sizeof(guard));
    for(unsigned label=0;label<6;label++)for(unsigned page=0;page<MID_DISPLAY_PAGE_COUNT;page++){
        s.identity.label="ABCDE?"[label];s.counts.link_ok=UINT_MAX;s.counts.rx_dest=UINT_MAX;s.counts.rx_relay=UINT_MAX;
        mid_display_render(&s,page,guard.frame);
        for(unsigned i=0;i<16;i++)assert(guard.before[i]==0xa5&&guard.after[i]==0xa5);
        char lines[8][MID_DISPLAY_COLS+1];mid_display_lines(&s,page,lines);
        for(unsigned i=0;i<8;i++)assert(strlen(lines[i])==MID_DISPLAY_COLS);
    }
    s.counts.link_ok=UINT_MAX;e=event(MID_DISPLAY_EV_TX_LINK_OK,20);e.at_ms=17;assert(!mid_display_model_apply(&s,&e)&&s.counts.link_ok==UINT_MAX);
    assert(mid_display_registered_label(A)=='A'&&mid_display_registered_label(B)=='?');
    const char *invalid[MID_DISPLAY_HELP_LINES]={"this command is much longer than the display", "", "", "", ""};
    mid_display_snapshot saved=s;assert(mid_display_set_help(&s,invalid)==-1&&!memcmp(&s,&saved,sizeof(s)));
    e=(mid_display_event){.kind=MID_DISPLAY_EV_STATUS,.at_ms=18,.mode=(mid_display_mode)-1};assert(mid_display_model_apply(&s,&e)==-1);
    e=(mid_display_event){.kind=MID_DISPLAY_EV_CFG_REJECTED,.at_ms=19};assert(!mid_display_model_apply(&s,&e));
    assert(s.cfg_valid==0&&s.counts.cfg_rejected==1);char rejected[8][MID_DISPLAY_COLS+1];mid_display_lines(&s,3,rejected);
    assert(strstr(rejected[3],"--------")&&strstr(rejected[4],"REJECTED"));
    puts("PASS: no false MID confirmation; late callbacks; relay/destination distinction; sticky errors; ANN ACK; counter saturation; 36 framebuffer guard/page/label cases.");
    return 0;
}
