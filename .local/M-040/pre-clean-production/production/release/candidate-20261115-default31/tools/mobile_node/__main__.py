"""python -m tools.mobile_node node|agent --help"""
import argparse
import hashlib
import math
import signal
import threading
import time
import uuid
from pathlib import Path
from .edge import MobileEdge
from .node import Node
from .providers import ExternalGPS, GPSD, fake_GPS_function
from .reporting import GatewayReporter, ReportQueue
from .traffic import Journal, fake_agent_function


def parser():
    p = argparse.ArgumentParser(description='Local mobile node and independent business agent')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('node', 'agent'):
        q = sub.add_parser(name)
        q.add_argument('--edge-port', type=int, default=8780)
        q.add_argument('--state', required=True, help='Local logs and bounded report queue directory')
        q.add_argument('--seed', type=int, default=1)
        q.add_argument('--duration', type=float, default=0, help='Stop after seconds; 0 runs until Ctrl+C')
        q.add_argument('--interval-min', type=float, default=2)
        q.add_argument('--interval-max', type=float, default=5)
        q.add_argument('--min-bytes', type=int, default=32)
        q.add_argument('--max-bytes', type=int, default=120)
        q.add_argument('--dest', action='append', default=[], help='Repeat for candidate destination MACs; default observed neighbors')
    n = sub.choices['node']
    n.add_argument('--gateway', help='HTTP(S) observation gateway base URL; omit for local logging only')
    n.add_argument('--label', default='')
    n.add_argument('--agent', action='store_true', help='Also start business agent; default telemetry only')
    n.add_argument('--gps', choices=('fake', 'gpsd', 'external', 'none'), default='fake')
    n.add_argument('--gps-function', help='module:function returning fix dict or None')
    n.add_argument('--gpsd-host', default='127.0.0.1')
    n.add_argument('--gpsd-port', type=int, default=2947)
    n.add_argument('--center-lat', type=float, default=30.0)
    n.add_argument('--center-lon', type=float, default=120.0)
    n.add_argument('--width-m', type=float, default=600)
    n.add_argument('--height-m', type=float, default=400)
    n.add_argument('--speed-mps', type=float, default=1.4)
    n.add_argument('--sample-s', type=float, default=1)
    n.add_argument('--report-s', type=float, default=10)
    n.add_argument('--max-age-s', type=float, default=15)
    n.add_argument('--queue-limit', type=int, default=120)
    n.add_argument('--no-position-injection', action='store_true', help='For old firmware: GPS stays in local reports only')
    return p


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    if not math.isfinite(a.duration) or a.duration < 0:
        p.error('--duration must be nonnegative')
    if not .05 <= a.interval_min <= a.interval_max <= 86400 or not 0 <= a.min_bytes <= a.max_bytes <= 160:
        p.error('interval must be 0.05..86400 seconds and payload 0..160 bytes')
    if a.command == 'node' and a.gps == 'external' and not a.gps_function:
        p.error('--gps-function module:function required with external GPS')
    state = Path(a.state)
    state.mkdir(parents=True, exist_ok=True)
    journal = Journal(state / (a.command + '-' + uuid.uuid4().hex + '.jsonl'))
    edge = MobileEdge(a.edge_port)
    stop = threading.Event()
    workers = []
    queue = None
    timer = None
    # Keep signal handlers in the main thread. Worker/test callers own their stop event.
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
    try:
        agent_options = dict(edge=MobileEdge(a.edge_port), journal=journal, stop=stop,
                             seed=a.seed, interval_min=a.interval_min, interval_max=a.interval_max,
                             min_bytes=a.min_bytes, max_bytes=a.max_bytes, dest=a.dest,
                             receive=a.command == 'agent')
        if a.command == 'node':
            # The native identity salts the seed so identical CLI defaults give independent paths.
            own = edge.status()['node_id']
            seed = a.seed + int.from_bytes(hashlib.sha256(own.encode()).digest()[:8], 'big')
            provider = fake_GPS_function(seed=seed, center_lat=a.center_lat, center_lon=a.center_lon,
                                         width_m=a.width_m, height_m=a.height_m, speed_mps=a.speed_mps)
            if a.gps == 'none':
                provider = lambda: None
            elif a.gps == 'gpsd':
                provider = GPSD(a.gpsd_host, a.gpsd_port)
            elif a.gps == 'external':
                provider = ExternalGPS(a.gps_function)
            queue = ReportQueue(state / 'reports.sqlite3', a.queue_limit)
            node = Node(edge, provider, queue, journal, a.label, a.sample_s,
                        a.report_s, a.max_age_s, not a.no_position_injection)
            if a.gateway:
                reporter = GatewayReporter(a.gateway, queue, journal)
                workers.append(threading.Thread(target=reporter.run, args=(stop,), name='gateway-reporter'))
            if a.agent:
                workers.append(threading.Thread(target=fake_agent_function, kwargs=agent_options,
                                                 name='business-agent'))
        if a.duration:
            timer = threading.Timer(a.duration, stop.set)
            timer.start()
        for worker in workers:
            worker.start()
        journal.write('started', command=a.command, options=vars(a), serial_owner=False)
        print(f'{a.command} running; local edge {edge.base}; logs {state.resolve()}', flush=True)
        if a.command == 'node':
            node.run(stop)
        else:
            fake_agent_function(**agent_options)
    finally:
        stop.set()
        if timer:
            timer.cancel()
            timer.join()
        for worker in workers:
            if worker.ident:
                worker.join()
        journal.write('stopped', queue=queue.stats() if queue else None)
        if queue:
            queue.close()
        journal.close()


if __name__ == '__main__':
    main()
