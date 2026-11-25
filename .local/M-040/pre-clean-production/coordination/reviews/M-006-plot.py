"""Prepare and plot completed stage summaries; never runs a task policy."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def prepare(inputs, output):
    output.mkdir(parents=True, exist_ok=False)
    rows, provenance = [], []
    for path in inputs:
        summary = read(path)
        manifest_path = path.parent / 'manifest.json'
        if not manifest_path.exists():
            manifest_path = manifest_path.with_suffix('.json.gz')
        manifest = read(manifest_path)
        assert len(summary['cases']) == summary['planned']
        wait = manifest.get('task_wait', 200.)
        provenance.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for r in summary['cases']:
            assert r['process_exit_code'] == 0 and r['status'] in ('success', 'horizon_incomplete')
            n = r['network']
            rows.append(dict(tasks=r['tasks'], seed=r['seed'], condition=r['condition'],
                             task_wait=wait, success=int(r['success']), status=r['status'],
                             completion_fraction=r['completion_fraction'],
                             makespan_return=r['makespan_return'], capped_makespan=r['capped_makespan'],
                             messages=n['demanded'], application_bytes=n['demand_application_bytes'],
                             delivered=n['delivered'], pending=n['pending'], dropped=n['dropped'],
                             latency_p95=n['latency_p95'], initial_sha256=r['initial_sha256'],
                             source_case=str(path.parent / r['case'])))
    keys = [(r['tasks'], r['seed'], r['condition'], r['task_wait']) for r in rows]
    assert len(set(keys)) == len(keys)
    with (output / 'source_data.csv').open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    groups = {}
    for r in rows:
        groups.setdefault((r['tasks'], r['condition'], r['task_wait']), []).append(r)
    profile = []
    for (tasks, condition, wait), values in sorted(groups.items()):
        good = [r for r in values if r['success']]
        profile.append(dict(tasks=tasks, condition=condition, task_wait=wait, n=len(values),
                            success=len(good), mean_completion=sum(r['completion_fraction'] for r in values)/len(values),
                            successful_mean_return=sum(r['makespan_return'] for r in good)/len(good) if good else None,
                            capped_mean=sum(r['capped_makespan'] for r in values)/len(values),
                            mean_application_bytes=sum(r['application_bytes'] for r in values)/len(values),
                            total_dropped=sum(r['dropped'] for r in values)))
    (output / 'profile.json').write_text(json.dumps(dict(sources=provenance, rows=len(rows),
        missing_return_times=sum(not r['success'] for r in rows), groups=profile), indent=2)+'\n', encoding='utf-8')
    print(json.dumps(profile, indent=2))


def plot(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import ScalarFormatter
    import numpy as np
    with (output/'source_data.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ('tasks', 'seed', 'success'):
            r[k] = int(r[k])
        for k in ('task_wait', 'capped_makespan'):
            r[k] = float(r[k])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':24,'axes.labelsize':27,
                        'xtick.labelsize':24,'ytick.labelsize':24,'legend.fontsize':24,
                        'axes.linewidth':1.5,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig, axs = plt.subplots(2, 2, figsize=(21, 16.5), sharey=True)
    colors = ['#0072B2','#D55E00','#009E73','#CC79A7','#222222']
    markers = ['o','s','^','D','v']
    panels = [(15,200.,['instant','delay0.5','delay2'],[0.,.5,2.],
               'Fixed delay (simulation units)\n(a) 15 tasks; waiting limit 200'),
              (20,200.,['instant','delay0.5','delay2'],[0.,.5,2.],
               'Fixed delay (simulation units)\n(b) 20 tasks; waiting limit 200'),
              (15,200.,['fifo2048','fifo4096','fifo8192'],[2048.,4096.,8192.],
               'FIFO rate (application bytes / time unit)\n(c) 15 tasks; waiting limit 200'),
              (15,20.,['instant','delay0.5'],[0.,.5],
               'Fixed delay (simulation units)\n(d) 15 tasks; waiting limit 20')]
    for ax, (tasks, wait, conditions, xs, label) in zip(axs.flat, panels):
        for seed in range(5):
            rr = [next(r for r in rows if r['tasks']==tasks and r['task_wait']==wait and
                       r['condition']==cond and r['seed']==seed) for cond in conditions]
            yy = [r['capped_makespan'] if r['success'] else np.nan for r in rr]
            ax.plot(xs, yy, color=colors[seed], marker=markers[seed], markersize=12,
                    linewidth=2., alpha=.85, label=f'Seed {seed}')
            for x, r in zip(xs, rr):
                if not r['success']:
                    # Fixed visual offset exposes coincident censored cases; values stay in CSV.
                    jitter = (seed-2) * (max(xs)-min(xs)) * .012
                    ax.plot(x+jitter, 200., marker='x', color=colors[seed], markersize=16,
                            markeredgewidth=3., linestyle='none')
        ax.axhline(200., color='#777777', linestyle=':', linewidth=1.8)
        ax.set_yscale('log'); ax.set_ylim(10., 250.)
        ax.set_yticks([10,20,50,100,200]); ax.yaxis.set_major_formatter(ScalarFormatter())
        ax.minorticks_off(); ax.grid(axis='y', color='#DDDDDD', linewidth=1.)
        if conditions[0].startswith('fifo'):
            ax.set_xscale('log', base=2)
        ax.set_xticks(xs); ax.set_xticklabels([f'{x:g}' for x in xs])
        ax.set_xlabel(label)
        ax.spines[['top','right']].set_visible(False)
    for ax in axs[:,0]:
        ax.set_ylabel('Return time / timeout H\n(simulation units, log scale)')
    handles = [Line2D([0],[0],color=colors[s],marker=markers[s],markersize=12,linewidth=2,label=f'Seed {s}') for s in range(5)]
    handles.append(Line2D([0],[0],color='#555555',marker='x',markersize=14,linestyle='none',label='Incomplete at H=200'))
    fig.legend(handles=handles, loc='upper center', ncol=3, frameon=False, bbox_to_anchor=(.52,.99))
    fig.subplots_adjust(left=.12,right=.98,bottom=.10,top=.88,wspace=.18,hspace=.40)
    for suffix in ('pdf','svg','png'):
        target=output/f'figure.{suffix}'
        if target.exists():
            raise FileExistsError(target)
        fig.savefig(target, dpi=100 if suffix=='png' else 300, facecolor='white')
        if suffix == 'svg':
            # Matplotlib emits trailing path whitespace; normalize formatting only.
            target.write_text('\n'.join(line.rstrip() for line in target.read_text(encoding='utf-8').splitlines())+'\n', encoding='utf-8')
    fig.savefig(output/'preview_final_width.png', dpi=60, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--input',type=Path,action='append')
    p.add_argument('--plot',action='store_true')
    args=p.parse_args()
    if args.plot:
        plot(args.output)
    else:
        prepare(args.input,args.output)
