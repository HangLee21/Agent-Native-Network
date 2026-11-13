"""Combine already analyzed runs; no recapture, solver, serial or plotting."""
import argparse,json
from pathlib import Path
import analysis
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',action='append',required=True);p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output).resolve();root=Path(__file__).resolve().parents[4]
 if out.exists() or not out.is_relative_to(root/'simulation/outputs/E2-017'):raise ValueError('new E2-017 output required')
 result=analysis.pairs([analysis.strict(Path(p).read_bytes()) for p in a.run]);result['source_runs']=[dict(path=str(Path(p).resolve()),sha256=analysis.sha(p)) for p in a.run];out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
if __name__=='__main__':main()
