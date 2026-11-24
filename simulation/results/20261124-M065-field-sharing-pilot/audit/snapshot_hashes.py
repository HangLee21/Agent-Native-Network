"""Record hashes of reviewed evidence without copying or modifying source files."""
import hashlib,json
from pathlib import Path
root=Path.cwd();src=root/'simulation/outputs/E1-033/20261124-01-pilot/results';out=Path(__file__).resolve().parent
files=[src/'RUN_MANIFEST.json',src/'config.json',src/'summary.csv',src/'paired_differences.csv',src/'changed_examples.json']
files.extend(sorted(p for p in src.glob('group-*/*/*') if p.is_file()))
values={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out/'SAVED_HASHES.json').write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf8')
print('recorded',len(values),'evidence file hashes')
