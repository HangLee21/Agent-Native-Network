/* Deterministic host model, not RF: actual SR/FR C code, one local TX per 10 ms,
 * finite 20-slot fake driver (broadcast included), fixed deadline and losses. */
#include <source_route.h>
#include <reliable.h>
#include <peer_manager.h>
#ifndef HISTORICAL
#include <reliable_route.h>
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define N 30
#define ROUNDS 30
typedef struct {uint8_t mac[20][6];int used[20];} fake;
static int has(void*x,const uint8_t*m){fake*f=x;for(int i=0;i<20;i++)if(f->used[i]&&!memcmp(f->mac[i],m,6))return 1;return 0;}
static int add(void*x,const uint8_t*m){fake*f=x;for(int i=0;i<20;i++)if(!f->used[i]){f->used[i]=1;memcpy(f->mac[i],m,6);return 0;}return -1;}
static int del(void*x,const uint8_t*m){fake*f=x;for(int i=0;i<20;i++)if(f->used[i]&&!memcmp(f->mac[i],m,6)){f->used[i]=0;return 0;}return -1;}
static sr_node node[N];static fr_state reliable[N];static pm_state peers[N];static fake driver[N];static mid_id id[N];static uint32_t seq[N];
static unsigned received,confirmed,deadline,admit_fail,route_reject,driver_fail,air_drop,ack_drop,data_drop,timeout_count,attempts,duplicates;
static uint64_t now,start_at[N][ROUNDS+1],max_delay,repair_at,first_after=0;static unsigned link[N][N];
static uint64_t received_at[N][ROUNDS+1],confirmed_at[N][ROUNDS+1];static unsigned target[N][ROUNDS+1];
static unsigned loss_attempt[N][ROUNDS+1][2][5];
static unsigned variant;
static int connect(unsigned a,unsigned b,int moving){if(a==b)return 0;if(!moving)return 1;unsigned d=(a+N-b)%N;if(d>N/2)d=N-d;return d<=(variant==2?3u:2u) && !(now>=10000&&now<15000&&d==2&&((a+b+variant)%3==0));}
static int sendcb(void*ctx,const uint8_t dst[6],const uint8_t*b,size_t len){unsigned i=*(unsigned*)ctx;mid_id d;memcpy(d.mac,dst,6);attempts++;
#ifndef HISTORICAL
 fr_route_before(&reliable[i],&node[i],b,len,now);
#endif
 uint32_t q=++seq[i];int r=sr_submit(&node[i],d,q,b,len,now);if(r)route_reject++;
#ifndef HISTORICAL
 else fr_route_submitted(&reliable[i],b,len,q);
#endif
 return r;}
static void timeoutcb(void*x,const fr_message*m){(void)x;(void)m;timeout_count++;}
static int ensure(unsigned i,const uint8_t*m){
#ifdef LEGACY_PEERS
 const uint8_t b[6]={255,255,255,255,255,255};if(!has(&driver[i],b)&&add(&driver[i],b))return -1;if(has(&driver[i],m))return 0;return add(&driver[i],m);
#else
 pm_ops o={has,add,del,&driver[i]};
 return pm_ensure(&peers[i],&o,m,0);
#endif
}
static void events(unsigned i){sr_event e;while(sr_next_event(&node[i],&e))if(e.type==SR_DELIVERED){fr_message m;uint8_t ack[160];size_t n=0;int r=fr_receive(&reliable[i],e.origin.mac,e.boot,e.payload,e.len,now,&m,ack,&n);if(r==1){received++;unsigned src=m.src[5]-1u;if(src<N&&m.id<=ROUNDS)received_at[src][m.id]=now;}if(r==2)duplicates++;if(r==1||r==2){mid_id d;memcpy(d.mac,e.origin.mac,6);if(sr_submit(&node[i],d,++seq[i],ack,n,now))route_reject++;}if(r==3){
#if MID_ROUTE_FEEDBACK && !defined(HISTORICAL)
 if(m.route_seq)sr_confirmed(&node[i],m.route_seq,now);
#endif
 confirmed++;unsigned k=m.id;if(k<=ROUNDS&&start_at[i][k]){confirmed_at[i][k]=now;uint64_t d=now-start_at[i][k];if(d<=1000)deadline++;if(d>max_delay)max_delay=d;if(now>=repair_at&&!first_after)first_after=now-repair_at;}}}}
