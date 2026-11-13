"""Plots of normalized, already-analyzed E2 software-simulation metrics."""
from io import StringIO
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np

COLORS={'fixed':'#0072B2','replan':'#D55E00'}
NAMES={'fixed':'Fixed initial table','replan':'Observed MID replan'}

def generate(data,out):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':24,'axes.labelsize':24,'svg.fonttype':'none','pdf.fonttype':42,'axes.unicode_minus':False})
    keys=sorted({(r['scenario_id'],r['seed']) for r in data['runs']})
    for sid,seed in keys:
        sc=next(s for s in data['scenarios'] if s['id']==sid)
        runs=[r for r in data['runs'] if r['scenario_id']==sid and r['seed']==seed]
        for direction in [0,1]:
            if not any((r.get('metrics') or {}).get('seconds') for r in runs):continue
            fig,ax=plt.subplots(figsize=(18,6),layout='constrained')
            maximum=512
            for arm in ['fixed','replan']:
                run=next((r for r in runs if r['arm']==arm),None)
                if not run:continue
                rows=sorted((s for s in (run.get('metrics') or {}).get('seconds',[]) if s['direction']==direction),key=lambda s:s['second'])
                x=[s['second'] for s in rows];y=[s['goodput_bps'] if s['goodput_bps'] is not None else np.nan for s in rows]
                maximum=max([maximum,*[s['goodput_bps'] for s in rows if s['goodput_bps'] is not None]])
                if x:ax.step(x+[x[-1]+1],y+[y[-1]],where='post',color=COLORS[arm],linestyle='--' if arm=='fixed' else '-',lw=3.6,label=NAMES[arm])
            for region in sc['partitions']:
                if region['direction']==direction:ax.axvspan(region['start_s'],region['end_s'],facecolor='#eeeeee',hatch='///',edgecolor='#c3c3c3',lw=0,zorder=-5)
            ax.set_xlim(0,60);ax.set_ylim(-maximum*.04,maximum*1.16);ax.set_xticks([0,20,40,60]);ax.set_ylabel('Unique payload goodput (bit/s)');ax.set_xlabel('Simulated time (s)')
            ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color='#e3e8ed',lw=1)
            ax.legend(loc='upper center',bbox_to_anchor=(.5,1.22),ncols=2,frameon=False,fontsize=24)
            stream=StringIO();fig.savefig(stream,format='svg');svg=stream.getvalue();svg=svg[svg.index('<svg'):]
            data['plots'][f'{sid}|{seed}|{direction}']={'svg':svg}
            plt.close(fig)
    active=[sc for sc in data['scenarios'] if any(r['scenario_id']==sc['id'] for r in data['runs'])]
    if not active:return
    complete_E2=all(r.get('metrics') for r in data['runs'])
    fig,axes=plt.subplots(1,len(active),figsize=(180/25.4*3,8),layout='constrained',squeeze=False)
    for ax,sc in zip(axes[0],active):
        for i,seed in enumerate(sc['seeds']):
            values={}
            for arm in ['fixed','replan']:
                run=next((r for r in data['runs'] if r['scenario_id']==sc['id'] and r['seed']==seed and r['arm']==arm),None)
                if not run:continue
                dirs=(run.get('metrics') or {}).get('directions',[])
                if complete_E2 and dirs and not any(d.get('delivered') is None for d in dirs):value=sum(d['delivered'] for d in dirs)
                else:value=run['engine_summary'].get('destination_unique_before60')
                if value is None:continue
                values[arm]=value
                ax.scatter(i+(-.12 if arm=='fixed' else .12),values[arm],s=100,marker='o' if arm=='fixed' else 's',color=COLORS[arm],label=NAMES[arm] if i==0 else None,zorder=3)
            if len(values)==2:ax.plot([i-.12,i+.12],[values['fixed'],values['replan']],color='#b5c2ce',lw=2,zorder=1)
        ax.set_xticks(range(len(sc['seeds'])),[str(s) for s in sc['seeds']]);ax.set_ylim(0,250);ax.set_yticks([0,80,160,240]);ax.set_xlabel(sc['id']+' / paired seed');ax.set_ylabel('Unique destination deliveries / 240');ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color='#e3e8ed',lw=1)
    handles,labels=axes[0,0].get_legend_handles_labels()
    if handles:fig.legend(handles,labels,loc='outside upper center',ncols=2,frameon=False,fontsize=24)
    stem='paired-delivery' if complete_E2 else 'engine-paired-delivery'
    for suffix in ['pdf','svg','png']:
        name=stem+'.'+suffix;fig.savefig(out/name,dpi=100);data['exports'].append({'path':name,'label':suffix.upper()+(' E2配对交付图' if complete_E2 else ' E1引擎汇总配对图（待E2）')})
    plt.close(fig)
