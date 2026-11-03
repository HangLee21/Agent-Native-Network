/* E2 black-box transport driver. Links are test fixtures, never RF/latency data. */
#include "ann.h"
#include "ann_console.h"
#include "ann_log.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static ann_node n[5];
static ann_console c[5];
static int edges[5][5],errors,checks,drop_ack,logging;
static uint64_t clock_ms;
static unsigned data_hops;
static uint32_t ordinals[5];
static unsigned char saved_data[250],saved_ack[250];
static int saved_data_len,saved_ack_len;
static ann_id saved_data_from,saved_ack_from;
#define VERIFY(x) do{checks++;if(!(x)){errors++;fprintf(stderr,"E2 assertion %s:%d: %s\n",__FILE__,__LINE__,#x);}}while(0)

static void drain(void){unsigned i;ann_event e;char out[1200];for(i=0;i<5;i++){
 while(ann_next_event(n+i,&e)){if(logging){ann_log_event(c+i,&e,out,sizeof(out));puts(out);}}
 VERIFY(n[i].out_count<=ANN_QUEUE&&n[i].event_count<=ANN_QUEUE);
}}
static void connect(unsigned a,unsigned b){edges[a][b]=edges[b][a]=1;}
static void init(const char *name,int diamond){unsigned i;memset(edges,0,sizeof(edges));memset(ordinals,0,sizeof(ordinals));clock_ms=0;drop_ack=0;data_hops=0;saved_data_len=saved_ack_len=0;
 for(i=0;i<5;i++){ann_init(n+i,i+1,100+i);ann_console_init(c+i,n+i,"host-synthetic","E2-independent");strcpy(c[i].run_id,name);ann_start(n+i,0);}
 if(diamond){connect(0,1);connect(1,3);connect(0,2);connect(2,3);}else for(i=0;i<4;i++)connect(i,i+1);
}
static void pump(void){unsigned rounds,i,j;ann_out tx;uint8_t wire[250];char out[1200];
 for(rounds=0;rounds<300;rounds++){int work=0;
  for(i=0;i<5;i++)while(ann_next_tx(n+i,&tx,clock_ms)){
   int size=ann_encode(&tx.packet,wire,sizeof(wire));int ok=!tx.next||(tx.next<=5&&edges[i][tx.next-1]);
   VERIFY(size>=112&&size<=250);if(size<112)continue;work=1;
   if(logging){ann_log_tx(c+i,&tx,"tx_submit",0,clock_ms,++ordinals[i],out,sizeof(out));puts(out);}
   if(tx.packet.type==ANN_ACK&&tx.next==1){memcpy(saved_ack,wire,size);saved_ack_len=size;saved_ack_from=i+1;}
   for(j=0;j<5;j++)if(edges[i][j]&&(!tx.next||tx.next==j+1)){
    uint32_t before=n[j].delivered;
    if(tx.packet.type==ANN_ACK&&drop_ack){drop_ack--;continue;}
    if(tx.packet.type==ANN_DATA){data_hops++;if(tx.packet.dst==j+1&&!saved_data_len){memcpy(saved_data,wire,size);saved_data_len=size;saved_data_from=i+1;}}
    (void)ann_receive(n+j,i+1,wire,(size_t)size,clock_ms);
    if(logging&&n[j].delivered>before&&tx.packet.kind==ANN_ECHO){ann_log_echo(c+j,&tx.packet,clock_ms,out,sizeof(out));puts(out);}
   }
   ann_tx_result(n+i,&tx,ok,clock_ms);
   if(logging){ann_log_tx(c+i,&tx,"tx_result",ok,clock_ms,ordinals[i],out,sizeof(out));puts(out);}
  }
  drain();if(!work)return;
 }
 VERIFY(0);
}
static void advance(unsigned duration){uint64_t end=clock_ms+duration;while(clock_ms<end){unsigned i;clock_ms++;for(i=0;i<5;i++)ann_tick(n+i,clock_ms);pump();}}
static uint32_t send_to(ann_id dst,unsigned life,unsigned kind,uint32_t key,const char *body){uint32_t seq=0;int result=ann_submit(n,dst,(uint8_t)kind,key,body,strlen(body),life,0,clock_ms,&seq);VERIFY(result==0);return seq;}
static unsigned pending_count(ann_node *node){unsigned i,count=0;for(i=0;i<ANN_PENDING;i++)count+=node->pending[i].used!=0;return count;}

