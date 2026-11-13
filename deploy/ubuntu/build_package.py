"""Build a pure Python installable wheel from selected runtime sources, offline."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]
VERSION='0.4.0'


def build(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    files={};sources={}
    def add(source,name=None):
        raw=source.read_bytes();name=name or source.relative_to(ROOT).as_posix()
        files[name]=raw;sources[source.relative_to(ROOT).as_posix()]=hashlib.sha256(raw).hexdigest()
    for source in sorted((ROOT/'tools/mid_edge').glob('*.py')):
        if not source.name.startswith(('test_','hostcheck')):add(source)
    add(ROOT/'firmware/mid_baseline/field_agent/lora_ref/decoder.py','tools/mid_edge/_lora_decoder.py')
    add(ROOT/'tools/mid_sim_console/local_edge.py')
    for source in sorted((ROOT/'tools/mid_sim_console/edge_assets').rglob('*')):
        if source.is_file():add(source)
    for name in ('index.html','workbench.js','sender.js','route-view.js','neighbors.js'):
        source=ROOT/'research/agent_native_network/mid_sim_console'/name
        if source.is_file():add(source)
    files['tools/mid_edge/PACKAGE_SOURCES.json']=json.dumps(sources,indent=2).encode()
    dist=f'mid_edge-{VERSION}.dist-info'
    files[dist+'/METADATA']=(f'Metadata-Version: 2.1\nName: mid-edge\nVersion: {VERSION}\nSummary: Local MID board Wi-Fi business and LoRa reference control\nRequires-Python: >=3.10\nRequires-Dist: pyserial>=3.5\n\nSingle local serial owner; no host radio routing.\n').encode()
    files[dist+'/WHEEL']=b'Wheel-Version: 1.0\nGenerator: mid-edge-offline-builder\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    files[dist+'/entry_points.txt']=b'[console_scripts]\nmid-edge = tools.mid_edge.__main__:main\nmid-edge-board = tools.mid_edge.board_service:main\n'
    record=io.StringIO(newline='');writer=csv.writer(record,lineterminator='\n')
    for name,raw in sorted(files.items()):
        digest=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
        writer.writerow([name,'sha256='+digest,len(raw)])
    writer.writerow([dist+'/RECORD','','']);files[dist+'/RECORD']=record.getvalue().encode()
    wheel=output/f'mid_edge-{VERSION}-py3-none-any.whl'
    with zipfile.ZipFile(wheel,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(files.items()):archive.writestr(name,raw)
    (output/'SOURCES.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
    (output/'WHEEL.json').write_text(json.dumps(dict(wheel=wheel.name,sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),tag='py3-none-any',hardware_tested=False),indent=2),encoding='utf-8')
    for name in ('RASPBERRY_PI_LORA.md','board.example.json','mid-edge-board@.service'):
        shutil.copyfile(ROOT/'deploy/ubuntu'/name,output/name)
    return wheel


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    print(build(p.parse_args().output))
