"""Pure descriptive statistics for M-021; no engine, solver or hardware imports."""
import math
from statistics import median


def distribution(values):
    values=sorted(v for v in values if v is not None)
    def percentile(q):
        if not values:return None
        at=(len(values)-1)*q;lo=math.floor(at);hi=math.ceil(at)
        return values[lo]+(values[hi]-values[lo])*(at-lo)
    return dict(n=len(values),values=values,median=median(values) if values else None,
                IQR=percentile(.75)-percentile(.25) if values else None,
                min=min(values) if values else None,max=max(values) if values else None)


def recovery(bits,impact_start_s,anchor_s):
    """80% of ten complete pre-impact bins, three complete bins after real loss.

    The anchor is reconnect time for a full partition. No pre-loss stable run is
    counted as recovery when degradation takes time to develop.
    """
    if impact_start_s is None or anchor_s is None:
        return dict(status='unknown',reason='evaluation_anchor_missing')
    before=math.floor(impact_start_s);start=math.ceil(impact_start_s);after_anchor=math.ceil(anchor_s)
    if not 0<=impact_start_s<len(bits) or not impact_start_s<=anchor_s<=len(bits):
        return dict(status='unknown',reason='anchor_outside_run')
    baseline_bins=bits[max(0,before-10):before]
    if len(baseline_bins)!=10 or any(v is None for v in baseline_bins):
        return dict(status='unknown',reason='incomplete_pre_impact_baseline')
    baseline=sum(baseline_bins)/10
    if baseline<=0:return dict(status='not_assessable',reason='zero_baseline',baseline_bps=baseline)
    threshold=.8*baseline;tail=bits[start:]
    if any(v is None for v in tail):
        return dict(status='unknown',reason='incomplete_post_impact_coverage',baseline_bps=baseline)
    low=[i for i in range(start,len(bits)) if bits[i]<threshold]
    common=dict(baseline_bps=baseline,threshold_bps=threshold,impact_start_s=impact_start_s,recovery_anchor_s=anchor_s)
    if not low and all(v>=threshold for v in baseline_bins[-3:]):
        return dict(common,status='no_interruption',recovery_s=0,elapsed_from_impact_s=0)
    if not low:
        return dict(common,status='not_assessable',reason='unstable_pre_impact_service')
    first_low=low[0]
    for i in range(max(first_low+1,after_anchor),len(bits)-2):
        if all(v>=threshold for v in bits[i:i+3]):
            return dict(common,status='recovered',first_below_threshold_s=first_low,
                        recovery_window_end_s=i+3,recovery_s=i+3-anchor_s,
                        elapsed_from_impact_s=i+3-impact_start_s)
    return dict(common,status='right_censored',recovery_s=None,censor_s=len(bits)-anchor_s,
                first_below_threshold_s=first_low)


def longest_unreceived(rows,known,interval_s=.5):
    if not known:return dict(packets=None,planned_time_s=None,status='unknown')
    longest=current=0
    for row in sorted(rows,key=lambda r:r['slot']):
        current=0 if row['delivered'] else current+1;longest=max(longest,current)
    return dict(packets=longest,planned_time_s=longest*interval_s,
                scope='planned source slots without destination event, not physical RF outage')


def directed_path(nodes,edges,src,dst):
    """Optimistic positive-service/probability path, never a policy observation."""
    if src not in nodes or dst not in nodes:return None
    todo=[[src]];seen={src}
    for path in todo:
        if path[-1]==dst:return path
        for a,b in sorted(edges):
            if a==path[-1] and b in nodes and b not in seen:
                seen.add(b);todo.append([*path,b])
    return None
