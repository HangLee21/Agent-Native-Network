"""Check actual serial snapshot formatter against fake RF/GPS/ND state."""
from pathlib import Path
import argparse,datetime,json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
    if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
    out=ROOT/'simulation/outputs/E1-026'/a.run;out.mkdir(parents=True,exist_ok=False);app=ROOT/'firmware/mid_baseline/mobile_telemetry/idf/main/app_main.c';s=app.read_text(encoding='utf-8')
    fields=s[s.index('static const char*position_source('):s.index('static int zero_u32(')];ids=s[s.index('static void mac_text('):s.index('static cJSON* event(')]
    code='#include "telemetry.h"\n#include "neighbors.h"\n#include "cJSON.h"\n#include <assert.h>\n#include <stdio.h>\n'+r'''
static mid_id self={{2,0,0,0,0,1}};static mt_node mobile;static nd_node neighbors;static uint64_t clock_ms=1000;
static int telemetry_enabled=1;static uint32_t telemetry_period=10000;
static unsigned telemetry_generated,telemetry_submitted,telemetry_link_ok,telemetry_link_fail,telemetry_deferred;
static uint64_t millis(void){return clock_ms;}
'''+ids+fields+r'''
int main(void){mid_id peer={{2,0,0,0,0,2}};mid_mt_init(&mobile,self,10,30);nd_init(&neighbors,self,10,30);
mobile.peers[0]=(mt_peer){.used=1,.peer=peer,.board_boot=20,.announcement_seq=1,.at=900,.position={.boot=1,.seq=2,.age_ms=500,.accuracy_mm=UINT32_MAX,.lat_e7=310000000,.lon_e7=1210000000,.source=2,.fix=1}};
mid_mt_sample(&mobile,peer,1,-50,1,6,800);mid_mt_sample(&mobile,peer,1,0,1,6,900);
cJSON*j=cJSON_CreateObject();telemetry_fields(j);cJSON*remote=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(j,"peer_positions"),0);assert(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(remote,"peer_boot_matches"))&&cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(remote,"position")));cJSON_Delete(j);
neighbors.peers[0]=(nd_peer){.used=1,.id=peer,.boot=20,.seen=900};j=cJSON_CreateObject();telemetry_fields(j);remote=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(j,"peer_positions"),0);cJSON*pos=cJSON_GetObjectItemCaseSensitive(remote,"position");assert(cJSON_IsObject(pos)&&cJSON_GetObjectItemCaseSensitive(pos,"age_ms")->valueint==600);cJSON*rf=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(j,"rf_neighbors"),0);assert(cJSON_GetObjectItemCaseSensitive(rf,"rssi_dbm")->valueint==0&&cJSON_GetObjectItemCaseSensitive(rf,"rssi_mean_dbm")->valuedouble== -25&&cJSON_GetObjectItemCaseSensitive(rf,"sample_age_ms")->valueint==100);char*line=cJSON_PrintUnformatted(j);puts(line);cJSON_free(line);cJSON_Delete(j);
neighbors.peers[0].boot=21;j=cJSON_CreateObject();telemetry_fields(j);remote=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(j,"peer_positions"),0);assert(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(remote,"position"))&&cJSON_GetObjectItemCaseSensitive(remote,"position_age_ms")->valueint==600);cJSON_Delete(j);
puts("PASS actual snapshot: directional RF and ages, measured0, mean, unknown provider null, peer reboot hides old coordinates without falsifying age; synthetic fixture");return 0;}
'''
    (out/'snapshot_test.c').write_text(code,encoding='utf-8');cj=ROOT/'.local/espnow/E1-015/sdk/esp-idf-v5.5.1/components/json/cJSON';base=ROOT/'firmware/mid_baseline';mt=base/'mobile_telemetry';cmd=['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(base),'-I'+str(mt),'-I'+str(cj),str(base/'mid.c'),str(mt/'telemetry.c'),str(mt/'neighbors.c'),str(cj/'cJSON.c'),str(out/'snapshot_test.c'),'-o',str(out/'test.exe')]
    m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-026',run_id=a.run,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=cmd,status='running',worktree=str(ROOT),output_directory=str(out),budget=dict(device_access=0,per_command_s=120),app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),limitations=['Actual snapshot functions with synthetic RF/ND/GPS, no real hardware measurements.'])
    def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();r=subprocess.run([str(out/'test.exe')],capture_output=True,text=True,timeout=120);(out/'host.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();print(r.stdout);m.update(status='passed',exit_code=0)
    except Exception as e:m.update(status='failed',exit_code=1,error=repr(e))
    m['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps(dict(status=m['status'],output=str(out))));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())
