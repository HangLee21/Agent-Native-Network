"""Small SVG curve of a numeric CSV; blank rows are omitted."""
import argparse,csv,html
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--csv',required=True);p.add_argument('--x',required=True);p.add_argument('--y',required=True);p.add_argument('--output',required=True);a=p.parse_args()
with open(a.csv,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
points=[(float(r[a.x]),float(r[a.y])) for r in rows if r.get(a.x) and r.get(a.y)]
if not points:raise ValueError('no numeric points')
points.sort();xs=[v[0] for v in points];ys=[v[1] for v in points];xmin,xmax=min(xs),max(xs);ymin,ymax=min(ys),max(ys)
coords=' '.join(f'{60+500*(x-xmin)/(xmax-xmin or 1):.2f},{260-200*(y-ymin)/(ymax-ymin or 1):.2f}' for x,y in points)
svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="620" height="320"><rect width="100%" height="100%" fill="white"/><path d="M60 30 V260 H580" stroke="black" fill="none"/><polyline points="{coords}" fill="none" stroke="#1765aa" stroke-width="2"/><text x="260" y="300">{html.escape(a.x)} ({xmin:g}–{xmax:g})</text><text x="65" y="18">{html.escape(a.y)} ({ymin:g}–{ymax:g})</text></svg>'
out=Path(a.output)
with out.open('x',encoding='utf-8') as f:f.write(svg)
