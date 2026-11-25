"""Exercise actual IP operation and destination handler with fake IP I/O/radio admission."""
from pathlib import Path
import argparse,datetime,json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[3]
TEST=r'''
int main(void){sr_init(&router,self,boot,31);nd_init(&neighbors,self,boot,31);field_ip_request("{\"schema\":\"field.ip.v2\",\"op\":\"hello\",\"pc_id\":9,\"pc_session\":77}");assert(!strcmp(cJSON_GetObjectItemCaseSensitive(last,"event")->valuestring,"status"));
const char*good="{\"schema\":\"field.ip.v2\",\"op\":\"send\",\"pc_id\":9,\"pc_session\":77,\"entry_boot\":100,\"transaction\":1,\"dst\":\"02:00:00:00:00:02\",\"payload_hex\":\"00ff\"}";
field_ip_request(good);assert(submits==1&&!strcmp(cJSON_GetObjectItemCaseSensitive(last,"event")->valuestring,"accepted"));field_ip_request(good);assert(submits==1&&cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(last,"duplicate")));
field_ip_request("{\"schema\":\"field.ip.v2\",\"op\":\"send\",\"pc_id\":9,\"pc_session\":77,\"entry_boot\":99,\"transaction\":2,\"dst\":\"02:00:00:00:00:02\",\"payload_hex\":\"00ff\"}");assert(submits==1&&!strcmp(cJSON_GetObjectItemCaseSensitive(last,"event")->valuestring,"rejected"));
field_ip_request("{\"schema\":\"field.ip.v2\",\"op\":\"send\",\"pc_id\":9,\"pc_session\":77,\"entry_boot\":100,\"transaction\":1,\"dst\":\"02:00:00:00:00:02\",\"payload_hex\":\"0000\"}");assert(submits==1&&!strcmp(cJSON_GetObjectItemCaseSensitive(last,"error")->valuestring,"id_reuse"));
fg_packet ack={.kind=FG_RECEIPT,.pc_id=9,.session=77,.transaction=1,.len=10};field_put32(ack.body,100);field_put32(ack.body+4,1);ack.body[8]=0;ack.body[9]=255;sr_event e={.origin={{2,0,0,0,0,2}},.boot=101,.seq=50,.dst=self};e.len=(uint16_t)fg_encode(&ack,e.payload,160);pc_now=88;field_gateway_receive(&e);assert(cJSON_GetObjectItemCaseSensitive(last,"pc_session")->valueint==77);assert(!strcmp(cJSON_GetObjectItemCaseSensitive(last,"event")->valuestring,"delivery")&&!strcmp(cJSON_GetObjectItemCaseSensitive(last,"payload_hex")->valuestring,"00ff"));
fg_packet up={.kind=FG_UP,.pc_id=9,.transaction=99,.len=2,.body={1,255}};e.origin.mac[5]=3;e.boot=102;e.seq=60;e.len=(uint16_t)fg_encode(&up,e.payload,160);field_gateway_receive(&e);assert(!strcmp(cJSON_GetObjectItemCaseSensitive(last,"event")->valuestring,"inbox")&&!strcmp(cJSON_GetObjectItemCaseSensitive(last,"payload_hex")->valuestring,"01ff"));
/* Two different entries -> same final logical PC id/session/transaction. */
self.mac[5]=2;boot=101;fg_packet down={.kind=FG_DOWN,.pc_id=9,.session=77,.transaction=8,.len=2,.body={'H','i'}};e.origin.mac[5]=1;e.boot=100;e.seq=70;e.dst=self;e.len=(uint16_t)fg_encode(&down,e.payload,160);field_gateway_receive(&e);assert(local_deliveries==1);e.origin.mac[5]=4;e.boot=103;e.seq=80;field_gateway_receive(&e);assert(local_deliveries==1);down.body[0]='N';e.len=(uint16_t)fg_encode(&down,e.payload,160);field_gateway_receive(&e);assert(local_deliveries==1&&gateway_rejected==1);
puts("PASS actual IP parser/handler: source admission idempotence, changed-id content rejection, stale entry boot, exact destination receipt, active remote inbox, final cross-entry dedup; I/O is synthetic");cJSON_Delete(last);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
 if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
 out=ROOT/'simulation/outputs/E1-027'/a.run;out.mkdir(parents=True,exist_ok=False);base=ROOT/'firmware/mid_baseline/field_agent';app=(base/'idf/main/app_main.c').read_text(encoding='utf-8');inc=(base/'idf/main/field_runtime.inc').read_text(encoding='utf-8')
 def between(s,a,b):return s[s.index(a):s.index(b)]
 extracted=between(app,'static void mac_text(','static cJSON* event(')+between(app,'static int hexval(','static int printable(')+between(inc,'static uint32_t field_get32(','static int field_nvs_read(')+between(inc,'static const char*field_kind(','static void field_counters(')+between(inc,'static void field_hex(','static void field_records(')
 code='#include "bridge.h"\n#include "field.h"\n#include "source_route.h"\n#include "neighbors.h"\n#include "cJSON.h"\n#include <stdio.h>\n#include <string.h>\n#include <assert.h>\n#include <stdbool.h>\n'+r'''
