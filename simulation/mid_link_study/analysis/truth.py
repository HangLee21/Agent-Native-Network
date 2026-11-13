"""Evaluation-only view of H-008 assumed directed links. Never used by a policy."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from simulation.mid_link_study.scenarios.scenarios import load,state_at
try:
    from .metrics import directed_path
except ImportError:
    from metrics import directed_path


class Truth:
    def __init__(self,scenario_id):
        self.scenario=load(scenario_id)
        self.scenario_id=scenario_id

    def snapshot(self,t):
        if not 0<=t<=60:return None
        state=state_at(self.scenario,t)
        positive=[(e['src'],e['dst']) for e in state['edges'] if e['pdr']>0 and e['capacity_payload_bps']>0]
        paths=[dict(src=src,dst=dst,reachable=(path:=directed_path(state['active_nodes'],positive,src,dst)) is not None,path=path) for src,dst in [('A','B'),('B','A')]]
        return dict(state,flows=paths,evidence_kind='software_simulation',scope='evaluation_only_optimistic_path')

    def __call__(self,t,src,dst):
        state=self.snapshot(t)
        if state is None:return None
        return next(f['reachable'] for f in state['flows'] if f['src']==src and f['dst']==dst)

    def timeline(self):
        return [self.snapshot(t/2) for t in range(121)]

    def evaluation(self):
        return dict(impact_start_s=20,recovery_anchor_s=40 if self.scenario_id=='partition_restore' else 20,
                    recovery_anchor_kind='physical_graph_reconnected' if self.scenario_id=='partition_restore' else 'impairment_begins',
                    source='H-008 v1 declared intervention knots; fixed before E1 data')
