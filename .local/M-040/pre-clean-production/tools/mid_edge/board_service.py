"""A named local-board instance using a registered stable USB path."""
import argparse
import json
from pathlib import Path
import re
import signal
import threading
from .linux_service import run,Rejected
from .client import EdgeError


def validate_config(config):
    required={'port','id_path','interface','vid','pid','node_id','baud','http_port','start_policy'}
    if not isinstance(config,dict) or set(config)!=required:raise ValueError('exact board config fields required: '+','.join(sorted(required)))
    for name,pattern in [('node_id',r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}'),('id_path',r'[A-Za-z0-9_:./-]{8,200}'),('interface',r'[0-9a-f]{2}'),('vid',r'[0-9a-f]{4}'),('pid',r'[0-9a-f]{4}')]:
        if not isinstance(config[name],str) or not re.fullmatch(pattern,config[name]):raise ValueError('invalid registered '+name)
    if type(config['baud']) is not int or config['baud'] not in (115200,460800):raise ValueError('explicit firmware baud required')
    if type(config['http_port']) is not int or not 1024<=config['http_port']<=65535:raise ValueError('unprivileged localhost port required')
    if config['start_policy'] not in ('observe','saved'):raise ValueError('explicit observe/saved start_policy required')
    return config


def resolve_device(config):
    port=config.get('port')
    if not isinstance(port,str) or not port.startswith(('/dev/serial/by-path/','/dev/serial/by-id/')):
        raise ValueError('registered /dev/serial/by-path or by-id path required')
    device=str(Path(port).resolve(strict=True))
    if not re.fullmatch(r'/dev/tty(?:USB|ACM)[0-9]+',device):raise ValueError('stable path must resolve to a USB/ACM tty')
    return device


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path)
    p.add_argument('--state',required=True,type=Path);a=p.parse_args()
    try:config=validate_config(json.loads(a.config.read_text(encoding='utf-8')))
    except ValueError as exc:p.error(str(exc))
    stop=threading.Event()
    signal.signal(signal.SIGINT,lambda *_:stop.set());signal.signal(signal.SIGTERM,lambda *_:stop.set())
    try:return run(config,resolve_device(config),stop=stop,state=a.state)
    except Rejected as exc:print(json.dumps(dict(error=str(exc))));return 78
    except (EdgeError,OSError) as exc:print(json.dumps(dict(error=str(exc))));return 1


if __name__=='__main__':raise SystemExit(main())
