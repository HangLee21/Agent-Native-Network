import json,socket,subprocess,sys,time
from pathlib import Path
ROOT=Path(r'D:\Multi-Agent Network');PROD=ROOT/'.worktrees/production';OUT=ROOT/'simulation/outputs/H-025/20261115-03-compat';FIX=ROOT/'simulation/outputs/H-025/20261115-02-legacy-fixture'
sys.path.insert(0,str(PROD/'app/services'))
from tools.mobile_gateway.sources import Sources
src=Sources(udp_host='127.0.0.1',udp_port=0);assert src.sock is not None,src.error
client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(3)
try:
 dest=src.sock.getsockname();assert dest[0]=='127.0.0.1' and dest[1]!=1680
 push=(FIX/'push-data.bin').read_bytes();pull=(FIX/'pull-data.bin').read_bytes()
 client.sendto(push,dest);ack,peer=client.recvfrom(256);assert ack.hex()=='02123401' and peer==dest,(ack.hex(),peer,dest)
 client.sendto(pull,dest);ack2,peer2=client.recvfrom(256);assert ack2.hex()=='02567804' and peer2==dest,(ack2.hex(),peer2,dest)
 topology=src.topology();reports=topology.get('reports',[]);assert len(reports)==1,reports
 rep=reports[0]['report'];assert rep['observer_id']=='90:da:72:48:a4:e0' and rep['report_seq']==361,rep
 assert topology['receiver']['gateway_id']=='b827ebfffe32e2c1'
 result={'udp':{'bind':'127.0.0.1 ephemeral','push_ack':ack.hex(),'pull_ack':ack2.hex(),'same_socket':True,'gateway_id':topology['receiver']['gateway_id'],'observer_id':rep['observer_id'],'report_seq':rep['report_seq'],'historical_payload_synthetic_transport':True},'launch_modes':{}}
 for mode in ('legacy_local','remote','node_serial'):
  command=['cmd.exe','/c','START_STUDIO.cmd','--dry-run','--config',str(OUT/('fleet-'+mode+'.json'))]
  proc=subprocess.run(command,cwd=str(PROD),capture_output=True,text=True,encoding='utf-8',timeout=15)
  assert proc.returncode==0,(mode,proc.returncode,proc.stderr,proc.stdout)
  lines=[x for x in proc.stdout.splitlines() if x.startswith('{')];assert lines,(mode,proc.stdout)
  obj=json.loads(lines[-1]);assert obj['state']=='dry_run' and obj['gateway_mode']==mode and obj['hardware_probed'] is False,obj
  result['launch_modes'][mode]={'parsed':True,'release_ready':obj['release_ready'],'reason':obj.get('reason'),'hardware_probed':False}
 print(json.dumps(result,ensure_ascii=False))
finally:client.close();src.close()
