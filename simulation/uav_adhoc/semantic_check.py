"""Small deterministic host-core check, without a radio model."""
import ctypes as C
import sys
from pathlib import Path
from engine import B, U, Core

core = Core(Path(sys.argv[1]).resolve(), 0)
l = core.lib
try:
    # Each endpoint hears a hello and returns its real firmware ACK.
    for source, target in ((0, 1), (1, 0)):
        hello = B()
        size = l.host_hello(core.nodes[source], hello)
        assert size > 0
        reply = B()
        rsize = l.host_nd(core.nodes[target], source, hello, size, 100, reply)
        assert rsize > 0
        assert l.host_nd(core.nodes[source], target, reply, rsize, 125, B()) == 0
    for node in core.nodes[:2]:
        l.host_sync(node, 150)
        l.host_tick(node, 150)
    data = b'known-payload'
    payload = (C.c_ubyte * len(data)).from_buffer_copy(data)
    assert l.host_submit(core.nodes[0], 1, 42, payload, len(data), 151) == 0
    raw, dst, kind = B(), C.c_int(), C.c_int()
    length = l.host_next(core.nodes[0], 151, raw, C.byref(dst), C.byref(kind))
    assert length > 0 and dst.value == 1 and kind.value == 3
    assert l.host_receive(core.nodes[1], 0, raw, length, 176) >= 0
    l.host_result(core.nodes[0], 1, 176)
    event, received = U(), B()
    found = False
    while l.host_event(core.nodes[1], event, received):
        if event[0] == 6:
            assert (event[2], event[3], event[4], event[5]) == (0, 1, 42, 1)
            assert bytes(received[:event[7]]) == data
            found = True
    assert found
    print('PASS: hello/ACK, peer sync, direct payload and destination identity')
finally:
    core.close()
