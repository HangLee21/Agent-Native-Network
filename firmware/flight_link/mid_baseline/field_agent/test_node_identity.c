#include "node_identity.h"
#include "mid_display.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
int main(void){
 const uint8_t macs[5][6]={{0x90,0xda,0x72,0x48,0xa4,0xf8},{0x90,0xda,0x72,0x48,0xa5,0xcc},{0x90,0xda,0x72,0x48,0xa4,0xe0},{0x90,0xda,0x72,0x48,0xa5,0x20},{0x90,0xda,0x72,0x48,0xa6,0x98}};
 for(unsigned i=0;i<5;i++)assert(node_identity_default(macs[i])==i+1);
 const uint8_t unknown[6]={2,0,0,0,0xa5,0x20};assert(node_identity_default(unknown)==0);assert(node_identity_default(NULL)==0);
 mid_display_identity id={.channel=6,.label='?',.protocol=MID_DISPLAY_MID};memcpy(id.mac,unknown,6);mid_display_snapshot screen;assert(!mid_display_model_init(&screen,&id));char lines[8][MID_DISPLAY_COLS+1];uint8_t frame[MID_DISPLAY_FRAME_BYTES];
 mid_display_lines(&screen,0,lines);assert(!strncmp(lines[0],"UNSET A520",10));mid_display_render(&screen,0,frame);
 const uint32_t numbers[]={1,27,100,UINT32_MAX};const char*expected[]={"1","27","100","4294967295"};
 for(unsigned i=0;i<4;i++){screen.identity.node_id=numbers[i];assert(!mid_display_validate(&screen));mid_display_lines(&screen,0,lines);assert(!strncmp(lines[0],expected[i],strlen(expected[i])));mid_display_render(&screen,0,frame);}
 puts("PASS exact MAC defaults, unknown UNSET, numeric IDs 1/27/100/UINT32_MAX and OLED render");return 0;
}