int main(int argc,char**argv){int moving=argc>1&&argv[1][0]=='m';const char*name=argc>1?argv[1]:"dense";size_t name_len=strlen(name);if(moving&&name_len&&name[name_len-1]>='1'&&name[name_len-1]<='2')variant=(unsigned)(name[name_len-1]-'0');for(unsigned i=0;i<N;i++){id[i]=(mid_id){{2,0,0,0,0,(uint8_t)(i+1)}};sr_init(&node[i],id[i],100+i,27);fr_init(&reliable[i],id[i].mac,100+i);pm_init(&peers[i]);}repair_at=moving?10000:999999;
 for(now=10;now<=37000;now+=10){
  for(unsigned i=0;i<N;i++)for(unsigned j=0;j<N;j++){int live=connect(i,j,moving);if(live!=(int)link[i][j]){link[i][j]=(unsigned)live;sr_neighbor(&node[i],id[j],100+j,live);}}
  if(now<=30000&&now%1000==10){unsigned round=(unsigned)(now/1000);for(unsigned i=0;i<N;i++){unsigned d=moving?(i+6+round%2)%N:(i+1+round%29)%N;uint32_t msg=0;uint8_t payload[16]={(uint8_t)i,(uint8_t)round};if(fr_start(&reliable[i],id[d].mac,100+d,payload,sizeof(payload),now,&msg))admit_fail++;else {assert(msg<=ROUNDS);start_at[i][msg]=now;target[i][msg]=d;}}}
  for(unsigned i=0;i<N;i++){fr_tick(&reliable[i],now,sendcb,timeoutcb,&i);sr_tick(&node[i],now);}
  for(unsigned i=0;i<N;i++){sr_out out;if(!sr_next_tx(&node[i],&out,now))continue;if(ensure(i,out.next.mac)){driver_fail++;sr_tx_result(&node[i],&out,0,now);continue;}
   uint8_t bytes[250];int n=sr_encode(&out.packet,bytes,sizeof(bytes));assert(n>0);int dropped=0;unsigned type=sr_base_type(out.packet.type);int ack=type==SR_DATA&&out.packet.len>=6&&!memcmp(out.packet.payload,"FLW2",4)&&out.packet.payload[5]==2;
   if(type==SR_DATA&&out.packet.len>=36&&!memcmp(out.packet.payload,"FLW2",4)){const uint8_t*p=out.packet.payload;unsigned origin=p[25]-1u;unsigned msg=(unsigned)p[12]|((unsigned)p[13]<<8)|((unsigned)p[14]<<16)|((unsigned)p[15]<<24);unsigned hop=out.packet.index-1u;
    if(origin<N&&msg<=ROUNDS&&hop<5){unsigned a=++loss_attempt[origin][msg][ack?1:0][hop];if((origin*17u+msg*7u+hop*11u+(unsigned)ack*5u+a*3u)%13u==0){dropped=1;air_drop++;if(ack)ack_drop++;else data_drop++;}}
   }
   if(!dropped)for(unsigned j=0;j<N;j++)if(link[i][j]&&(out.next.mac[0]==255||mid_equal(out.next,id[j])))(void)sr_receive(&node[j],id[i],bytes,(size_t)n,now);
   sr_tx_result(&node[i],&out,1,now);
  }
  for(unsigned i=0;i<N;i++)events(i);
 }
 uint64_t ctrl=0,data=0,over=0,denied=0;for(unsigned i=0;i<N;i++){ctrl+=node[i].control_frames;data+=node[i].data_frames;over+=node[i].overflows;denied+=node[i].rreq_denied;}
 unsigned missed_no_rx=0,missed_received=0,affected=0,recovered=0;uint64_t recovery_max=0;
 for(unsigned i=0;i<N;i++)for(unsigned k=1;k<=ROUNDS;k++)if(start_at[i][k]&&(!confirmed_at[i][k]||confirmed_at[i][k]-start_at[i][k]>1000)){if(received_at[i][k]&&received_at[i][k]<=start_at[i][k]+1000)missed_received++;else missed_no_rx++;}
 if(moving)for(unsigned i=0;i<N;i++)for(unsigned dest=0;dest<N;dest++){int was_affected=0;uint64_t first=0;for(unsigned k=1;k<=ROUNDS;k++)if(start_at[i][k]&&target[i][k]==dest){if(start_at[i][k]>=10000&&start_at[i][k]<15000&&(!confirmed_at[i][k]||confirmed_at[i][k]-start_at[i][k]>1000))was_affected=1;if(start_at[i][k]>=15000&&confirmed_at[i][k]&&confirmed_at[i][k]-start_at[i][k]<=1000&&(!first||confirmed_at[i][k]<first))first=confirmed_at[i][k];}if(was_affected){affected++;if(first){recovered++;if(first-15000>recovery_max)recovery_max=first-15000;}}}
 printf("{\"scenario\":\"%s\",\"offered\":%u,\"deadline_ms\":1000,\"deadline_confirmed\":%u,\"received\":%u,\"confirmed\":%u,\"missed_no_destination_by_deadline\":%u,\"missed_destination_received_by_deadline\":%u,\"affected_flows\":%u,\"affected_flows_recovered\":%u,\"affected_flow_recovery_max_ms\":%llu,\"admit_fail\":%u,\"route_reject\":%u,\"driver_fail\":%u,\"air_drop\":%u,\"data_drop\":%u,\"ack_drop\":%u,\"timeouts\":%u,\"attempts\":%u,\"duplicates\":%u,\"control_frames\":%llu,\"data_frames\":%llu,\"overflows\":%llu,\"rreq_denied\":%llu,\"max_confirm_delay_ms\":%llu,\"first_confirm_after_change_ms\":%llu,\"sr_bytes\":%llu,\"fr_bytes\":%llu,\"peer_manager_bytes\":%llu}\n",name,N*ROUNDS,deadline,received,confirmed,missed_no_rx,missed_received,affected,recovered,(unsigned long long)recovery_max,admit_fail,route_reject,driver_fail,air_drop,data_drop,ack_drop,timeout_count,attempts,duplicates,(unsigned long long)ctrl,(unsigned long long)data,(unsigned long long)over,(unsigned long long)denied,(unsigned long long)max_delay,(unsigned long long)first_after,(unsigned long long)sizeof(sr_node),(unsigned long long)sizeof(fr_state),(unsigned long long)sizeof(pm_state));return 0;}
