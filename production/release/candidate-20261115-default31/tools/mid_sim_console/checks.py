"""Read-only HTTP/validation checks; does not start simulation experiments."""
import argparse,datetime,hashlib,http.client,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8767);p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output).resolve();assert out.is_relative_to(ROOT/'simulation/outputs/E2-020') and not out.exists();out.mkdir(parents=True);checks=[]
    def req(path,data=None,host=None,origin=None):
        c=http.client.HTTPConnection('127.0.0.1',a.port,timeout=5);headers={'Host':host or f'127.0.0.1:{a.port}'}
        if data is not None:headers.update({'Content-Type':'application/json','Origin':origin or f'http://127.0.0.1:{a.port}'})
        c.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,headers);r=c.getresponse();raw=r.read();code=r.status;c.close()
        try:raw=json.loads(raw)
        except ValueError:raw=raw.decode('utf-8')
        return code,raw
    def check(name,condition):checks.append(dict(name=name,passed=condition));assert condition,name
    try:
        code,catalog=req('/api/catalog');check('catalog_matches_real_H_ranges',code==200 and catalog['limits']['delay_ms']==[0,2000] and len(catalog['defaults']['links'])==20)
        code,default=req('/api/defaults');check('default_same_as_catalog',code==200 and default['settings']==catalog['defaults'])
        check('same_origin_D_page',req('/')[0]==200)
        check('invalid_host',req('/api/status',host='evil.test')[0]==403)
        check('cross_origin_write',req('/api/run',{},origin='https://evil.test')[0]==403)
        check('loopback_origin_mismatch',req('/api/run',{},origin=f'http://localhost:{a.port}')[0]==403)
        check('bad_delay_field',req('/api/run',{'settings':{'links':[dict(src='A',dst='C',delay_ms=2001)]}})[0]==422)
        check('duplicate_directed_edge',req('/api/run',{'settings':{'links':[dict(src='A',dst='C'),dict(src='A',dst='C')]}})[0]==422)
        check('window_backwards',req('/api/run',{'settings':dict(fault_start_s=40,fault_end_s=20)})[0]==422)
        check('no_model_paths_or_commands',req('/api/run',{'settings':{'command':'x'}})[0]==422)
        check('validate_no_execution',req('/api/validate',{'settings':default['settings']})[0]==200)
        check('path_traversal',req('/%2e%2e/%2e%2e/coordination/CURRENT.md')[0]==404)
        check('unknown_cancel',req('/api/runs/20261107-000000-000000000000/cancel',{})[0]==404)
    finally:
        (out/'checks.json').write_text(json.dumps(dict(checks=checks,simulation_runs_started=0,hardware_operations=0),indent=2),encoding='utf-8')
        m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E2-020',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,python_executable=sys.executable,output_directory=str(out),status='passed' if all(c['passed'] for c in checks) else 'failed',exit_code=0 if all(c['passed'] for c in checks) else 1,budget=dict(simulation_runs_started=0,hardware_operations=0),dirty_files_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('server.py')]},limitations=['HTTP/validation only; runner experiments and browser acceptance recorded separately.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=len(checks),simulation_runs_started=0)))

if __name__=='__main__':main()
