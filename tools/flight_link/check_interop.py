"""Freeze E1 C source; compile host fixture and exchange actual codec bytes."""
import base64,datetime,hashlib,json,os,pathlib,shutil,subprocess,sys
from .codec import encode_command,decode_receipt
from .gateway import Gateway
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame

def main():
 root=pathlib.Path.cwd();out=root/'simulation/outputs/E2-035/20261114-02-c-interop';out.mkdir(parents=True,exist_ok=False);start=datetime.datetime.now(datetime.timezone.utc).isoformat();e1=root/'firmware/flight_link/mid_baseline/field_agent/lora_ref';h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 sourcefiles=[e1/'flight_control.c',e1/'flight_control.h',root/'tools/flight_link/interop_fixture.c'];hashes={str(p.relative_to(root)):h(p) for p in sourcefiles}
 for p in sourcefiles:shutil.copyfile(p,out/p.name)
 assert all(h(p)==hashes[str(p.relative_to(root))] for p in sourcefiles),'E1 files changed during snapshot'
 exe=out/'interop.exe';cmd=['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror',str(out/'interop_fixture.c'),str(out/'flight_control.c'),'-o',str(exe)];built=subprocess.run(cmd,capture_output=True,text=True);(out/'compile.txt').write_text(built.stdout+built.stderr);assert built.returncode==0
 q=dict(cmd_id='0000000000000001',target='90:da:72:48:a5:20',target_boot=7,report_seq=10,operation='echo',value=0x12345678,ttl_ms=5000);data=encode_command(q)
 def receive(at):
  r=subprocess.run([str(exe),str(at)],input=data.hex(),text=True,capture_output=True,timeout=5);assert r.returncode==0;return r.stdout.splitlines()
 good=receive(1001);one=good[0].split();two=good[1].split();assert one[0]=='1' and two[0]=='2' and good[2]=='1 1';ack=decode_receipt(bytes.fromhex(one[1]));dup=decode_receipt(bytes.fromhex(two[1]));assert ack['target']==q['target'] and ack['cmd_id']==q['cmd_id'] and ack['value']==q['value'] and ack['executed'] and dup['duplicate']
 late=receive(6001);assert late[0].strip()=='0' and late[2]=='0 0'
 class Sock:
  def __init__(self):self.sent=[]
  def sendto(self,d,a):self.sent.append((d,a))
 tx=dict(freq=470.5,rfch=0,powe=14,modu='LORA',datr='SF7BW125',codr='4/5',ipol=False,ncrc=False)
 g=Gateway('b827ebfffe32e2c1','127.0.0.1',tx,encoder=encode_command,ack_decoder=decode_receipt);g.sock=Sock();report=encode_frame(dict(observer_id=q['target'],observer_boot=7,report_seq=10,snapshot_at_ms=1000,wifi_group=31,report_period_ms=10000,neighbors=[]))
 packet=lambda b:dict(stat=1,size=len(b),freq=470.5,data=base64.b64encode(b).decode());g.ingest(packet(report));g.handle(bytes([2])+b'ab'+bytes([2])+bytes.fromhex(g.eui),('127.0.0.1',1700));g.enqueue(q);g.flush();g.ingest(packet(bytes.fromhex(one[1])));assert g.commands[q['cmd_id']]['state']=='executed'
 result=dict(host_c_interop='passed',duplicate_no_reexecution=True,expired_rejected=True,gateway_end_to_end_synthetic='executed',e1_source_sha256=hashes,compile_command=cmd,not_rf_or_target=True);(out/'result.json').write_text(json.dumps(result,indent=2));m=dict(task_id='E2-035',run_id=out.name,started_at=start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(root),git_commit=None,dirty_files_sha256=hashes,command=sys.orig_argv,python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256={},config_file=None,seeds=[],budget=dict(workers=1),output_directory=str(out),process_id=os.getpid(),status='passed',exit_code=0,review_reference=None,limitations=['Host GCC and synthetic input; no target build, physical gateway, board, or RF.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
