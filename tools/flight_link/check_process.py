"""One finite real process, synthetic packet forwarder, and E1 host-C command endpoint."""
import base64,datetime,hashlib,json,os,pathlib,socket,subprocess,sys,time,urllib.request
root=pathlib.Path.cwd();out=root/'simulation/outputs/E2-035/20261114-08-process-health';out.mkdir(parents=True,exist_ok=False);start=datetime.datetime.now(datetime.timezone.utc).isoformat()
config=dict(freq=470.5,rfch=0,powe=14,modu='LORA',datr='SF7BW125',codr='4/5',ipol=False,ncrc=False);(out/'synthetic-tx-config.json').write_text(json.dumps(config))
cmd=[sys.executable,'-u','-X','utf8','-m','tools.flight_link.gateway','--udp-host','127.0.0.1','--udp-port','0','--http-port','0','--gateway-ip','127.0.0.1','--gateway-eui','b827ebfffe32e2c1','--tx-config',str(out/'synthetic-tx-config.json'),'--duration','6'];proc=subprocess.Popen(cmd,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');result={}
try:
 ready=json.loads(proc.stdout.readline());assert ready['codec_available'];result['ready']=ready
 from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame
 target='90:da:72:48:a5:20';eui=bytes.fromhex('b827ebfffe32e2c1');report=encode_frame(dict(observer_id=target,observer_boot=7,report_seq=10,snapshot_at_ms=1000,wifi_group=31,report_period_ms=10000,neighbors=[]))
 pkt=lambda b:dict(stat=1,size=len(b),freq=470.5,data=base64.b64encode(b).decode());gateway=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);gateway.bind(('127.0.0.1',0));gateway.settimeout(3);address=tuple(ready['udp'])
 gateway.sendto(bytes([2])+b'aa'+bytes([0])+eui+json.dumps({'rxpk':[pkt(report)]}).encode(),address);assert gateway.recvfrom(2048)[0]==bytes([2])+b'aa'+bytes([1])
 gateway.sendto(bytes([2])+b'bb'+bytes([2])+eui,address);assert gateway.recvfrom(2048)[0]==bytes([2])+b'bb'+bytes([4])
 base=f"http://127.0.0.1:{ready['http_port']}";opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));q=dict(cmd_id='0000000000000001',target=target,target_boot=7,report_seq=10,operation='echo',value=0x12345678,ttl_ms=5000)
 req=urllib.request.Request(base+'/api/v1/commands',json.dumps(q).encode(),headers={'Content-Type':'application/json','Origin':base});result['queued']=json.load(opener.open(req))['state']
 down=gateway.recvfrom(2048)[0];assert down[3]==3;encoded=base64.b64decode(json.loads(down[4:])['txpk']['data']);assert encoded[:4]==b'LRC2'
 gateway.sendto(bytes([2])+down[1:3]+bytes([5])+eui+b'{"txpk_ack":{"error":"NONE"}}',address)
 exe=root/'simulation/outputs/E2-035/20261114-02-c-interop/interop.exe';actual=subprocess.run([str(exe),'1001'],input=encoded.hex(),text=True,capture_output=True,timeout=5,check=True).stdout.splitlines();receipt=bytes.fromhex(actual[0].split()[1]);assert actual[0].startswith('1 ')
 gateway.sendto(bytes([2])+b'cc'+bytes([0])+eui+json.dumps({'rxpk':[pkt(receipt)]}).encode(),address);assert gateway.recvfrom(2048)[0]==bytes([2])+b'cc'+bytes([1])
 until=time.monotonic()+2
 while True:
  snapshot=json.load(opener.open(base+'/api/v1/lora/topology'));state=snapshot['commands'][0]['state']
  if state=='executed':break
  if time.monotonic()>until:raise AssertionError('no matched LRA2 receipt')
  time.sleep(.05)
 result.update(final_state=state,tx_ack=snapshot['commands'][0]['gateway_tx_ack'],receipt=snapshot['commands'][0]['receipt'],source='ephemeral_loopback_and_frozen_host_C_fixture',real_rf=False);gateway.close()
finally:
 try:stdout,stderr=proc.communicate(timeout=10)
 except subprocess.TimeoutExpired:proc.terminate();stdout,stderr=proc.communicate(timeout=5)
 (out/'process-stdout.txt').write_text(stdout,encoding='utf-8');(out/'process-stderr.txt').write_text(stderr,encoding='utf-8')
 if proc.returncode!=0:raise RuntimeError(f'gateway process exit {proc.returncode}: {stderr}')
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files=list((root/'tools/flight_link').glob('*.py'))+[root/'firmware/flight_link/CONTRACT.md',root/'simulation/outputs/E2-035/20261114-02-c-interop/interop.exe'];m=dict(task_id='E2-035',run_id=out.name,started_at=start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(root),git_commit=None,dirty_files_sha256={str(p.relative_to(root)):h(p) for p in files},command=cmd,python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256={},config_file=str(out/'synthetic-tx-config.json'),seeds=[],budget=dict(duration_s=6,workers=1),output_directory=str(out),process_id=proc.pid,status='passed',exit_code=proc.returncode,review_reference=None,limitations=['Synthetic localhost forwarder plus E1 host C fixture; no physical gateway, board, RF or target build. TX parameters are fixture-only.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2));print(json.dumps(result))
