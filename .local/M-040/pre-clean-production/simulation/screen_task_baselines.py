"""Fetch pinned screening sources and smoke-test the untrained HeteroMRTA environment."""
from pathlib import Path
import hashlib
import json
import types
import urllib.request
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def main():
    manifest=json.loads((ROOT/'research/agent_native_network/task_baseline_sources.json').read_text())
    for repo in manifest:
        for f in repo['files']:
            dest=ROOT/'data/task_baseline_screen'/repo['repo'].split('/')[1]/f['path']
            if not dest.exists():
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(urllib.request.urlopen(f['url'],timeout=60).read())
            assert hashlib.sha256(dest.read_bytes()).hexdigest()==f['sha256']
    path=ROOT/'data/task_baseline_screen/HeteroMRTA/env/task_env.py'
    source=path.read_text()
    original='float(tasks_time[i, :])'
    replacement='tasks_time[i, :].item()'
    assert source.count(original)==1
    module=types.ModuleType('screened_task_env')
    # In-memory compatibility change only; downloaded upstream bytes remain intact.
    exec(compile(source.replace(original,replacement),str(path),'exec'),module.__dict__)
    env=module.TaskEnv(per_species_range=(3,3),species_range=(3,3),tasks_range=(15,15),seed=0)
    env.init_state()
    obs=env.agent_observe(0)
    result=dict(check='environment initialization and observation only; no policy inference',seed=0,
        numpy_version=np.__version__,compatibility_patch=dict(original=original,replacement=replacement,
        reason='NumPy 2 rejects float conversion of a one-element non-scalar array'),
        agents=env.agents_num,tasks=env.tasks_num,observation_shapes=[list(x.shape) for x in obs],
        all_finite=all(np.isfinite(x).all().item() for x in obs))
    assert result['all_finite']
    (ROOT/'research/agent_native_network/task_baseline_smoke.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
