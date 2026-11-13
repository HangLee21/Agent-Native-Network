"""Plot only E2's existing metrics; do not read raw logs or re-run analysis."""
from io import StringIO
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np

COLORS = {'fixed': '#0072B2', 'replan': '#D55E00'}

def event_seconds(run, name):
    result = []
    for a in run['annotations']:
        if a['name'] == name:
            ns = a.get('original_host_ns') or a.get('raw_source', {}).get('original_host_ns') or a['host_monotonic_ns']
            result.append((ns-run['display_t0_ns'])/1e9)
    return result

def panel(ax, runs, direction, fonts=24):
    for arm in ['fixed', 'replan']:
        run = next((r for r in runs if r['arm'] == arm), None)
        if not run:
            continue
        rows = sorted((s for s in run['seconds'] if s['direction'] == direction), key=lambda s:s['second'])
        x = [s['second'] for s in rows]
        y = [s['goodput_bps'] if s['goodput_bps'] is not None else np.nan for s in rows]
        if x:
            ax.step(x+[x[-1]+1], y+[y[-1]], where='post', color=COLORS[arm], lw=3.5, linestyle='--' if arm=='fixed' else '-', label='Fixed table' if arm=='fixed' else 'On-site replan')
        unknown = [s['second'] for s in rows if s['goodput_bps'] is None]
        if unknown:
            # All null windows remain absent from the curve. Hatching identifies whose capture is missing.
            for second in unknown:
                ax.axvspan(second, second+1, facecolor='#eeeeee', edgecolor='#bbbbbb', hatch='///', lw=0, zorder=-5)
            ax.text((min(unknown)+60)/2, 150, f'{arm}: unknown', ha='center', fontsize=fonts, color='#666666')
        if arm == 'replan':
            starts, ends = event_seconds(run,'solve_start'), event_seconds(run,'solve_end')
            if starts and ends:
                ax.axvspan(starts[0], ends[0], color='#f1d7be', alpha=.6, zorder=-2)
            retired = event_seconds(run,'retire_effective')
            if retired:
                ax.axvline(retired[0], color='#555555', lw=2, linestyle=':')
    ax.set_xlim(0,60); ax.set_ylim(-25,600)
    ax.set_xticks([0,20,40,60]); ax.set_yticks([0,256,512])
    ax.tick_params(labelsize=fonts)
    ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y',color='#dfe4e9',lw=1)

def generate(data, directory):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':24,'axes.labelsize':24,'pdf.fonttype':42,'svg.fonttype':'none','axes.unicode_minus':False})
    pairs = sorted({r['pair_id'] for r in data['runs']})
    for pair in pairs:
        runs=[r for r in data['runs'] if r['pair_id']==pair]
        for direction in [0,1]:
            fig, ax=plt.subplots(figsize=(18,6),layout='constrained')
            panel(ax,runs,direction)
            ax.set_xlabel('Host observation time since business start (s)');ax.set_ylabel('Payload goodput (bit/s)')
            ax.legend(loc='upper center',bbox_to_anchor=(.5,1.2),ncols=2,frameon=False,fontsize=24)
            fig.canvas.draw();pos=ax.get_position()
            stream=StringIO();fig.savefig(stream,format='svg')
            svg=stream.getvalue();svg=svg[svg.index('<svg'):]
            data['plots'][f'{pair}-{direction}']={'svg':svg,'bounds':[pos.x0,1-pos.y1,pos.width,pos.height]}
            plt.close(fig)
    fig, axes=plt.subplots(len(pairs),2,figsize=(180/25.4*3,4.6*len(pairs)),layout='constrained',squeeze=False)
    for row,pair in enumerate(pairs):
        runs=[r for r in data['runs'] if r['pair_id']==pair]
        for direction in [0,1]:
            ax=axes[row,direction];panel(ax,runs,direction)
            ax.set_xlabel(f'Pair {pair} / '+('A to B' if direction==0 else 'B to A')+' / host time (s)')
            ax.set_ylabel('Payload goodput (bit/s)')
    handles, labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='outside upper center',ncols=2,frameon=False,fontsize=26)
    for suffix in ['pdf','svg','png']:
        fig.savefig(directory/f'paired-service.{suffix}',dpi=90 if suffix=='png' else 150)
    plt.close(fig)
