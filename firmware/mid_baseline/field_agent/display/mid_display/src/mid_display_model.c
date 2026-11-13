#include "mid_display.h"
#include <limits.h>
#include <string.h>

static int mac_known(const uint8_t m[6]) {
    unsigned any=0;for(unsigned i=0;i<6;i++)any|=m[i];return any!=0;
}
static void increment(uint32_t *value){if(*value<UINT32_MAX)(*value)++;}
static int ref_known(const mid_display_ref *r) {
    return (r->valid&(MID_DISPLAY_REF_ORIGIN|MID_DISPLAY_REF_SEQ))==
        (MID_DISPLAY_REF_ORIGIN|MID_DISPLAY_REF_SEQ) && !(r->valid&~15u) && mac_known(r->origin);
}
static int same_ref(const mid_display_ref *a,const mid_display_ref *b) {
    if(!ref_known(a)||!ref_known(b)||a->valid!=b->valid||memcmp(a->origin,b->origin,6)||a->seq!=b->seq)return 0;
    if((a->valid&MID_DISPLAY_REF_BOOT)&&a->boot!=b->boot)return 0;
    if((a->valid&MID_DISPLAY_REF_FLOW)&&a->flow!=b->flow)return 0;
    return 1;
}
char mid_display_registered_label(const uint8_t mac[6]) {
    static const uint8_t a[6]={0x90,0xda,0x72,0x48,0xa4,0xf8};
    return mac&&!memcmp(a,mac,6)?'A':'?';
}
int mid_display_model_init(mid_display_snapshot *s,const mid_display_identity *identity) {
    if(!s||!identity||!mac_known(identity->mac)||identity->channel<1||identity->channel>14||
       (identity->protocol!=MID_DISPLAY_MID&&identity->protocol!=MID_DISPLAY_ANN)||
       !((identity->label>='A'&&identity->label<='E')||identity->label=='?'))return -1;
    memset(s,0,sizeof(*s));s->identity=*identity;strcpy(s->command,"--");
    const char *ann[MID_DISPLAY_HELP_LINES]={"info   stats   stop","arm -> start / bench","nonce always required","CMD OK is not TX OK","PRG changes page only"};
    const char *mid[MID_DISPLAY_HELP_LINES]={"MID CLI: see E1 spec","No commands frozen","Dest remains unknown","CMD OK: command only","PRG changes page only"};
    return mid_display_set_help(s,identity->protocol==MID_DISPLAY_ANN?ann:mid);
}
int mid_display_set_help(mid_display_snapshot *s,const char *const lines[MID_DISPLAY_HELP_LINES]) {
    if(!s||!lines)return -1;
    for(unsigned i=0;i<MID_DISPLAY_HELP_LINES;i++){
        if(!lines[i]||strlen(lines[i])>MID_DISPLAY_COLS)return -1;
        for(const unsigned char *p=(const unsigned char*)lines[i];*p;p++)if(*p<32||*p>126)return -1;
    }
    for(unsigned i=0;i<MID_DISPLAY_HELP_LINES;i++)strcpy(s->help[i],lines[i]);
    return 0;
}
static void fault(mid_display_snapshot *s,const mid_display_event *e,mid_display_tx_state state) {
    increment(&s->fault_count);s->last_fault=state;s->fault_ref=e->ref;s->fault_code=e->code;
}
static int business_same(const mid_display_ref *a,const mid_display_ref *b) {
    return ref_known(a)&&ref_known(b)&&!memcmp(a->origin,b->origin,6)&&a->seq==b->seq&&
        ((a->valid&MID_DISPLAY_REF_BOOT)==(b->valid&MID_DISPLAY_REF_BOOT))&&
        (!(a->valid&MID_DISPLAY_REF_BOOT)||a->boot==b->boot);
}
static void business(mid_display_snapshot *s,const mid_display_event *e) {
    int rx=e->kind>=MID_DISPLAY_EV_RX_RELAY&&e->kind<=MID_DISPLAY_EV_RX_DUPLICATE;
    int tx=e->kind>=MID_DISPLAY_EV_TX_QUEUED&&e->kind<=MID_DISPLAY_EV_ANN_CONFIRMED;
    if(!rx&&!tx)return;
    int same=business_same(&s->business_ref,&e->ref);
    /* Old callbacks may count as faults but must not relabel a newer packet. */
    if(!rx&&e->kind!=MID_DISPLAY_EV_TX_QUEUED&&e->kind!=MID_DISPLAY_EV_TX_SUBMITTED&&!same)return;
    if(!same){s->business_flags=0;s->business_tx=MID_DISPLAY_TX_NONE;memset(s->business_next,0,6);}
    s->business_ref=e->ref;memcpy(s->business_dst,e->dst,6);s->business_at_ms=e->at_ms;
    if(e->kind==MID_DISPLAY_EV_RX_RELAY)s->business_flags|=1;
    if(e->kind==MID_DISPLAY_EV_RX_DEST||e->kind==MID_DISPLAY_EV_RX_DUPLICATE)s->business_flags|=32;
    if(tx){
        memcpy(s->business_next,e->next_hop,6);
        if(e->kind==MID_DISPLAY_EV_TX_QUEUED){s->business_flags|=16;s->business_tx=MID_DISPLAY_TX_QUEUED;}
        if(e->kind==MID_DISPLAY_EV_TX_SUBMITTED){s->business_flags|=2;s->business_tx=MID_DISPLAY_TX_SUBMITTED;}
        if(e->kind==MID_DISPLAY_EV_TX_LINK_OK){s->business_flags|=4;s->business_tx=MID_DISPLAY_TX_LINK_OK;}
        if(e->kind==MID_DISPLAY_EV_ANN_CONFIRMED){s->business_flags|=4;s->business_tx=MID_DISPLAY_TX_ANN_CONFIRMED;}
        if(e->kind==MID_DISPLAY_EV_TX_LINK_FAIL||e->kind==MID_DISPLAY_EV_TX_LOCAL_FAIL||e->kind==MID_DISPLAY_EV_TX_TIMEOUT){s->business_flags|=8;s->business_tx=e->kind==MID_DISPLAY_EV_TX_LINK_FAIL?MID_DISPLAY_TX_LINK_FAIL:e->kind==MID_DISPLAY_EV_TX_TIMEOUT?MID_DISPLAY_TX_TIMEOUT:MID_DISPLAY_TX_LOCAL_FAIL;}
    }
}
int mid_display_model_apply(mid_display_snapshot *s,const mid_display_event *e) {
    if(!s||!e)return -1;
    if(e->at_ms<s->at_ms)goto invalid;
    if(e->kind==MID_DISPLAY_EV_STATUS){
        if((unsigned)e->mode>MID_DISPLAY_WAIT_CONFIG)goto invalid;
        s->mode=e->mode;s->peers=e->peers;s->routes=e->routes;
    }else if(e->kind==MID_DISPLAY_EV_COMMAND){
        if(!memchr(e->command,0,sizeof(e->command))||e->command_ok>1)goto invalid;
        for(unsigned i=0;e->command[i];i++)if((unsigned char)e->command[i]<32||(unsigned char)e->command[i]>126)goto invalid;
        memcpy(s->command,e->command,sizeof(s->command));s->command_result=e->command_ok?1:-1;
        if(e->command_ok)increment(&s->counts.commands_ok);else increment(&s->counts.commands_error);
    }else if(e->kind>=MID_DISPLAY_EV_TX_QUEUED&&e->kind<=MID_DISPLAY_EV_ANN_CONFIRMED){
        if(!ref_known(&e->ref)||!mac_known(e->dst))goto invalid;
        if(e->kind==MID_DISPLAY_EV_ANN_CONFIRMED&&
           (s->identity.protocol!=MID_DISPLAY_ANN||!(e->ref.valid&MID_DISPLAY_REF_BOOT)||memcmp(e->ref.origin,s->identity.mac,6)))goto invalid;
        int matches=same_ref(&s->tx_ref,&e->ref);
        if(matches&&memcmp(s->tx_dst,e->dst,6))goto invalid;
        mid_display_tx_state state=MID_DISPLAY_TX_NONE;
        switch(e->kind){
        case MID_DISPLAY_EV_TX_QUEUED:increment(&s->counts.queued);state=MID_DISPLAY_TX_QUEUED;break;
        case MID_DISPLAY_EV_TX_SUBMITTED:increment(&s->counts.submitted);state=MID_DISPLAY_TX_SUBMITTED;break;
        case MID_DISPLAY_EV_TX_LINK_OK:increment(&s->counts.link_ok);state=MID_DISPLAY_TX_LINK_OK;break;
        case MID_DISPLAY_EV_TX_LINK_FAIL:increment(&s->counts.link_fail);state=MID_DISPLAY_TX_LINK_FAIL;fault(s,e,state);break;
        case MID_DISPLAY_EV_TX_LOCAL_FAIL:increment(&s->counts.local_fail);state=MID_DISPLAY_TX_LOCAL_FAIL;fault(s,e,state);break;
        case MID_DISPLAY_EV_TX_TIMEOUT:increment(&s->counts.timeouts);state=MID_DISPLAY_TX_TIMEOUT;fault(s,e,state);break;
        case MID_DISPLAY_EV_ANN_CONFIRMED:increment(&s->counts.ann_confirmed);state=MID_DISPLAY_TX_ANN_CONFIRMED;break;
        default:goto invalid;
        }
        if(e->kind==MID_DISPLAY_EV_TX_QUEUED||e->kind==MID_DISPLAY_EV_TX_SUBMITTED||matches){
            /* A delayed callback may update totals/faults but cannot relabel a newer message. */
            if(!(matches&&s->tx_state==MID_DISPLAY_TX_ANN_CONFIRMED&&e->kind!=MID_DISPLAY_EV_TX_QUEUED)){
                s->tx_state=state;s->tx_ref=e->ref;memcpy(s->tx_dst,e->dst,6);memcpy(s->tx_next,e->next_hop,6);
            }
        }
    }else if(e->kind>=MID_DISPLAY_EV_RX_RELAY&&e->kind<=MID_DISPLAY_EV_RX_DUPLICATE){
        if(!ref_known(&e->ref)||!mac_known(e->dst))goto invalid;
        int local=!memcmp(e->dst,s->identity.mac,6);
        if((e->kind==MID_DISPLAY_EV_RX_RELAY&&local)||(e->kind!=MID_DISPLAY_EV_RX_RELAY&&!local))goto invalid;
        if(e->kind==MID_DISPLAY_EV_RX_RELAY){s->rx_state=MID_DISPLAY_RX_RELAY;increment(&s->counts.rx_relay);}
        else if(e->kind==MID_DISPLAY_EV_RX_DEST){s->rx_state=MID_DISPLAY_RX_DEST;increment(&s->counts.rx_dest);}
        else{s->rx_state=MID_DISPLAY_RX_DUPLICATE;increment(&s->counts.rx_duplicate);}
        s->rx_ref=e->ref;memcpy(s->rx_dst,e->dst,6);
    }else if(e->kind>=MID_DISPLAY_EV_CFG_RECEIVED&&e->kind<=MID_DISPLAY_EV_CFG_REJECTED){
        if(e->cfg_valid&~3u)goto invalid;
        if((e->cfg_valid&MID_DISPLAY_CFG_ORIGIN)&&!mac_known(e->cfg_origin))goto invalid;
        if(e->kind!=MID_DISPLAY_EV_CFG_REJECTED&&e->cfg_valid!=3)goto invalid;
        s->cfg_state=(mid_display_cfg_state)(MID_DISPLAY_CFG_RECEIVED+e->kind-MID_DISPLAY_EV_CFG_RECEIVED);
        memset(s->cfg_origin,0,6);if(e->cfg_valid&MID_DISPLAY_CFG_ORIGIN)memcpy(s->cfg_origin,e->cfg_origin,6);
        s->cfg_valid=e->cfg_valid;s->cfg_seq=e->cfg_seq;
        switch(e->kind){
        case MID_DISPLAY_EV_CFG_RECEIVED:increment(&s->counts.cfg_received);break;
        case MID_DISPLAY_EV_CFG_APPLIED:increment(&s->counts.cfg_applied);break;
        case MID_DISPLAY_EV_CFG_STALE:increment(&s->counts.cfg_stale);break;
        case MID_DISPLAY_EV_CFG_REJECTED:increment(&s->counts.cfg_rejected);break;
        default:goto invalid;
        }
    }else goto invalid;
    business(s,e);s->at_ms=e->at_ms;return 0;
invalid:
    increment(&s->counts.invalid_events);return -1;
}
const char *mid_display_tx_text(mid_display_tx_state state) {
    static const char *const names[]={"NONE","QUEUED","SUBMITTED","LINK OK","LINK FAIL","LOCAL FAIL","TIMEOUT","ANN ACKED"};
    return (unsigned)state<sizeof(names)/sizeof(names[0])?names[state]:"UNKNOWN";
}
const char *mid_display_rx_text(mid_display_rx_state state) {
    static const char *const names[]={"NONE","RELAY ONLY","DEST RECEIVED","DUP DEST RX"};
    return (unsigned)state<sizeof(names)/sizeof(names[0])?names[state]:"UNKNOWN";
}
const char *mid_display_cfg_text(mid_display_cfg_state state) {
    static const char *const names[]={"NONE","RECEIVED","APPLIED","STALE","REJECTED"};
    return (unsigned)state<sizeof(names)/sizeof(names[0])?names[state]:"UNKNOWN";
}
const char *mid_display_destination_text(const mid_display_snapshot *s) {
    if(s->tx_state==MID_DISPLAY_TX_NONE)return "NO TX";
    return s->identity.protocol==MID_DISPLAY_ANN&&s->tx_state==MID_DISPLAY_TX_ANN_CONFIRMED?"ANN CONFIRMED":"UNCONFIRMED";
}
int mid_display_validate(const mid_display_snapshot *s) {
    if(s&&s->business_ref.valid&&(!ref_known(&s->business_ref)||!mac_known(s->business_dst)||
        (s->business_flags&~63u)||(unsigned)s->business_tx>MID_DISPLAY_TX_ANN_CONFIRMED))return -1;
    if(!s||!mac_known(s->identity.mac)||s->identity.channel<1||s->identity.channel>14||
       (s->identity.protocol!=MID_DISPLAY_MID&&s->identity.protocol!=MID_DISPLAY_ANN)||
       !((s->identity.label>='A'&&s->identity.label<='E')||s->identity.label=='?')||
       (unsigned)s->mode>MID_DISPLAY_WAIT_CONFIG||(unsigned)s->tx_state>MID_DISPLAY_TX_ANN_CONFIRMED||
       (unsigned)s->rx_state>MID_DISPLAY_RX_DUPLICATE||(unsigned)s->cfg_state>MID_DISPLAY_CFG_REJECTED||
       !memchr(s->command,0,sizeof(s->command))||s->command_result< -1||s->command_result>1)return -1;
    if(s->identity.protocol==MID_DISPLAY_MID&&(s->tx_state==MID_DISPLAY_TX_ANN_CONFIRMED||s->counts.ann_confirmed))return -1;
    if(s->tx_state!=MID_DISPLAY_TX_NONE&&(!ref_known(&s->tx_ref)||!mac_known(s->tx_dst)))return -1;
    if(s->tx_state==MID_DISPLAY_TX_ANN_CONFIRMED&&(!(s->tx_ref.valid&MID_DISPLAY_REF_BOOT)||memcmp(s->tx_ref.origin,s->identity.mac,6)))return -1;
    if(s->rx_state!=MID_DISPLAY_RX_NONE){
        if(!ref_known(&s->rx_ref)||!mac_known(s->rx_dst))return -1;
        int local=!memcmp(s->rx_dst,s->identity.mac,6);
        if((s->rx_state==MID_DISPLAY_RX_RELAY&&local)||(s->rx_state!=MID_DISPLAY_RX_RELAY&&!local))return -1;
    }
    if(s->cfg_valid&~3u)return -1;
    if((s->cfg_valid&MID_DISPLAY_CFG_ORIGIN)&&!mac_known(s->cfg_origin))return -1;
    if(s->cfg_state!=MID_DISPLAY_CFG_NONE&&s->cfg_state!=MID_DISPLAY_CFG_REJECTED&&s->cfg_valid!=3)return -1;
    for(unsigned i=0;i<MID_DISPLAY_HELP_LINES;i++)if(!memchr(s->help[i],0,sizeof(s->help[i])))return -1;
    return 0;
}
