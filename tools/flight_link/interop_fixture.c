#include "flight_control.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
int main(int argc,char **argv){
 unsigned char frame[48],out[48],mac[6]={0x90,0xda,0x72,0x48,0xa5,0x20};unsigned v;
 for(unsigned i=0;i<48;i++){if(scanf("%2x",&v)!=1)return 2;frame[i]=(unsigned char)v;}
 uint64_t now=argc>1?strtoull(argv[1],0,10):1001;fc_state state;fc_init(&state,mac,7);fc_report_sent(&state,10,1000);
 for(unsigned trial=0;trial<2;trial++){
  int r=fc_receive(&state,frame,48,now+trial,3,out);printf("%d ",r);
  if(r)for(unsigned i=0;i<48;i++)printf("%02x",out[i]);
  printf("\n");
 }
 printf("%u %u\n",state.executed,state.duplicates);return 0;
}
