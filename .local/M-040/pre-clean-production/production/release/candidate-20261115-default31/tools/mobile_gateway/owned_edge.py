"""H lifecycle wrapper for the existing E2 local owner; never changes board configuration."""
import argparse
import json
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer

from tools.mid_edge.client import Edge
from tools.mid_sim_console.local_edge import Handler, LocalEdge


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial-port',required=True)
    p.add_argument('--node-id',required=True)
    p.add_argument('--build',required=True)
    p.add_argument('--boot',type=int,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--stop-file',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    with Edge(args.serial_port,args.node_id,460800,log=args.output/'native.jsonl') as edge:
        info=edge.identify()
        if info['build_id']!=args.build or info['boot_id']!=args.boot or info.get('deployment_mode')!='autonomous' or not info.get('radio'):
            raise RuntimeError('fresh identity/build/boot/active autonomous state differs; no config command sent')
        app=LocalEdge(edge,args.output/'requests.json')
        with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
            server.app=app
            worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.1},daemon=True)
            worker.start()
            ready=dict(port=server.server_port,serial_port=args.serial_port,node_id=args.node_id,info=info,pid=__import__('os').getpid())
            (args.output/'ready.json').write_text(json.dumps(ready,indent=2),encoding='utf-8')
            print(json.dumps(ready),flush=True)
            try:
                while not args.stop_file.exists():
                    threading.Event().wait(.1)
            finally:
                server.shutdown()
                worker.join(3)
                app.stopping=True
                app.thread.join(2)
                final=edge.info()
                (args.output/'final.json').write_text(json.dumps(dict(info=final,stats=edge.command('stats'),radio_or_config_commands=0),indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
