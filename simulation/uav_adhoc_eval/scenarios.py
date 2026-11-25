import json
from pathlib import Path

speeds=[5,15,25,35,50]
scenarios=[dict(id=f'{motion}-{density}-{speed}',nodes=30,speed_m_s=speed,motion=motion,density=density,
    duration_s=300,offered_load='per_node_fixed',area_m=None,radio_range_m=None,
    first_batch=speed in (5,25,50),trajectory_seed=None,traffic_seed=None,
    status='proposed_parameters_not_calibrated') for motion in ('formation','crossing_separation','reorganization')
    for density in ('compact','sparse') for speed in speeds]
import argparse
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
with Path(a.output).open('x',encoding='utf-8') as f:json.dump(scenarios,f,indent=2)