static void run_case(const char *name){unsigned i;
 if(!strcmp(name,"normal")){init(name,0);send_to(5,5000,ANN_TRANSACTION,0,"independent");advance(50);VERIFY(n[4].delivered==1&&n[0].confirmed==1);VERIFY(data_hops>=4);VERIFY(pending_count(n)==0);}
 else if(!strcmp(name,"partition")){init(name,0);edges[2][3]=edges[3][2]=0;send_to(5,1000,ANN_TRANSACTION,0,"isolated");advance(2000);VERIFY(!n[4].delivered&&!n[0].confirmed);VERIFY(pending_count(n)==0);}
 else if(!strcmp(name,"alternate")){ann_route *route=NULL;init(name,1);send_to(4,5000,ANN_TRANSACTION,0,"before");advance(20);VERIFY(n[3].delivered==1&&n[0].confirmed==1);for(i=0;i<ANN_TABLE;i++)if(n[0].routes[i].used&&n[0].routes[i].dst==4)route=n[0].routes+i;VERIFY(route!=NULL);if(route){unsigned next=(unsigned)route->path[1]-1;edges[0][next]=edges[next][0]=0;send_to(4,5000,ANN_TRANSACTION,0,"after");advance(2500);VERIFY(n[3].delivered==2&&n[0].confirmed==2);}}
 else if(!strcmp(name,"duplicates")){uint32_t d;init(name,0);drop_ack=1;send_to(5,5000,ANN_TRANSACTION,0,"ACK lost");advance(1600);VERIFY(n[4].delivered==1&&n[0].confirmed==1&&n[4].duplicates>=1);VERIFY(saved_data_len>0&&saved_ack_len>0);d=n[4].delivered;(void)ann_receive(n+4,saved_data_from,saved_data,saved_data_len,clock_ms);pump();(void)ann_receive(n,saved_ack_from,saved_ack,saved_ack_len,clock_ms);drain();VERIFY(n[4].delivered==d&&n[0].confirmed==1);}
 else if(!strcmp(name,"cancel")){uint32_t seq;init(name,0);seq=send_to(5,5000,ANN_TRANSACTION,0,"cancel before send");VERIFY(!ann_cancel(n,seq,clock_ms));advance(1000);VERIFY(!n[4].delivered&&!n[0].confirmed&&pending_count(n)==0);}
 else if(!strcmp(name,"expiry")){init(name,0);send_to(5,1,ANN_TRANSACTION,0,"too late");clock_ms=2;for(i=0;i<5;i++)ann_tick(n+i,clock_ms);pump();advance(1000);VERIFY(!n[4].delivered&&!n[0].confirmed&&pending_count(n)==0);}
 else if(!strcmp(name,"reboot")){init(name,0);send_to(5,5000,ANN_TRANSACTION,0,"old boot");advance(20);ann_init(n,1,999);ann_start(n,clock_ms);send_to(5,5000,ANN_TRANSACTION,0,"new boot seq one");advance(50);VERIFY(n[4].delivered==2&&n[0].confirmed==1);ann_init(n+2,3,888);ann_start(n+2,clock_ms);send_to(5,5000,ANN_TRANSACTION,0,"relay reboot");advance(50);VERIFY(n[4].delivered==3&&n[0].confirmed==2);}
 else if(!strcmp(name,"bounds")){uint32_t seq;init(name,0);for(i=0;i<ANN_PENDING;i++){VERIFY(!ann_submit(n,5,ANN_TRANSACTION,0,"x",1,60000,0,0,&seq));drain();}VERIFY(ann_submit(n,5,ANN_TRANSACTION,0,"x",1,60000,0,0,&seq)==-2);VERIFY(pending_count(n)==ANN_PENDING&&n[0].out_count<=ANN_QUEUE);ann_stop(n,0);VERIFY(!n[0].out_count&&pending_count(n)==0);VERIFY(ann_submit(n,5,ANN_TRANSACTION,0,"x",1,1,0,0,&seq)==-1);}
 else if(!strcmp(name,"continuous100")){unsigned replayed=0;init(name,0);for(i=0;i<100;i++){VERIFY(pending_count(n)==0);send_to(5,60000,ANN_TRANSACTION,0,"100 sequential");advance(100);VERIFY(n[4].delivered==i+1&&n[0].confirmed==i+1);if(i==16||i==99){VERIFY(saved_data_len>0);(void)ann_receive(n+4,saved_data_from,saved_data,saved_data_len,clock_ms);pump();VERIFY(n[4].delivered==i+1&&n[0].confirmed==i+1);replayed++;}}VERIFY(replayed==2&&n[4].delivered==100&&n[0].confirmed==100);}
 else if(!strcmp(name,"telemetry")){uint8_t body[16]={0};uint32_t seq;logging=1;init("E2-echo",0);VERIFY(!ann_submit(n,5,ANN_TRANSACTION,0,body,sizeof(body),5000,1,clock_ms,&seq));advance(20);VERIFY(n[4].delivered==1&&n[0].delivered==1&&n[0].confirmed==1);logging=0;}
 else if(!strcmp(name,"wire")){ann_packet p;uint8_t wire[250];int size;memset(&p,0,sizeof(p));p.type=ANN_DATA;p.ttl=8;p.path_len=2;p.index=1;p.path[0]=p.origin=1;p.path[1]=p.dst=5;p.boot=100;p.seq=7;p.remaining_ms=5000;p.kind=ANN_TRANSACTION;p.payload_len=3;memcpy(p.payload,"abc",3);size=ann_encode(&p,wire,250);VERIFY(size==115);printf("{\"wire_hex\":\"");for(i=0;i<(unsigned)size;i++)printf("%02x",wire[i]);puts("\"}");for(i=0;i<(unsigned)size;i++){ann_packet decoded;wire[i]^=1;VERIFY(ann_decode(&decoded,wire,(size_t)size)<0);wire[i]^=1;}}
 else{VERIFY(0);}
}
int main(int argc,char **argv){if(argc!=2)return 2;run_case(argv[1]);printf("{\"schema\":\"e2.core-test.v1\",\"case\":\"%s\",\"checks\":%d,\"failures\":%d,\"evidence_kind\":\"synthetic\",\"radio\":false}\n",argv[1],checks,errors);return errors?1:0;}
