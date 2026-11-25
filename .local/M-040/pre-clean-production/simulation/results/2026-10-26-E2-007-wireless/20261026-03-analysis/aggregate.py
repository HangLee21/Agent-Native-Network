"""Read fixed E2-007 results; write a new descriptive summary, never rerun tasks."""
import hashlib
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
def load(path):
    return json.loads(path.read_bytes())
def bounds(values):
    return dict(min=min(values),median=statistics.median(values),max=max(values))

def main():
    output=HERE/'descriptive_summary.json'
    if output.exists():
        raise FileExistsError(output)
    task_path=BASE/'20261026-02-task/summary.json'
    replay_path=BASE/'20261026-01-replay/summary.json'
    tasks=load(task_path)['cases'];replays=load(replay_path)['cases']
    summary=dict(task_episodes=len(tasks),task_successes=sum(r['status']=='success' for r in tasks),
        replay_cases=len(replays),replay_completed=sum(r['status']=='completed' for r in replays),
        task_groups={},replay_groups={},paired_cases=[],
        input_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (task_path,replay_path)},
        aggregation_scope='Descriptive only: 2 task seeds, 1 task MAC seed. Replay MAC seeds are not task replicates.')
    for condition in ('event_fifo','event_latest','refresh_latest'):
        a=[r for r in tasks if r['condition']==condition]
        summary['task_groups'][condition]=dict(n=len(a),
            makespan_to_instant=bounds([r['makespan_to_instant_ratio'] for r in a]),
            busy_fraction=bounds([r['network']['channel_busy_us']/(r['end_time']*2e7) for r in a]),
            queue_p95_seconds=bounds([r['delivery_metrics']['queue_delay_seconds_p95'] for r in a]),
            fact_age_p95_seconds=bounds([r['delivery_metrics']['fact_age_seconds_p95'] for r in a]),
            airtime_us_per_completed_task=bounds([r['network']['airtime_attempt_us']/r['completed'] for r in a]),
            application_bytes=sum(r['network']['demand_application_bytes'] for r in a),
            event_bytes=sum(r['publication_bytes']['event'] for r in a),
            refresh_bytes=sum(r['publication_bytes']['refresh'] for r in a),
            airtime_attempt_us=sum(r['network']['airtime_attempt_us'] for r in a),
            collided=sum(r['network']['collided'] for r in a),
            rejected=sum(r['network']['rejected'] for r in a),
            replaced=sum(r['network']['replaced'] for r in a),
            coalesced=sum(r['network']['coalesced'] for r in a),
            pending=sum(r['network']['pending'] for r in a),
            cache_applied=sum(r['delivery_metrics']['cache_applied'] for r in a),
            cache_unchanged=sum(r['delivery_metrics']['cache_unchanged'] for r in a))
    for policy in ('fifo','latest_state'):
        a=[r for r in replays if r['policy']==policy]
        detailed=[load(BASE/'20261026-01-replay'/r['case_id']/'result.json') for r in a]
        summary['replay_groups'][policy]=dict(n=len(a),
            demanded=sum(r['demanded'] for r in a),delivered=sum(r['delivered'] for r in a),
            collided=sum(r['collided'] for r in a),replaced=sum(r['replaced'] for r in a),
            rejected=sum(r['dropped'] for r in a),application_bytes=sum(r['application_bytes'] for r in a),
            airtime_attempt_us=sum(r['airtime_attempt_us'] for r in a),
            channel_busy_us=sum(r['channel_busy_us'] for r in a),
            pending_at_window=sum(r['pending_at_window'] for r in a),
            busy_fraction_at_window=bounds([r['window_stats']['channel_busy_us']/(r['reference_window_model']*2e7) for r in detailed]),
            queue_p95_seconds=bounds([r['drained_stats']['latency_p95_seconds'] for r in detailed]),
            drain_after_window_seconds=bounds([r['drain_after_window_seconds'] for r in a]))
    for seed in (5,6):
        for n in (9,18,36):
            a={r['condition']:r for r in tasks if r['seed']==seed and r['agents']==n}
            summary['paired_cases'].append(dict(seed=seed,agents=n,tasks=a['event_fifo']['tasks'],
                instant=a['event_fifo']['instant_reference']['makespan_return'],
                makespan={k:r['makespan_return'] for k,r in a.items()},
                ratios={k:r['makespan_to_instant_ratio'] for k,r in a.items()},
                tx_us_per_task={k:r['network']['airtime_attempt_us']/r['completed'] for k,r in a.items()}))
    output.write_bytes((json.dumps(summary,indent=2)+'\n').encode())
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()
