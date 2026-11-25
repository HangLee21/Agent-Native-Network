"""Five paired v2/v3 runs with one injected reboot, one worker."""
import argparse,datetime,json,pathlib,psutil,shutil,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--deadline-utc',required=True);a=p.parse_args();here=pathlib.Path(__file__).resolve().parent;root=here.parents[2];out=pathlib.Path(a.output).resolve();allowed=(root/'simulation/outputs/E1-031').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise ValueError('new output required')
out.mkdir(parents=True,exist_ok=False);deadline=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00'));start=time.monotonic();report={'status':'running','results':[],'workers':1,'max_wall_s':1200,'deadline_utc':a.deadline_utc,'reboot_node':0,'reboot_at_s':300,'new_epoch':41,'limits':['One source reset in synthetic radio','v3 assumes trustworthy monotonically increasing origin epoch; no real persistence/authentication','Destination reboot and stale data not solved']}
def save():(out/'batch.json').write_text(json.dumps(report,indent=2),encoding='utf8')
def source_stats(folder):
 off={};rec={};resets=[]
 with (folder/'events.jsonl').open() as f:
  for line in f:
   x=json.loads(line);k=(x.get('origin_id'),x.get('origin_boot_id'),x.get('seq'))
   if x['event']=='offered':off[k]=x
   elif x['event']=='destination_received':assert k in off and k not in rec and x['dst_id']==off[k]['dst_id'] and x['bytes_match'];rec[k]=x['time_us']
   elif x['event']=='reboot':resets.append((x['origin_id'],x['time_us'],x['new_boot']))
 assert resets==[(0,300000000,41)]
 z={}
 for label,boot in (('pre',1),('post',41)):
  keys=[k for k,x in off.items() if k[0]==0 and k[1]==boot and x['time_us']+1000000<=600000000];ok=sum(k in rec and rec[k]-off[k]['time_us']<=1000000 for k in keys);z[label]={'eligible':len(keys),'on_time':ok,'rate':ok/len(keys) if keys else None}
 return z
save()
try:
 for seed in range(5):
  dirs=[]
  for version in (2,3):
   if datetime.datetime.now(datetime.timezone.utc)>=deadline or time.monotonic()-start>=1200:raise TimeoutError('stage/batch limit')
   if psutil.virtual_memory().available<1073741824 or shutil.disk_usage(out).free<2147483648:raise RuntimeError('host resource guard')
   name=f'seed-{seed:02}-v{version}';folder=out/name;cmd=[sys.executable,'-B',str(here/'run.py'),'--output',str(folder),'--seconds','600','--seed',str(seed),'--policy','5','--mode','crossing','--speed','25','--density','compact','--version',str(version),'--reboot-at','300','--reboot-node','0'];report['active']=name;save()
   with (out/(name+'.log')).open('w',encoding='utf8') as log:
    q=subprocess.Popen(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
    while q.poll() is None:
     if datetime.datetime.now(datetime.timezone.utc)>=deadline or time.monotonic()-start>=1200 or psutil.virtual_memory().available<1073741824:
      q.terminate();q.wait(timeout=10);raise TimeoutError('case terminated on guard')
     time.sleep(.5)
    if q.returncode:raise RuntimeError(f'{name} exit {q.returncode}')
   dirs.append(folder)
  audit=out/f'audit-seed-{seed:02}';res=subprocess.run([sys.executable,'-B',str(here.parent/'epoch'/'audit_pair.py'),str(dirs[0]),str(dirs[1]),'--output',str(audit)],cwd=root,capture_output=True,text=True)
  if res.returncode:raise RuntimeError(res.stderr[:1000])
  x=json.loads((audit/'comparison.json').read_text());assert x['same_offers_and_geometric_4hop']
  z={'seed':seed,'v2_origin':source_stats(dirs[0]),'v3_origin':source_stats(dirs[1]),'whole_network_delta':x['paired_rate_difference'],'v2_control':x['base']['control_airtime_us'],'v3_control':x['candidate']['control_airtime_us']};report['results'].append(z);report.pop('active',None);save();print(json.dumps(z),flush=True)
 report['status']='completed'
except BaseException as e:report.update(status='interrupted',error=repr(e));raise
finally:report.update(elapsed_seconds=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
