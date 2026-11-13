"""Finite three-process, three-board local-edge acceptance. No host forwarding."""
import argparse,datetime,json,os,queue,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import reservation

class Client:
 def __init__(self,label,binding,out,profile=None,epoch=1):
  self.label=label;self.rows=[];self.queue=queue.Queue();self.log=out/f'{label}-{epoch}.stdout.jsonl';self.err=(out/f'{label}-{epoch}.stderr.txt').open('x',encoding='utf-8');self.requests=(out/f'{label}-{epoch}.requests.jsonl').open('x',encoding='utf-8')
  self.command=[sys.executable,'-m','tools.mid_edge','--port',binding['port'],'--node-id',binding['node_id'],'--baud','460800','--log',str(out/f'{label}-{epoch}.events.jsonl')]
  if profile:self.command+=['--profile',str(profile)]
  self.proc=subprocess.Popen(self.command,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,text=True,encoding='utf-8',bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  def read():
   with self.log.open('x',encoding='utf-8') as f:
    for line in self.proc.stdout:
     f.write(line);f.flush()
     try:v=json.loads(line)
     except ValueError:continue
     self.rows.append(v);self.queue.put(v)
  self.reader=threading.Thread(target=read,daemon=True);self.reader.start();self.ready=self.queue.get(timeout=12);assert self.ready.get('ready') is True,self.ready
 def ask(self,op,**fields):
  request=json.dumps(dict(op=op,**fields))+'\n';self.requests.write(request);self.requests.flush();self.proc.stdin.write(request);self.proc.stdin.flush();v=self.queue.get(timeout=10)
  if not v.get('ok'):raise RuntimeError(f'{self.label} {op}: {v}')
  return v['result']
 def close(self):
  if self.proc.stdin and not self.proc.stdin.closed:self.proc.stdin.close()
  try:self.proc.wait(timeout=4)
  except subprocess.TimeoutExpired:self.proc.terminate();self.proc.wait(timeout=3)
  self.reader.join(timeout=3);self.err.close();self.requests.close();assert self.proc.returncode==0,(self.label,self.proc.returncode)

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',type=Path);p.add_argument('--reboot-b',action='store_true');p.add_argument('--reboot-a',action='store_true');p.add_argument('--headless-c',action='store_true');a=p.parse_args()
 out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False);assert reservation()['owner']=='H012'
 labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_bytes())['labels'];bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_bytes())['bindings'];by={k:next(b for b in bindings if b['node_id']==labels[k])for k in 'ABC'}
 clients={};r=dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),evidence_kind='real_RF_same_PC_three_independent_local_processes',physical_hosts_verified=1,host_forwarding=False,profile_provisioned=bool(a.profile),packets=[],stop_confirmed={},closed={},child_commands={})
 def start(label,profile=None,epoch=1):
  c=Client(label,by[label],out,profile,epoch);clients[label]=c;r['child_commands'][f'{label}-{epoch}']=c.command;return c
 def packet(text):
  raw=text.encode('utf-8');tx=clients['A'].ask('send',dst=labels['C'],payload_hex=raw.hex());rx=clients['C'].ask('recv',timeout=4);identity={k:tx[k]for k in ('origin','origin_boot','seq','dst')}
  assert all(rx[k]==v for k,v in identity.items()) and rx['payload_hex']==raw.hex() and rx['node_id']==labels['C']
  end=time.monotonic()+2
  while True:
   events=clients['B'].ask('events',after=0);same=[e for e in events if all(e.get(k)==v for k,v in identity.items())]
   if any(e['event']=='rx_relay'for e in same) and any(e['event']=='tx_submit' and e.get('next_hop')==labels['C']for e in same):break
   if time.monotonic()>=end:raise AssertionError('B serial evidence not observed before deadline')
   time.sleep(.03)
  item=dict(text=text,payload_hex=raw.hex(),identity=identity,source_admission=tx,destination=rx,relay_events=same,actual_chain=['A','B','C']);r['packets'].append(item);print(json.dumps(dict(delivered=True,identity=identity,actual_chain=item['actual_chain'])),flush=True)
 try:
  for label in 'CBA':start(label,a.profile.resolve() if a.profile else None)
  r['before_local_start_info']={k:c.ask('info')for k,c in clients.items()}
  for k,info in r['before_local_start_info'].items():
   if info.get('deployment_saved') and not info.get('radio'):clients[k].ask('local_start')
  r['initial_info']={k:c.ask('info')for k,c in clients.items()}
  for k,info in r['initial_info'].items():assert info['node_id']==labels[k] and info['deployment_mode']=='offline_table' and info['deployment_saved'] and info['radio'] and not info['deployment_fault']
  if a.headless_c:assert r['initial_info']['C']['display_enabled'] is False and clients['C'].ask('stats')['display_hw']==0
  packet('H012 无屏端实际收件' if a.headless_c else 'H012 独立本地应用 A 经 B 到 C')
  if a.reboot_b:
   before=r['initial_info']['B']['boot_id'];clients.pop('B').close()
   command=[sys.executable,str(ROOT/'tools/mid_hardware/edge_bench/reset_board.py'),'--board','B','--output',str(out/'B-reset')]
   reset=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));(out/'B-reset-command.stdout.txt').write_text(reset.stdout);(out/'B-reset-command.stderr.txt').write_text(reset.stderr);assert reset.returncode==0
   start('B',epoch=2);r['after_B_reset_info']={k:c.ask('info')for k,c in clients.items()};b=r['after_B_reset_info']['B'];assert b['boot_id']!=before and b['deployment_mode']=='offline_table' and b['deployment_saved'] and b['radio'] and not b['deployment_fault']
   assert r['after_B_reset_info']['A']['boot_id']==r['initial_info']['A']['boot_id'] and r['after_B_reset_info']['C']['boot_id']==r['initial_info']['C']['boot_id']
   packet('H012 B 单独重启后原本地配置转发')
  if a.reboot_a:
   before=clients['A'].ask('info')['boot_id'];clients.pop('A').close()
   command=[sys.executable,str(ROOT/'tools/mid_hardware/edge_bench/reset_board.py'),'--board','A','--output',str(out/'A-reset')]
   reset=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));(out/'A-reset-command.stdout.txt').write_text(reset.stdout);(out/'A-reset-command.stderr.txt').write_text(reset.stderr);assert reset.returncode==0
   start('A',epoch=2);r['after_A_reset_info']={k:c.ask('info')for k,c in clients.items()};info=r['after_A_reset_info']['A'];assert info['boot_id']!=before and info['deployment_mode']=='offline_table' and info['deployment_saved'] and info['radio'] and not info['deployment_fault']
   packet('H012 A 新启动身份无需远端重配置')
  r['success']=True
 except Exception as exc:r.update(success=False,error=repr(exc))
 finally:
  for label,c in clients.items():
   try:
    c.ask('stop');s=c.ask('stats');r['stop_confirmed'][label]=s['radio'] is False and s['queue_depth']==0 and not s['stopping'];r.setdefault('final_stats',{})[label]=s
   except Exception as exc:r.setdefault('cleanup_errors',[]).append(dict(board=label,error=repr(exc)))
   try:c.close();r['closed'][label]=True
   except Exception as exc:r['closed'][label]=False;r.setdefault('cleanup_errors',[]).append(dict(board=label,error=repr(exc)))
  r['success']=r.get('success',False) and len(r['stop_confirmed'])==3 and all(r['stop_confirmed'].values()) and all(r['closed'].values()) and not r.get('cleanup_errors')
  r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:r.get(k)for k in ('success','error','stop_confirmed','closed','cleanup_errors')},ensure_ascii=False))
 return 0 if r['success'] else 1
if __name__=='__main__':raise SystemExit(main())