static mid_id self={{2,0,0,0,0,1}};static uint32_t boot=100,sequence,field_last_seq;static uint32_t pc_now=77;static int active=1,route_mode=1;static sr_node router;static fa_node agent;static nd_node neighbors;static fg_node bridge_state;static unsigned gateway_rejected,submits,local_deliveries;
typedef struct {int used;uint32_t transaction,session;mid_id dst;uint64_t until;} field_query;static field_query ip_queries[8];static cJSON*last;
static uint64_t millis(void){return 1000;}static uint32_t field_rng(void*a){(void)a;return 7;}static void field_ip_suspend(uint64_t until){(void)until;}
static int field_ip_live(uint64_t now){(void)now;return 1;}static uint64_t field_ip_until(void){return 11000;}static uint32_t field_ip_pc_id(void){return 9;}static uint32_t field_ip_session(void){return pc_now;}
static int field_ip_lease(uint32_t a,uint32_t b,uint32_t c,uint32_t d,uint32_t e,uint64_t f){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;return 0;}
static void field_ip_status(cJSON*j,uint64_t now){(void)now;cJSON_AddNumberToObject(j,"max_payload_bytes",128);}
static void field_ip_base(cJSON*j,const char*type){cJSON_AddStringToObject(j,"event",type);cJSON_AddNumberToObject(j,"pc_session",pc_now);}static void field_ip_emit(cJSON*j,int keep){(void)keep;cJSON_Delete(last);last=j;}static void field_ip_poll(uint64_t after){(void)after;}
static cJSON*event(const char*type){cJSON*j=cJSON_CreateObject();cJSON_AddStringToObject(j,"event",type);return j;}
static void output(cJSON*j){if(!strcmp(cJSON_GetObjectItemCaseSensitive(j,"event")->valuestring,"pc_payload_received"))local_deliveries++;cJSON_Delete(j);}
static int field_submit(mid_id dst,const uint8_t*bytes,unsigned len){(void)dst;fg_packet p;assert(!fg_decode(&p,bytes,len));submits++;field_last_seq=++sequence;return 0;}
#define CHANNEL 6
'''+extracted+between(inc,'static void pc_event_payload(','static int field_send_envelope(')+between(inc,'static void field_ip_request(','static void field_route_event(')+TEST
 (out/'ip_test.c').write_text(code,encoding='utf-8');cj=ROOT/'.local/espnow/E1-015/sdk/esp-idf-v5.5.1/components/json/cJSON';cmd=['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(ROOT/'firmware/mid_baseline'),'-I'+str(base),'-I'+str(cj),str(ROOT/'firmware/mid_baseline/mid.c'),str(base/'source_route.c'),str(base/'field.c'),str(base/'bridge.c'),str(base/'neighbors.c'),str(cj/'cJSON.c'),str(out/'ip_test.c'),'-o',str(out/'test.exe')]
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-027',run_id=a.run,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='running',command=cmd,worktree=str(ROOT),output_directory=str(out),budget=dict(per_command_s=120,device_access=0),runtime_sha256=hashlib.sha256(inc.encode()).hexdigest(),limitations=['Actual extracted parser/handler; fake IP/radio I/O. No real UDP/hotspot/ESP/RF evidence.'])
 def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
 save()
 try:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();r=subprocess.run([str(out/'test.exe')],capture_output=True,text=True,timeout=120);(out/'host.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();print(r.stdout);m.update(status='passed',exit_code=0)
 except Exception as e:m.update(status='failed',exit_code=1,error=repr(e))
 m['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps(dict(status=m['status'],output=str(out))));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())
