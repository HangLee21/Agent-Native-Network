"""Audit generated LoRa events against independent E2 normalized evaluator."""
import csv,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'uav_adhoc_eval'))
from analyze import analyze

def check(source,output):
    source=Path(source);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    results=[]
    for run in sorted(p for p in source.iterdir() if p.is_dir()):
        summary=json.loads((run/'summary.json').read_text());commands=json.loads((run/'commands.json').read_text())
        with (run/'events.jsonl').open(encoding='utf-8') as f:events=[json.loads(x) for x in f]
        seen=set();received=set();executed=set();acks=set();duplicates=0
        for e in events:
            if e['type']=='offered':
                key=(e['origin'],e['origin_boot'],e['seq'],e['dst']);assert key not in seen;seen.add(key)
            elif e['type']=='delivered':
                key=(e['origin'],e['origin_boot'],e['seq'],e['dst']);assert key in seen and key not in received and e['receiver']==e['dst'];received.add(key)
            elif e['type']=='command_executed':
                key=(e['cmd_id'],e['target']);assert e['executor']==e['target'] and key not in executed;executed.add(key)
            elif e['type']=='command_duplicate':
                assert (e['cmd_id'],e['target']) in executed;duplicates+=1
            elif e['type']=='command_ack_received':
                key=(e['cmd_id'],e['target']);assert key in executed;acks.add(key)
            elif e['type']=='neighbor_received':assert e['generated_at']<=e['t']
        normalized,samples=analyze(dict(events=events))
        assert len(seen)==summary['offered']==normalized['offered']
        assert len(received)==summary['received']==normalized['delivered_unique']
        assert len(executed)==summary['commands_executed']==normalized['commands_executed']
        assert len(acks)==summary['commands_ack_received'] and duplicates==summary['duplicate_receipts']
        assert normalized['duplicate_executions']==0
        with (run/'nodes.csv').open(encoding='utf-8',newline='') as f:nodes=list(csv.DictReader(f))
        assert len(nodes)==30 and sum(int(n['offered']) for n in nodes)==len(seen) and sum(int(n['received']) for n in nodes)==len(received)
        assert len(commands)==summary['commands_issued']
        results.append(dict(run=run.name,offered=len(seen),received=len(received),commands_executed=len(executed),acks=len(acks),duplicate_commands=duplicates,normalized_aoi_samples=len(samples),status='passed'))
    assert len(results)==12
    (output/'audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(dict(runs=len(results),status='passed',duplicate_commands=sum(x['duplicate_commands'] for x in results))))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args();check(a.input,a.output)
