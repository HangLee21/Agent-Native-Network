"""Small radio primitives; values are explicit hypotheses, not measurements."""
import math

def duration_us(length, rate_mbps, preamble_us, unicast):
    frame = preamble_us + math.ceil((length + 43) * 8 / rate_mbps)
    ack = preamble_us + 112 + 10 if unicast else 0
    return frame, ack

def mark_interference(new, existing, adjacency):
    """Apply overlap to both transmissions using receiver-local geometry."""
    i = new['src']
    for other in existing:
        if other['end'] <= new['start']:
            continue
        for receiver in new['targets']:
            if other['src'] == receiver or other['src'] in adjacency[receiver]:
                new['collided'].add(receiver)
        for receiver in other['targets']:
            if i == receiver or i in adjacency[receiver]:
                other['collided'].add(receiver)

def self_check():
    from motion import positions, scale_initial_separation
    assert duration_us(60, 1, 192, False) == (1016, 0)
    assert duration_us(60, 1, 192, True) == (1016, 314)
    # 0 and 2 cannot hear each other but both can reach 1.
    adj = [{1}, {0, 2}, {1}]
    left = dict(src=0, start=0, end=1000, targets={1}, collided=set())
    right = dict(src=2, start=100, end=1100, targets={1}, collided=set())
    mark_interference(right, [left], adj)
    assert left['collided'] == {1} and right['collided'] == {1}
    # A later frame cannot collide with an already finished frame.
    later = dict(src=2, start=1000, end=2000, targets={1}, collided=set())
    old = dict(src=0, start=0, end=1000, targets={1}, collided=set())
    mark_interference(later, [old], adj)
    assert not later['collided'] and not old['collided']
    # Receiver transmission during a reception is half-duplex interference.
    old = dict(src=0, start=0, end=1000, targets={1}, collided=set())
    tx = dict(src=1, start=100, end=1100, targets={2}, collided=set())
    mark_interference(tx, [old], adj)
    assert 1 in old['collided']
    for mode in ('formation', 'crossing', 'reorganize'):
        initial=positions(mode,25,0,0);a=positions(mode,25,0,1);b=positions(mode,25,0,2)
        sa=scale_initial_separation(a,initial,1.6);sb=scale_initial_separation(b,initial,1.6)
        for i in range(len(a)):
            assert all(abs((b[i][j]-a[i][j])-(sb[i][j]-sa[i][j])) < 1e-9 for j in (0,1))
    print('PASS timing, hidden sender overlap, nonoverlap and half-duplex')

if __name__ == '__main__':
    self_check()
