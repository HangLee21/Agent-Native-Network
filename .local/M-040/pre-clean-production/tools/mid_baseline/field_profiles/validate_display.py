"""Host-only checks for the field OLED renderer and actual checkpoint cooldown function."""
from pathlib import Path
import argparse,datetime,json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[3]
DISPLAY=r'''
#include "mid_display.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void){mid_display_identity id={.mac={0x90,0xda,0x72,0x48,0xa4,0xf8},.channel=6,.label='A',.protocol=MID_DISPLAY_MID};mid_display_snapshot s;assert(!mid_display_model_init(&s,&id));mid_display_event e={.kind=MID_DISPLAY_EV_RX_RELAY,.at_ms=10000,.ref={.origin={0x90,0xda,0x72,0x48,0xa4,0xe0},.boot=3,.seq=22,.valid=7},.dst={0x90,0xda,0x72,0x48,0xa5,0xcc}};assert(!mid_display_model_apply(&s,&e));s.field_running=1;s.field_segment=2;s.field_tx=12;s.field_forward=3;s.field_rx=9;s.field_rf_valid=1;s.field_rssi=-70;s.field_rf_at=4000;memcpy(s.field_rf_peer,e.dst,6);char lines[8][22];mid_display_lines(&s,0,lines);assert(strstr(lines[3],"00000016")&&!strcmp(lines[4],"RF B -70 6s          ")&&strstr(lines[5],"RELAY RX")&&strstr(lines[6],"T12 F3 R9")&&strstr(lines[7],"S2 AGENT RUN"));e.kind=MID_DISPLAY_EV_TX_SUBMITTED;memcpy(e.next_hop,e.dst,6);assert(!mid_display_model_apply(&s,&e));mid_display_lines(&s,0,lines);assert(strstr(lines[5],"RX -> TX SUBMITTED"));uint8_t frame[1024];mid_display_render(&s,0,frame);unsigned pixels=0;for(unsigned i=0;i<1024;i++)pixels+=frame[i]!=0;assert(pixels>0);for(unsigned i=0;i<8;i++)puts(lines[i]);puts("PASS field OLED API3 default page seq/TX/relay/RX,physical-hop RSSI age, counts, segment; synthetic renderer only");return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
 if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
 out=ROOT/'simulation/outputs/E1-027'/a.run;out.mkdir(parents=True,exist_ok=False);base=ROOT/'firmware/mid_baseline/field_agent';display=base/'display/mid_display';(out/'display_test.c').write_text(DISPLAY,encoding='utf-8')
 inc=(base/'idf/main/field_runtime.inc').read_text(encoding='utf-8');checkpoint=inc[inc.index('static int field_checkpoint('):inc.index('static const char*field_kind(')]
 code='#include "field.h"\n#include <assert.h>\n#include <string.h>\n#include <stdio.h>\n#define ESP_OK 0\n#define ESP_ERR_INVALID_STATE 1\n'+r'''
typedef struct {uint32_t magic,boot,segment;uint64_t uptime;uint32_t totals[5],segment_counts[5],overwritten,late,origins_full;char note[32];} field_summary;
static fa_node agent;static uint32_t boot=100;static uint64_t checkpoint_attempt,checkpoint_due,clock_ms;static unsigned checkpoint_writes,checkpoint_failures,flash_calls;static field_summary saved;static int failed;
static uint64_t millis(void){return clock_ms;}static int field_nvs_write(const char*key,const void*value,size_t len){assert(!strcmp(key,"summary")&&len==sizeof(saved));flash_calls++;if(failed)return 2;memcpy(&saved,value,len);return 0;}
'''+checkpoint+r'''
int main(void){fa_init(&agent);agent.cfg.segment=2;agent.cfg.checkpoint_s=60;agent.totals[0]=7;clock_ms=59999;assert(field_checkpoint()!=ESP_OK&&!flash_calls);clock_ms=60000;assert(!field_checkpoint()&&flash_calls==1&&saved.boot==100&&saved.totals[0]==7);clock_ms=60001;assert(field_checkpoint()!=ESP_OK&&flash_calls==1);clock_ms=120000;failed=1;assert(field_checkpoint()!=ESP_OK&&flash_calls==2&&checkpoint_failures==1);clock_ms=120001;assert(field_checkpoint()!=ESP_OK&&flash_calls==2);boot=101;fa_init(&agent);assert(saved.boot==100&&!agent.totals[0]);puts("PASS actual checkpoint function minimum60s attempt cooldown, no early/per-packet write, failed commit cooldown, old summary not merged across boot; fake NVS only");return 0;}
'''
 (out/'checkpoint_test.c').write_text(code,encoding='utf-8');commands=[('display',['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(display/'include'),str(display/'src/mid_display_model.c'),str(display/'src/mid_display_render.c'),str(out/'display_test.c'),'-o',str(out/'display.exe')]),('checkpoint',['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(ROOT/'firmware/mid_baseline'),'-I'+str(base),str(ROOT/'firmware/mid_baseline/mid.c'),str(base/'field.c'),str(out/'checkpoint_test.c'),'-o',str(out/'checkpoint.exe')])]
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-027',run_id=a.run,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='running',command=[c for _,c in commands],worktree=str(ROOT),output_directory=str(out),budget=dict(per_command_s=120,device_access=0),limitations=['Pure C synthetic OLED snapshot and fake NVS. No actual pixels/PRG/powercut/flash execution.'])
 def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
 save()
 try:
  for name,cmd in commands:
   r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/(name+'-compile.log')).write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();r=subprocess.run([str(out/(name+'.exe'))],capture_output=True,text=True,timeout=120);(out/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();print(r.stdout)
  m.update(status='passed',exit_code=0)
 except Exception as e:m.update(status='failed',exit_code=1,error=repr(e))
 m['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps(dict(status=m['status'],output=str(out))));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())
