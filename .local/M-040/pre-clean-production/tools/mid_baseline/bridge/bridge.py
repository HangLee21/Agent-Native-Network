"""Offline bridge: NetworkUpdate JSON -> MID config JSON line. Never opens serial."""
import argparse
import json
import math
import struct


def mac(text):
    parts = text.split(':')
    if len(parts) != 6 or any(len(x) != 2 for x in parts):
        raise ValueError('MAC must be xx:xx:xx:xx:xx:xx')
    b = bytes(int(x, 16) for x in parts)
    if b[0] & 1 or b == bytes(6):
        raise ValueError('unicast MAC required')
    return b


def quantize(values):
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('invalid weights')
    total = sum(values)
    if not total:
        return [0]*len(values)
    exact = [65535*x/total for x in values]
    q = [int(x) for x in exact]
    order = sorted(range(len(q)), key=lambda j: (-(exact[j]-q[j]), j))
    for j in order[:65535-sum(q)]:
        q[j] += 1
    return q


def pack(update, publisher, boot, seq):
    if update.get('schema') != 'mid.network_update.v1':
        raise ValueError('schema')
    nodes, flows = update['nodes'], update['flows']
    n, k = len(nodes), len(flows)
    if not 2 <= n <= 5 or not 1 <= k <= 2:
        raise ValueError('node/flow bounds')
    ids = [mac(x) for x in nodes]
    if len(set(ids)) != n or mac(publisher) not in ids:
        raise ValueError('unique nodes and publisher membership required')
    pairs = [(nodes.index(f['src']), nodes.index(f['dst'])) for f in flows]
    if any(s == d for s, d in pairs) or len(set(pairs)) != k:
        raise ValueError('duplicate/invalid flows')
    weights = [[[0.0]*n for _ in nodes] for _ in flows]
    seen = set()
    for row in update['routes']:
        i = nodes.index(row['node'])
        pair = (nodes.index(row['src']), nodes.index(row['dst']))
        f = pairs.index(pair)
        if (f, i) in seen or i == pair[1]:
            raise ValueError('duplicate/destination row')
        seen.add((f, i))
        gseen = set()
        for gateway in row['gateways']:
            j = nodes.index(gateway['node'])
            if j == i or j in gseen:
                raise ValueError('self/duplicate gateway')
            gseen.add(j)
            weights[f][i][j] = float(gateway['weight'])
    body = bytes([n, k])+b''.join(ids)+b''.join(bytes(pair) for pair in pairs)
    body += b''.join(struct.pack('<'+'H'*n, *quantize(row)) for flow in weights for row in flow)
    if type(boot) is not int or type(seq) is not int or not 1 <= boot <= 0xffffffff or not 1 <= seq <= 0xffffffff:
        raise ValueError('nonzero uint32 boot/sequence required')
    frame = struct.pack('<4sBBH6sIIH', b'MID1', 1, 8, len(body), mac(publisher), boot, seq, 0)+body
    if len(frame) > 250:
        raise ValueError('frame too large; fragmentation unsupported')
    return frame


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('update')
    p.add_argument('--publisher', required=True)
    p.add_argument('--boot', required=True, type=int)
    p.add_argument('--seq', required=True, type=int)
    p.add_argument('--nonce', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    from pathlib import Path
    if not 1 <= len(args.nonce) <= 64 or not args.nonce.isascii():
        raise ValueError('nonce')
    update = json.loads(Path(args.update).read_text(encoding='utf-8'))
    frame = pack(update, args.publisher, args.boot, args.seq)
    with Path(args.output).open('x', encoding='utf-8') as f:
        json.dump(dict(schema='mid.serial.v1', cmd='config', nonce=args.nonce, frame_hex=frame.hex()), f)
        f.write('\n')


if __name__ == '__main__':
    main()
