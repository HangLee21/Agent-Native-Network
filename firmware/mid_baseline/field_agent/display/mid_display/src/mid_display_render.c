#include "mid_display.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "mid_display_font.h"

static void row(char lines[8][MID_DISPLAY_COLS+1],unsigned index,const char *fmt,...) {
    char buffer[128];va_list args;va_start(args,fmt);vsnprintf(buffer,sizeof(buffer),fmt,args);va_end(args);
    size_t n=strlen(buffer);if(n>MID_DISPLAY_COLS)n=MID_DISPLAY_COLS;
    memset(lines[index],' ',MID_DISPLAY_COLS);memcpy(lines[index],buffer,n);
}
static void mac_text(const uint8_t mac[6],char out[18]) {
    unsigned any=0;for(unsigned i=0;i<6;i++)any|=mac[i];
    if(!any){strcpy(out,"--:--:--:--:--:--");return;}
    snprintf(out,18,"%02x:%02x:%02x:%02x:%02x:%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
}
static void count_text(uint32_t count,char out[7]) {
    if(count>99999)strcpy(out,">99999");else snprintf(out,7,"%lu",(unsigned long)count);
}
static void hex_text(uint32_t value,int known,char out[9]) {
    if(known)snprintf(out,9,"%08lx",(unsigned long)value);else strcpy(out,"--------");
}
static void peer_text(const uint8_t mac[6],char out[18]) {
    static const uint8_t ids[5][6]={{0x90,0xda,0x72,0x48,0xa4,0xf8},{0x90,0xda,0x72,0x48,0xa5,0xcc},{0x90,0xda,0x72,0x48,0xa4,0xe0},{0x90,0xda,0x72,0x48,0xa5,0x20},{0x90,0xda,0x72,0x48,0xa6,0x98}};
    for(unsigned i=0;i<5;i++)if(!memcmp(mac,ids[i],6)){snprintf(out,18,"%c",'A'+i);return;}
    unsigned any=0;for(unsigned i=0;i<6;i++)any|=mac[i];
    if(!any)strcpy(out,"--");else snprintf(out,18,"..%02x:%02x:%02x",mac[3],mac[4],mac[5]);
}
void mid_display_lines(const mid_display_snapshot *s,unsigned page,char lines[8][MID_DISPLAY_COLS+1]) {
    for(unsigned i=0;i<8;i++){memset(lines[i],' ',MID_DISPLAY_COLS);lines[i][MID_DISPLAY_COLS]=0;}
    if(mid_display_validate(s)){row(lines,0,"INVALID !");row(lines,2,"Snapshot rejected");return;}
    static const char *const titles[]={"DEVICE","TX","RX","CONFIG","COUNTS","HELP"};
    static const char *const modes[]={"IDLE","ARMED","ACTIVE","BENCH","WAITCFG"};
    page%=MID_DISPLAY_PAGE_COUNT;
    int marked=s->fault_count||s->counts.cfg_rejected||s->counts.commands_error||s->counts.invalid_events;
    row(lines,0,"%s %c%s",titles[page],s->identity.label,marked?" !":"");
    char a[18],b[18],n[9],f[9],c1[7],c2[7];
    if(page==0){
        row(lines,0,"DEVICE %c%s",s->identity.label,marked?" !":"");
        if(!s->business_ref.valid){
            row(lines,2,"%s CH:%u",modes[s->mode],s->identity.channel);row(lines,3,"Waiting for data");
            row(lines,4,"SRC -- -> DST --");row(lines,5,"SEQ --------");row(lines,6,"No business packet");
        }else{
            peer_text(s->business_ref.origin,a);peer_text(s->business_dst,b);row(lines,2,"%s -> %s",a,b);
            hex_text(s->business_ref.seq,s->business_ref.valid&MID_DISPLAY_REF_SEQ,n);row(lines,3,"SEQ %s",n);
            hex_text(s->business_ref.boot,s->business_ref.valid&MID_DISPLAY_REF_BOOT,f);row(lines,4,"BOOT %s",f);
            unsigned flags=s->business_flags;
            if(flags&8)row(lines,5,"%s%s",flags&1?"RX -> ":"",mid_display_tx_text(s->business_tx));
            else if(flags&32)row(lines,5,"DEST RX (local)");
            else if(flags&1)row(lines,5,"%s",flags&4?"RX -> TX LINK OK":flags&2?"RX -> TX SUBMITTED":flags&16?"RX -> TX QUEUED":"RELAY RX (not TX)");
            else row(lines,5,"TX %s",mid_display_tx_text(s->business_tx));
            peer_text(s->business_next,a);row(lines,6,"NEXT %s",a);
        }
        peer_text(s->field_rf_peer,a);if(s->field_rf_valid)row(lines,4,"RF %s %d %lus",a,(int)s->field_rssi,(unsigned long)((s->at_ms-s->field_rf_at)/1000));else row(lines,4,"RF -- RSSI unknown");
        row(lines,6,"T%lu F%lu R%lu",(unsigned long)(s->field_tx>9999?9999:s->field_tx),(unsigned long)(s->field_forward>9999?9999:s->field_forward),(unsigned long)(s->field_rx>9999?9999:s->field_rx));
        row(lines,7,"S%lu %s",(unsigned long)s->field_segment,s->field_running?"AGENT RUN":"AGENT PAUSED");
    }else if(page==1){
        mac_text(s->tx_dst,a);mac_text(s->tx_next,b);
        row(lines,2,"Dst:%s",a);row(lines,3,"Hop:%s",b);
        hex_text(s->tx_ref.seq,s->tx_ref.valid&MID_DISPLAY_REF_SEQ,n);hex_text(s->tx_ref.flow,s->tx_ref.valid&MID_DISPLAY_REF_FLOW,f);
        row(lines,4,"S:%s F:%s",n,f);row(lines,5,"TX:%s",mid_display_tx_text(s->tx_state));
        row(lines,6,"Dest:%s",mid_display_destination_text(s));
        if(s->fault_count)row(lines,7,"F:%s PRG:RX",mid_display_tx_text(s->last_fault));
        else row(lines,7,"TXerr:0 PRG:RX");
    }else if(page==2){
        mac_text(s->rx_ref.origin,a);mac_text(s->rx_dst,b);row(lines,2,"Src:%s",a);row(lines,3,"Dst:%s",b);
        hex_text(s->rx_ref.seq,s->rx_ref.valid&MID_DISPLAY_REF_SEQ,n);hex_text(s->rx_ref.flow,s->rx_ref.valid&MID_DISPLAY_REF_FLOW,f);
        row(lines,4,"S:%s F:%s",n,f);row(lines,5,"RX:%s",mid_display_rx_text(s->rx_state));
        count_text(s->counts.rx_dest,c1);count_text(s->counts.rx_relay,c2);row(lines,6,"D:%s R:%s",c1,c2);
        row(lines,7,"PRG:CONFIG");
    }else if(page==3){
        mac_text(s->cfg_origin,a);row(lines,2,"Src:%s",a);
        hex_text(s->cfg_seq,s->cfg_valid&MID_DISPLAY_CFG_SEQ,n);row(lines,3,"Update:%s",n);
        row(lines,4,"CFG:%s",mid_display_cfg_text(s->cfg_state));
        count_text(s->counts.cfg_received,c1);count_text(s->counts.cfg_applied,c2);row(lines,5,"R:%s A:%s",c1,c2);
        count_text(s->counts.cfg_stale,c1);count_text(s->counts.cfg_rejected,c2);row(lines,6,"Old:%s Bad:%s",c1,c2);
        row(lines,7,"PRG:COUNTS");
    }else if(page==4){
        count_text(s->counts.queued,c1);count_text(s->counts.submitted,c2);row(lines,2,"Q:%s S:%s",c1,c2);
        count_text(s->counts.link_ok,c1);count_text(s->counts.link_fail,c2);row(lines,3,"L+:%s L-:%s",c1,c2);
        count_text(s->counts.rx_dest,c1);count_text(s->counts.ann_confirmed,c2);row(lines,4,"D:%s Ack:%s",c1,c2);
        count_text(s->counts.timeouts,c1);count_text(s->counts.local_fail,c2);row(lines,5,"T:%s F:%s",c1,c2);
        count_text(s->peers,c1);count_text(s->routes,c2);row(lines,6,"N:%s Rt:%s",c1,c2);
        row(lines,7,"PRG:HELP");
    }else{
        for(unsigned i=0;i<MID_DISPLAY_HELP_LINES;i++)row(lines,i+2,"%s",s->help[i]);
        row(lines,7,"PRG:STATUS");
    }
}
static const uint8_t *columns(char ch) {
    for(unsigned i=0;i<sizeof(font)/sizeof(font[0]);i++)if(font[i].ch==ch)return font[i].col;
    return font[1].col;
}
static void text(uint8_t *frame,int x,int y,const char *str,int scale) {
    for(;*str&&x+5*scale<=128;str++,x+=6*scale){
        const uint8_t *g=columns(*str);
        for(int c=0;c<5;c++)for(int r=0;r<7;r++)if(g[c]&(1u<<r))
            for(int dx=0;dx<scale;dx++)for(int dy=0;dy<scale;dy++){
                int px=x+c*scale+dx,py=y+r*scale+dy;
                if(px>=0&&px<128&&py>=0&&py<64)frame[px+128*(py/8)]|=(uint8_t)(1u<<(py%8));
            }
    }
}
void mid_display_render(const mid_display_snapshot *s,unsigned page,uint8_t frame[MID_DISPLAY_FRAME_BYTES]) {
    char lines[8][MID_DISPLAY_COLS+1];memset(frame,0,MID_DISPLAY_FRAME_BYTES);
    mid_display_lines(s,page,lines);text(frame,0,0,lines[0],2);
    for(unsigned i=2;i<8;i++)text(frame,0,(int)i*8,lines[i],1);
}
