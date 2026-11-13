"""M-022 loopback-only software simulation console. Never imports device code."""
import argparse,copy,datetime,hashlib,json,mimetypes,os,re,secrets,subprocess,sys,threading,time,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from settings_api import catalog,get_defaults,normalize_settings,compile_scenario,settings_hash,SettingsError,plan
from view import build
import workbench
IDS=re.compile(r'^\d{8}-\d{6}-[a-f0-9]{12}$')

class Problem(Exception):
    def __init__(self,status,message,code='request_error'):self.status,self.message,self.code=status,message,code

def strict_pairs(items):
    result={}
    for k,v in items:
        if k in result:raise ValueError('duplicate JSON key')
        result[k]=v
    return result

class App:
    def __init__(self,state_path=None):
        self.lock=threading.RLock();self.active=None;self.jobs={};self.processes={};self.closing=False
        self.state=Path(state_path) if state_path else ROOT/'.local/mid/E2-020/state.json';self.state.parent.mkdir(parents=True,exist_ok=True)
        if self.state.exists():
            self.jobs=json.loads(self.state.read_bytes())
            for j in self.jobs.values():
                if j['state'] in ['queued','running']:j.update(state='failed',error='服务上次中断，保留部分记录；没有自动重跑。')
        python=ROOT/'.local/mid/E1-016/venv/Scripts/python.exe';self.python=str(python) if python.exists() else sys.executable
    def persist(self):
        temp=self.state.with_suffix('.tmp');temp.write_text(json.dumps(self.jobs,ensure_ascii=False,allow_nan=False),encoding='utf-8');temp.replace(self.state)
    def status(self):
        with self.lock:return dict(ok=True,mode='software_simulation',busy=self.active is not None,active_run_id=self.active,runs=[dict(run_id=j['run_id'],state=j['state'],url=j['url']) for j in reversed(list(self.jobs.values()))],limits=dict(wall_seconds=120,cpu_threads=2),process_id=os.getpid())
    def submit(self,settings,algorithm=None):
        normalized=normalize_settings(settings);scenario=compile_scenario(normalized)
        measured=normalized['schema']=='mid.measured.settings.v1'
        allowed=['fixed','latency_aware'] if normalized['schema'] in ['mid.routing.settings.v1','mid.measured.settings.v1'] else ['fixed','adaptive']
        if measured:
            from simulation.mid_link_console.runner.workbench import ALGORITHMS,validate_scenario
            allowed=list(ALGORITHMS)
            algorithm=algorithm or 'latency_aware'
            validate_scenario(scenario,algorithm)
        if algorithm is not None and algorithm not in allowed:raise ValueError('当前模式不支持所选算法。')
        with self.lock:
            if self.closing:raise Problem(503,'服务正在关闭。')
            if self.active:raise Problem(409,'已有一次模拟在运行，请等待或取消。','busy')
            rid=time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(6);out=ROOT/'simulation/outputs/E2-022'/rid;out.mkdir(parents=True,exist_ok=False)
            (out/'settings.json').write_text(json.dumps(normalized,ensure_ascii=False,indent=2),encoding='utf-8');(out/'scenario.json').write_text(json.dumps(scenario,ensure_ascii=False,indent=2),encoding='utf-8')
            executed='compare_latency' if measured and algorithm in ['fixed','latency_aware'] else algorithm
            (out/'options.json').write_text(json.dumps(dict(algorithm=executed)),encoding='utf-8')
            job=dict(ok=True,run_id=rid,state='queued',status='queued',settings=normalized,settings_sha256=settings_hash(normalized),started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),output_directory=str(out),url='/results/'+rid+'/',result_url='/api/runs/'+rid+'/result',error=None,result=None,cancel_requested=False)
            job.update(selected_algorithm=algorithm or allowed[-1],execution_semantics='actual_arms_executed' if measured and algorithm not in ['fixed','latency_aware'] else 'paired_run_selected_arm_display')
            self.jobs[rid]=job;self.active=rid;self.persist()
            threading.Thread(target=self.execute,args=(rid,),daemon=False).start();return copy.deepcopy(job)
    def execute(self,rid):
        with self.lock:
            job=self.jobs[rid];out=Path(job['output_directory']);job.update(state='running',status='running');self.persist()
        code=None;error=None
        try:
            env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONUTF8='1')
            with (out/'stdout.txt').open('xb') as stdout,(out/'stderr.txt').open('xb') as stderr:
                with self.lock:
                    if job['cancel_requested']:raise Problem(409,'已取消。')
                    proc=subprocess.Popen([self.python,str(HERE/'worker.py'),str(out/'settings.json'),str(out/'experiment'),str(out/'options.json')],cwd=str(ROOT),env=env,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.processes[rid]=proc;job['worker_pid']=proc.pid
                try:code=proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    error='运行超过120秒墙时上限，已结束计算并保留部分输出。';proc.kill();code=proc.wait()
            if code!=0 and not error:error='计算未完成：'+(out/'stderr.txt').read_text(encoding='utf-8',errors='replace')[-1500:]
            result=build(out/'experiment') if code==0 else self.load_result(out/'experiment')
            if code==0 and result.get('status') not in ['complete','completed']:error=result.get('error') or '执行器返回未完成状态。'
            if code==0 and result is None:error='执行器未写出可读取的结果。'
        except Exception as exc:error=str(exc);result=None
        finally:
            with self.lock:
                job.update(state='cancelled' if job['cancel_requested'] else 'failed' if error else 'completed',error=error,result=result,exit_code=code,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
                job['status']=job['state'];self.processes.pop(rid,None)
                manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));manifest.update(template_only=False,task_id='E2-022',run_id=rid,started_at=job['started_at'],finished_at=job['finished_at'],worktree=str(ROOT),command=[self.python,str(HERE/'worker.py'),str(out/'settings.json'),str(out/'experiment')],python_executable=self.python,output_directory=str(out),status=job['state'],exit_code=code,budget=dict(wall_seconds=120,cpu_threads=2,hardware_operations=0),data_and_weights_sha256={'settings.json':hashlib.sha256((out/'settings.json').read_bytes()).hexdigest()},limitations=['Software simulation only; settings frozen per run, no real RF.'])
                manifest['command'].append(str(out/'options.json'))
                manifest['data_and_weights_sha256']['options.json']=hashlib.sha256((out/'options.json').read_bytes()).hexdigest()
                manifest['dirty_files_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'worker.py',HERE/'server.py',HERE/'settings_api.py',HERE/'view.py',ROOT/'simulation/mid_link_console/settings/measured.py',ROOT/'simulation/mid_link_console/runner/workbench.py'] if p.is_file()}
                (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');(out/'job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
                if self.active==rid:self.active=None
                self.persist()
    @staticmethod
    def load_result(folder):
        for name in ['result.json','RESULT.json','INDEX.json','summary.json']:
            if (folder/name).is_file():return json.loads((folder/name).read_bytes())
        return None
    def get(self,rid):
        with self.lock:
            if rid not in self.jobs:raise Problem(404,'没有这个运行ID。')
            j=copy.deepcopy(self.jobs[rid]);j['summary']=(j.get('result') or {}).get('summary',j.get('result'));j['links']=dict(result=j['result_url'],replay=j['url']);return j
    def cancel(self,rid):
        with self.lock:
            if rid not in self.jobs:raise Problem(404,'没有这个运行ID。')
            job=self.jobs[rid]
            if job['state'] in ['queued','running']:
                job['cancel_requested']=True
                proc=self.processes.get(rid)
                (Path(job['output_directory'])/'cancel.flag').touch()
                if proc and proc.poll() is None:
                    def force_stop():
                        if proc.poll() is None:proc.kill()
                    timer=threading.Timer(2,force_stop);timer.daemon=True;timer.start()
                self.persist()
            return self.get(rid)

class Handler(BaseHTTPRequestHandler):
    def reply(self,code,value,kind='application/json; charset=utf-8'):
        raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8');self.send_response(code)
        for k,v in [('Content-Type',kind),('Content-Length',str(len(raw))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Content-Security-Policy',"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")]:self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)
    def body(self):
        if self.headers.get('Content-Type','').split(';')[0]!='application/json' or self.headers.get('Transfer-Encoding'):raise ValueError('需要application/json。')
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=65536:raise ValueError('请求大小应在1–65536字节。')
        result=json.loads(self.rfile.read(size),object_pairs_hook=strict_pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
        if not isinstance(result,dict):raise ValueError('JSON object required')
        return result
    def do_GET(self):self.handle_api(False)
    def do_POST(self):self.handle_api(True)
    def handle_api(self,write):
        try:
            self.connection.settimeout(10);port=self.server.server_port;host=self.headers.get('Host');origin=self.headers.get('Origin')
            if len(self.headers.get_all('Host',[]))!=1 or host not in [f'127.0.0.1:{port}',f'localhost:{port}']:raise Problem(403,'需要本机Host。')
            if len(self.headers.get_all('Origin',[]))>1 or ((write or origin is not None) and origin!='http://'+host) or (write and self.headers.get('Sec-Fetch-Site')=='cross-site'):raise Problem(403,'仅允许同源请求。')
            url=urlsplit(self.path);path=url.path;app=self.server.app;parts=path.strip('/').split('/')
            if not write and path=='/api/workbench':
                from simulation.mid_link_console.settings import measured
                value=workbench.snapshot()
                return self.reply(200,dict(ok=True,settings=value['settings'],snapshot=value,catalog=measured.catalog(),algorithms=[dict(id='fixed',label='固定链（配对选看）'),dict(id='latency_aware',label='时延感知（配对选看）'),dict(id='mid',label='原MID（限A↔B双向/不限跳数）')],execution_semantics='paired_run_selected_arm_display'))
            if (not write and path in ['/api/snapshot','/api/measured-defaults']) or (write and path=='/api/reset'):
                if write and self.body():raise ValueError('复位请求必须为{}。')
                return self.reply(200,dict(workbench.snapshot(),ok=True))
            if path.startswith('/api/hardware/'):
                code,value=workbench.forward('/api/'+path[len('/api/hardware/'):],self.body() if write else None)
                return self.reply(code,value)
            if not write and path=='/api/status':return self.reply(200,app.status())
            mode=parse_qs(url.query).get('mode',['routing'])[0]
            if mode not in ['routing','mid']:raise Problem(400,'未知模式。')
            if not write and path in ['/api/catalog','/api/presets']:return self.reply(200,dict(catalog(mode),ok=True))
            if not write and (path=='/api/defaults' or path.startswith('/api/presets/')):
                preset=parse_qs(url.query).get('preset',[None])[0] if path=='/api/defaults' else path.rsplit('/',1)[-1];return self.reply(200,dict(ok=True,settings=get_defaults(preset,mode)))
            if write and path=='/api/plan':
                data=self.body()
                if set(data)-{'settings','time_s'} or 'settings' not in data:raise ValueError('需要settings及可选time_s。')
                return self.reply(200,plan(data['settings'],data.get('time_s',0)))
            if write and path in ['/api/run','/api/validate']:
                data=self.body();wrapped='settings' in data
                if wrapped and set(data)-{'settings','algorithm'}:raise ValueError('不支持的运行字段。')
                settings=data['settings'] if wrapped else data
                if path=='/api/run':return self.reply(202,app.submit(settings,data.get('algorithm') if wrapped else None))
                normalized=normalize_settings(settings);return self.reply(200,dict(ok=True,settings=normalized,scenario=compile_scenario(normalized),settings_sha256=settings_hash(normalized)))
            if len(parts)>=3 and parts[:2]==['api','runs'] and IDS.fullmatch(parts[2]):
                if not write and len(parts)==3:return self.reply(200,app.get(parts[2]))
                if not write and parts[3:]==['packets']:
                    job=app.get(parts[2]);return self.reply(200,dict(ok=True,run_id=job['run_id'],state=job['state'],packets=(job['result'] or {}).get('packets',{})))
                if not write and parts[3:]==['result']:
                    job=app.get(parts[2]);return self.reply(200,dict(ok=True,run_id=job['run_id'],state=job['state'],settings=job['settings'],result=job['result'],summary=job['summary'],links=job['links']))
                if write and parts[3:] in [['cancel'],['stop']]:
                    if self.body():raise ValueError('取消请求必须为{}。')
                    return self.reply(200,app.cancel(parts[2]))
            if write or path.startswith('/api/'):raise Problem(404,'接口不存在。')
            if len(parts)>=2 and parts[0]=='results' and IDS.fullmatch(parts[1]):
                job=app.get(parts[1]);base=Path(job['output_directory'])/'experiment';rel='/'.join(parts[2:]) or 'index.html'
                if rel=='index.html' and not (base/rel).is_file():
                    raw=('<!doctype html><meta charset="utf-8"><title>本次模拟结果</title><h1>本次真实模拟结果</h1><a href="/">返回控制台</a><pre id="r"></pre><script>fetch("'+job['result_url']+'").then(r=>r.json()).then(r=>document.getElementById("r").textContent=JSON.stringify(r,null,2))</script>').encode();return self.reply(200,raw,'text/html; charset=utf-8')
            else:
                base=ROOT/'research/agent_native_network/mid_sim_console';rel=path.lstrip('/') or 'index.html'
                if not (base/'index.html').is_file():base=HERE/'static'
            target=(base/unquote(rel)).resolve()
            if not target.is_relative_to(base.resolve()) or not target.is_file() or target.suffix not in ['.html','.css','.js','.json','.svg','.png','.csv','.jsonl']:raise Problem(404,'文件不存在。')
            return self.reply(200,target.read_bytes(),(mimetypes.guess_type(target.name)[0] or 'application/octet-stream')+'; charset=utf-8')
        except workbench.BridgeError as exc:self.reply(exc.status,exc.value)
        except ImportError as exc:self.reply(503,dict(ok=False,error=dict(code='snapshot_pending',message='实测快照尚未交付。')))
        except SettingsError as exc:self.reply(422,dict(ok=False,error=exc.as_dict()))
        except Problem as exc:self.reply(exc.status,dict(ok=False,error=dict(code=exc.code,message=exc.message)))
        except (ValueError,UnicodeError) as exc:self.reply(400,dict(ok=False,error=dict(code='invalid_request',message=str(exc))))
        except (BrokenPipeError,ConnectionResetError,TimeoutError):pass
        except Exception as exc:self.reply(500,dict(ok=False,error=dict(code='service_error',message=str(exc))))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8767);parser.add_argument('--open',action='store_true');args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('port must be 1024..65535')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.daemon_threads=True;server.app=App();url=f'http://127.0.0.1:{args.port}/';print('软件仿真控制台 '+url,flush=True)
    if args.open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.app.closing=True
        if server.app.active:server.app.cancel(server.app.active)
        server.server_close()

if __name__=='__main__':main()
