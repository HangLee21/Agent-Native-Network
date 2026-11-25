"""H-operated bounded serial publication, never auto-selects ports or flashes."""
import argparse
import json
import time
from pathlib import Path
from bridge import pack, mac


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('update')
    p.add_argument('--port', required=True)
    p.add_argument('--publisher', required=True)
    p.add_argument('--boot', required=True, type=int)
    p.add_argument('--first-seq', required=True, type=int)
    p.add_argument('--count', type=int, default=1)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    if not 1 <= args.count <= 60 or not 1 <= args.first_seq <= 0xffffffff-args.count+1:
        p.error('count 1..60; no sequence wrap')
    update = json.loads(Path(args.update).read_text(encoding='utf-8'))
    frames = [pack(update, args.publisher, args.boot, args.first_seq+i) for i in range(args.count)]
    import serial
    # Exclusive log creation before any port action. No automatic start/stop or routing choice.
    with Path(args.output).open('x', encoding='utf-8') as log:
        port=serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=1, exclusive=True)
        port.dtr=False
        port.rts=False
        port.port=args.port
        with port:
            def send(obj):
                data=(json.dumps(obj,separators=(',',':'))+'\n').encode('ascii')
                if port.write(data)!=len(data):
                    raise IOError('short serial write')
                log.write(json.dumps(dict(direction='tx',at=time.monotonic(),command=obj))+'\n');log.flush()
            nonce='publish-identity-check'
            send(dict(schema='mid.serial.v1',cmd='info',nonce=nonce))
            deadline=time.monotonic()+3
            identity=None
            while time.monotonic()<deadline:
                raw=port.readline()
                if not raw:continue
                log.write(json.dumps(dict(direction='rx',at=time.monotonic(),line=raw.decode('utf-8',errors='replace')))+'\n')
                try:j=json.loads(raw)
                except (ValueError,UnicodeDecodeError):continue
                if j.get('schema')=='mid.serial.v1' and j.get('event')=='command_result' and j.get('nonce')==nonce:
                    identity=j;break
            if not identity or not identity.get('ok') or mac(identity['node_id'])!=mac(args.publisher) or identity['boot_id']!=args.boot:
                raise ValueError('bound entry identity/boot mismatch; no config sent')
            if identity.get('mode') not in ('wait_config','active') or not identity.get('radio'):
                raise ValueError('H must explicitly start all bound nodes first')
            start=time.monotonic()
            for i,frame in enumerate(frames):
                target=start+i
                while time.monotonic()<target:
                    raw=port.readline()
                    if raw:log.write(json.dumps(dict(direction='rx',at=time.monotonic(),line=raw.decode('utf-8',errors='replace')))+'\n')
                send(dict(schema='mid.serial.v1',cmd='config',nonce=f'publish-{args.first_seq+i}',frame_hex=frame.hex()))
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                raw=port.readline()
                if raw:log.write(json.dumps(dict(direction='rx',at=time.monotonic(),line=raw.decode('utf-8',errors='replace')))+'\n')
    # Publication does not assert adoption on remote nodes. H owns finally-stop of the scenario.


if __name__=='__main__':
    main()
