"""Fixed paired-run worker. No client-selected imports or commands."""
import json,os,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
if __name__=='__main__':
    settings=Path(sys.argv[1]);output=Path(sys.argv[2]).resolve()
    assert any(output.is_relative_to(ROOT/'simulation/outputs'/task) for task in ['E2-020','E2-021','E2-022']) and not output.exists()
    timer=threading.Timer(120,lambda:os._exit(124));timer.daemon=True;timer.start()
    data=json.loads(settings.read_bytes())
    options=json.loads(Path(sys.argv[3]).read_bytes()) if len(sys.argv)>3 else {}
    if data.get('schema')=='mid.measured.settings.v1':
        from simulation.mid_link_console.runner.workbench import run_pair
    elif data.get('schema')=='mid.routing.settings.v1':
        from simulation.mid_link_console.runner.routing_pair import run_pair
    else:
        from simulation.mid_link_console.runner.pair import run_pair
    kwargs=dict(algorithm=options.get('algorithm')) if data.get('schema')=='mid.measured.settings.v1' else {}
    result=run_pair(data,output,cancel=lambda:(settings.parent/'cancel.flag').exists(),**kwargs)
    print(json.dumps(result,ensure_ascii=True,default=str))
    raise SystemExit(0 if result.get('status')=='complete' else 2)
