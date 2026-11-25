#include "deployment.h"
#include "mid_display.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static mid_deployment path(void) {
    mid_deployment p = {.profile_id="abc-two-way", .autostart=1};
    p.table.n=3; p.table.k=2;
    for(unsigned i=0;i<3;i++) {p.table.nodes[i].mac[0]=2;p.table.nodes[i].mac[5]=(uint8_t)(i+1);}
    p.table.src[0]=0;p.table.dst[0]=2;p.table.src[1]=2;p.table.dst[1]=0;
    p.table.w[0][0][1]=p.table.w[0][1][2]=65535;
    p.table.w[1][2][1]=p.table.w[1][1][0]=65535;
    return p;
}
int main(int argc, char **argv) {
    if(argc==2) {
        uint8_t raw[MID_DEPLOYMENT_BYTES];FILE *f=fopen(argv[1],"rb");assert(f);
        size_t size=fread(raw,1,sizeof(raw),f);assert(!ferror(f));assert(feof(f));fclose(f);
        mid_deployment input={.profile_id="generated-profile",.autostart=1};
        assert(!mid_table_decode(&input.table,raw,size));
        for(unsigned i=0;i<input.table.n;i++) {
            mid_node one;assert(!mid_deployment_install(&one,&input,input.table.nodes[i],0));
        }
    }
    mid_deployment p=path(),restored;
    uint8_t saved[MID_DEPLOYMENT_BYTES],wire[MID_FRAME];
    int n=mid_deployment_encode(&p,p.table.nodes[0],saved,sizeof(saved));assert(n>0);
    for (unsigned size=0;size<(unsigned)n;size++) assert(mid_deployment_decode(&restored,p.table.nodes[0],saved,size)<0);
    for(unsigned direction=0;direction<2;direction++) for(unsigned restart=0;restart<2;restart++) {
        mid_node nodes[3];
        for(unsigned i=0;i<3;i++) {
            assert(!mid_deployment_decode(&restored,p.table.nodes[i],saved,(size_t)n));
            assert(!mid_deployment_install(&nodes[i],&restored,p.table.nodes[i],500));
            assert(!nodes[i].publisher_boot && nodes[i].have_table && !nodes[i].have_seq);
        }
        unsigned src=direction?2:0,dst=direction?0:2;
        mid_packet packet={.kind=2,.ttl=8,.origin=p.table.nodes[src],.boot=4321,.seq=1,.size=166},decoded;
        memcpy(packet.body,p.table.nodes[dst].mac,6);
        for(unsigned i=0;i<160;i++)packet.body[6+i]=(uint8_t)i;
        mid_id next;
        assert(mid_data(&nodes[src],&packet,&next)==1 && mid_equal(next,p.table.nodes[1]));
        if(restart) {
            memset(&nodes[1],0xa5,sizeof(nodes[1]));
            assert(!mid_deployment_decode(&restored,p.table.nodes[1],saved,(size_t)n));
            assert(!mid_deployment_install(&nodes[1],&restored,p.table.nodes[1],0));
        }
        n=mid_deployment_encode(&p,p.table.nodes[0],saved,sizeof(saved));
        int bytes=mid_encode(&packet,wire,sizeof(wire));assert(bytes>0);
        assert(!mid_decode(&decoded,wire,(size_t)bytes));
        assert(mid_data(&nodes[1],&decoded,&next)==1 && mid_equal(next,p.table.nodes[dst]));
        decoded.ttl--;bytes=mid_encode(&decoded,wire,sizeof(wire));assert(bytes>0);
        assert(!mid_decode(&decoded,wire,(size_t)bytes));
        assert(mid_data(&nodes[dst],&decoded,&next)==2);
        assert(decoded.boot==4321 && decoded.seq==1 && mid_equal(decoded.origin,p.table.nodes[src]));
        assert(!memcmp(packet.body,decoded.body,166));
        assert(mid_data(&nodes[dst],&decoded,&next)==0);
        packet.boot++;assert(mid_data(&nodes[dst],&packet,&next)==2);
    }
    mid_deployment bad=p;
    bad.table.w[0][1][2]=0;bad.table.w[0][1][0]=65535;
    assert(mid_deployment_validate(&bad,p.table.nodes[0])<0); /* loop */
    bad=p;bad.table.w[0][1][2]=0;assert(mid_deployment_validate(&bad,p.table.nodes[0])<0); /* dead end */
    bad=p;bad.table.w[0][0][1]=32767;bad.table.w[0][0][2]=32768;
    assert(mid_deployment_validate(&bad,p.table.nodes[0])<0); /* stochastic original MID remains a different mode */
    mid_id stranger={{2,0,0,0,0,9}};assert(mid_deployment_validate(&p,stranger)<0);
    bad=p;bad.autostart=2;assert(mid_deployment_validate(&bad,p.table.nodes[0])<0);
    for(unsigned pos=4;pos<10;pos++) {uint8_t broken[MID_DEPLOYMENT_BYTES];memcpy(broken,saved,(size_t)n);broken[pos]=255;assert(mid_deployment_decode(&restored,p.table.nodes[0],broken,(size_t)n)<0);}
    /* Legacy live configuration still requires the real publisher boot. */
    mid_node legacy;mid_init(&legacy,p.table.nodes[1],p.table.nodes[0],123);
    mid_packet cfg={.kind=1,.ttl=8,.origin=p.table.nodes[0],.boot=124,.seq=7};
    cfg.size=(uint16_t)mid_table_encode(&p.table,cfg.body,sizeof(cfg.body));
    assert(mid_config(&legacy,&cfg)<0);cfg.boot=123;assert(mid_config(&legacy,&cfg)==1);
    /* Headless links the same API-2 model and updates counts without a backend. */
    mid_display_identity identity={.mac={2,0,0,0,0,1},.channel=6,.label='A',.protocol=MID_DISPLAY_MID};
    mid_display_snapshot screen;assert(!mid_display_model_init(&screen,&identity));
    assert(!mid_display_start(&screen));assert(mid_display_hardware_state()==MID_DISPLAY_HW_OFF);
    mid_display_event e={.kind=MID_DISPLAY_EV_RX_DEST,.at_ms=1,.ref={.origin={2,0,0,0,0,3},.valid=7,.boot=10,.seq=11},.dst={2,0,0,0,0,1}};
    assert(!mid_display_model_apply(&screen,&e));assert(screen.counts.rx_dest==1 && screen.business_ref.seq==11);
    assert(!mid_display_publish(&screen));
    puts("PASS: serialized profile, independent cold-start, relay reset, bidirectional 160-byte payload/identity, duplicate/new-boot, invalid tables/blob, legacy binding, headless API2 counts");
    return 0;
}
