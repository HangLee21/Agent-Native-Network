"""Exercise actual adapter parsing/formatting functions with the installed SDK cJSON."""
from pathlib import Path
import argparse,datetime,json,subprocess,hashlib,sys
ROOT=Path(__file__).resolve().parents[3]
MAIN=r'''
int main(void){
 const char*valid="{\"position_boot\":7,\"position_seq\":1,\"source\":\"simulated\",\"fix\":true,\"age_ms\":500,\"lat\":31.2345678,\"lon\":121.2345678,\"accuracy_m\":null}";
 cJSON*j=cJSON_Parse(valid);mt_position p;assert(!position_parse(j,&p));assert(p.lat_e7==312345678&&p.lon_e7==1212345678&&p.accuracy_mm==UINT32_MAX);cJSON_Delete(j);
 j=cJSON_CreateObject();position_fields(j,p);cJSON*x=cJSON_GetObjectItemCaseSensitive(j,"position");assert(cJSON_IsObject(x)&&cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(x,"accuracy_m")));char*text=cJSON_PrintUnformatted(j);puts(text);cJSON_free(text);cJSON_Delete(j);
 j=cJSON_CreateObject();position_fields(j,mid_mt_aged(p,29501));assert(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(j,"position"))&&cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"stale")));cJSON_Delete(j);assert(mid_mt_aged(p,29500).fix);
 mt_node node;mid_id self={{2,0,0,0,0,1}};mid_mt_init(&node,self,1,30);j=cJSON_CreateObject();position_fields(j,mid_mt_local(&node,0));assert(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(j,"position_boot"))&&cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(j,"position_age_ms")));cJSON_Delete(j);
 const char*bad[]={
 "{\"position_boot\":7,\"position_seq\":1,\"source\":\"gnss\",\"fix\":true,\"age_ms\":0,\"lat\":91,\"lon\":0}",
 "{\"position_boot\":7,\"position_seq\":1,\"source\":\"gnss\",\"fix\":true,\"age_ms\":0,\"lat\":1e309,\"lon\":0}",
 "{\"position_boot\":7,\"position_seq\":1,\"source\":\"unavailable\",\"fix\":true,\"age_ms\":0,\"lat\":0,\"lon\":0}",
 "{\"position_boot\":7,\"position_seq\":1,\"source\":\"gnss\",\"fix\":false,\"age_ms\":0,\"lat\":0,\"lon\":0}",
 "{\"position_boot\":0,\"position_seq\":1,\"source\":\"gnss\",\"fix\":false,\"age_ms\":0,\"lat\":null,\"lon\":null}",
 "{\"position_boot\":7,\"position_seq\":1,\"source\":\"gnss\",\"fix\":true,\"age_ms\":0.5,\"lat\":0,\"lon\":0}",
 "{\"position_boot\":7,\"position_seq\":1,\"source\":\"gnss\",\"fix\":true,\"age_ms\":0,\"lat\":0,\"lon\":0,\"accuracy_m\":-1}"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++){j=cJSON_Parse(bad[i]);assert(j&&position_parse(j,&p)<0);cJSON_Delete(j);}
 j=cJSON_Parse("{\"position_boot\":7,\"position_seq\":2,\"source\":\"gnss\",\"fix\":false,\"age_ms\":0,\"lat\":null,\"lon\":null}");assert(!position_parse(j,&p)&&!p.fix&&p.source==1);cJSON_Delete(j);
 puts("PASS actual cJSON parser/formatter: WGS84, finite/range/type, accuracy null, unavailable identities null, freshness boundary and no-fix");return 0;
}
'''
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
    if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
    out=ROOT/'simulation/outputs/E1-026'/a.run;out.mkdir(parents=True,exist_ok=False)
    app=ROOT/'firmware/mid_baseline/mobile_telemetry/idf/main/app_main.c';source=app.read_text(encoding='utf-8')
    def between(start,end):return source[source.index(start):source.index(end)]
    extracted=between('static const char*str(', 'static int printable(')+between('static const char*position_source(', 'static void telemetry_fields(')+between('static int zero_u32(', 'static void rf_observation(')
    test=out/'json_test.c';test.write_text('#include "telemetry.h"\n#include "cJSON.h"\n#include <stdio.h>\n#include <string.h>\n#include <math.h>\n#include <assert.h>\n'+extracted+MAIN,encoding='utf-8')
    cj=ROOT/'.local/espnow/E1-015/sdk/esp-idf-v5.5.1/components/json/cJSON'
    cmd=['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(cj),'-I'+str(ROOT/'firmware/mid_baseline'),'-I'+str(ROOT/'firmware/mid_baseline/mobile_telemetry'),str(ROOT/'firmware/mid_baseline/mid.c'),str(ROOT/'firmware/mid_baseline/mobile_telemetry/telemetry.c'),str(cj/'cJSON.c'),str(test),'-lm','-o',str(out/'test.exe')]
    m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-026',run_id=a.run,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=cmd,worktree=str(ROOT),output_directory=str(out),budget=dict(per_command_s=120,device_access=0),status='running',app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),cjson_sha256=hashlib.sha256((cj/'cJSON.c').read_bytes()).hexdigest(),limitations=['Extracted actual parse/format functions, not full firmware/hardware execution.'])
    def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
        r=subprocess.run([str(out/'test.exe')],capture_output=True,text=True,timeout=120);(out/'host.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();print(r.stdout);m.update(status='passed',exit_code=0)
    except Exception as e:m.update(status='failed',exit_code=1,error=repr(e))
    m['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps(dict(status=m['status'],output=str(out))));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())
