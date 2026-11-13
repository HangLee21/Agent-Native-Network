"""Run actual callback body against bounded fake queue/metadata; no radio API is invoked."""
from pathlib import Path
import argparse,datetime,json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
    if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
    out=ROOT/'simulation/outputs/E1-026'/a.run;out.mkdir(parents=True,exist_ok=False)
    app=ROOT/'firmware/mid_baseline/mobile_telemetry/idf/main/app_main.c';s=app.read_text(encoding='utf-8');struct=s[s.index('typedef struct {int type,len'):s.index('typedef struct {mid_packet packet')];callback=s[s.index('static void receive_cb('):s.index('static void send_cb(')]
    code='#include <stdint.h>\n#include <string.h>\n#include <assert.h>\n#include <stdio.h>\n#define SERIAL_MAX 1024\n#define pdTRUE 1\n'+struct+r'''
typedef struct {int8_t rssi;uint8_t channel;} fake_rx_ctrl;
typedef struct {uint8_t*src_addr;fake_rx_ctrl*rx_ctrl;} esp_now_recv_info_t;
static input saved;static void*inputs;static volatile unsigned callback_drops;static int success=1;
static int64_t esp_timer_get_time(void){return 1234567;}
static int xQueueSend(void*q,const input*e,int ticks){(void)q;(void)ticks;saved=*e;return success;}
'''+callback+r'''
int main(void){uint8_t mac[6]={2,0,0,0,0,7},payload[1470];memset(payload,0xa5,sizeof(payload));fake_rx_ctrl rx={-61,6};esp_now_recv_info_t info={mac,&rx};
receive_cb(&info,payload,52);rx.rssi=-30;mac[5]=9;payload[0]=0;assert(saved.mac[5]==7&&saved.rssi==-61&&saved.rx_channel==6&&saved.rssi_valid&&saved.channel_valid&&saved.rx_at_ms==1234&&saved.data[0]==0xa5);
info.rx_ctrl=NULL;receive_cb(&info,payload,2);assert(saved.len==2&&!saved.rssi_valid&&!saved.channel_valid&&saved.data[2]==0);
info.rx_ctrl=&rx;rx.rssi=0;rx.channel=0;receive_cb(&info,payload,1470);assert(saved.len==1470&&saved.rssi_valid&&saved.rssi==0&&!saved.channel_valid&&saved.data[249]==0xa5&&saved.line[250]==0);
success=0;receive_cb(&info,payload,52);assert(callback_drops==1);puts("PASS actual callback copies sender/RSSI/channel/time by value, missing vs0, short/oversize bounded copy, queue drop accounting; fake metadata only");return 0;}
'''
    (out/'callback_test.c').write_text(code,encoding='utf-8');cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-pedantic',str(out/'callback_test.c'),'-o',str(out/'test.exe')]
    m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-026',run_id=a.run,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=cmd,status='running',worktree=str(ROOT),output_directory=str(out),budget=dict(device_access=0,per_command_s=120),app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),limitations=['Actual callback body, fake queue/metadata layout. Actual rx_ctrl ABI checked only by target compilation, RF values require H.'])
    def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();r=subprocess.run([str(out/'test.exe')],capture_output=True,text=True,timeout=120);(out/'host.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();print(r.stdout);m.update(status='passed',exit_code=0)
    except Exception as e:m.update(status='failed',exit_code=1,error=repr(e))
    m['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps(dict(status=m['status'],output=str(out))));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())
