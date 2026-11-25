"""Passive reader for the existing PC HTTP API. No UDP, POST or maintenance writes."""
import argparse
import collections
import copy
import json
from pathlib import Path
import time
from .client import Client


class ObservationReader:
    def __init__(self, port=8791, client=None):
        self.client = client or Client(port)
        self.instance = None
        self.cursor = 0
        self.statuses = {}
        self.records = collections.OrderedDict()
        self.reports = collections.deque(maxlen=32)
        self.counts = collections.Counter()

    def _reset(self, instance):
        self.instance, self.cursor = instance, 0
        self.statuses.clear()
        self.records.clear()
        self.reports.clear()
        self.counts.clear()

    def read(self):
        started = time.time()
        status = self.client.status()
        if status['instance_id'] != self.instance:
            self._reset(status['instance_id'])
        history = self.client.events(self.cursor)
        if history.get('instance_id') != self.instance:
            raise RuntimeError('PC instance changed during read; no sources merged, read again')
        for event in history['events']:
            self.counts[event.get('kind', 'unknown')] += 1
            if event.get('kind') == 'wireless_report':
                self.reports.append(copy.deepcopy(event))
            wrapped = event.get('raw', {})
            if event.get('kind') != 'wireless_status' or wrapped.get('type') != 'wireless_status':
                continue
            raw = wrapped.get('raw', {})
            if raw.get('schema') != 'field.ip.v2' or raw.get('pc_id') != status['pc_id']:
                continue
            node, boot = raw.get('entry_id'), raw.get('entry_boot')
            if not node or type(boot) is not int:
                continue
            received = event['received_at']
            if raw.get('event') == 'field_status':
                self.statuses[(node,boot)] = dict(node_id=node, boot_id=boot,
                    agent_running=raw.get('agent_running'),
                    counts={k:raw[k] for k in ('source_admitted','source_submitted',
                        'destination_received','relay_received','relay_submitted') if k in raw},
                    record_overwritten=raw.get('record_overwritten'),
                    latest_record_cursor=raw.get('latest_record_cursor'),
                    observed_at=received, rf_rows_available='rf_neighbors' in raw or 'neighbors' in raw,
                    position=None, raw=copy.deepcopy(raw))
                while len(self.statuses) > 32:
                    self.statuses.pop(next(iter(self.statuses)))
            elif raw.get('event') == 'record':
                required = ('record_cursor','kind','origin','origin_boot','seq','dst','payload_hex','at_ms')
                if any(k not in raw for k in required):
                    self.counts['incomplete_native_records'] += 1
                    continue
                record = {k:raw[k] for k in required}
                record.update(observer_id=node, observer_boot=boot, segment=raw.get('segment'),
                              observed_at=received, rf_source='unavailable',
                              source='native_RAM_readback_over_IP', raw=copy.deepcopy(raw),
                              payload_scope='FG02_envelope' if raw['payload_hex'].startswith('46473032') else 'board_application',
                              clock_scope='observer_boot_uptime')
                key = node, boot, raw['record_cursor']
                self.records[key] = record
                while len(self.records) > 256:
                    self.records.popitem(last=False)
        self.cursor = history['cursor']
        map_state = self.client.call('/api/v1/state')
        if self.client.status()['instance_id'] != self.instance:
            raise RuntimeError('PC instance changed before State read finished; no mixed snapshot exported')
        now = time.time()
        current = {(row['node_id'],row['boot_id']):row for row in status['entries']}
        native_status = []
        for key, sample in self.statuses.items():
            if key not in current:
                continue  # old observer boot is not a current board sample
            native_status.append(dict(copy.deepcopy(sample),
                readback_age_ms=max(0,int((now-sample['observed_at'])*1000)),
                ip_entry_connected=bool(current[key]['connected']),
                neighbor_scope='not_in_field_status; do_not_infer_RF_edges'))
        records = []
        for (node,boot,_), sample in self.records.items():
            if (node,boot) not in current:
                continue
            sample = copy.deepcopy(sample)
            raw = sample['raw']
            uptime, at = raw.get('entry_uptime_ms'), raw.get('at_ms')
            sample['record_age_lower_bound_ms'] = (max(0,int(uptime-at))+max(0,int((now-sample['observed_at'])*1000))
                if isinstance(uptime,(int,float)) and isinstance(at,(int,float)) and uptime >= at else None)
            records.append(sample)
        return dict(schema='field.readonly.observations.v1', pc_instance_id=self.instance,
                    pc_id=status['pc_id'], pc_session=status['pc_session'],
                    sampled_between=[started,now], entries=copy.deepcopy(status['entries']),
                    native_status=native_status, records=records, native_reports=list(self.reports),
                    map_state=map_state, pc_diagnostics=status.get('telemetry'),
                    observed_event_counts=dict(self.counts), event_cursor=self.cursor,
                    history_truncated=history.get('truncated',False),
                    source='existing_PC_HTTP_API; hardware_provenance_is_in_raw_records',
                    side_effects=dict(http_post=0,udp_writes=0,serial_opens=0,maintenance_control_writes=0),
                    limitations=['IP registration is not an RF edge.',
                                 'field_status and record do not contain last-hop RSSI or a neighbor table.',
                                 'at_ms belongs to the observer board boot; readback time is not packet creation time.',
                                 'This reader neither updates 8791 State nor acquires new board samples.'])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8791)
    p.add_argument('--output',type=Path,help='New JSON file, never overwrites a previous capture')
    a = p.parse_args(argv)
    result = ObservationReader(a.port).read()
    raw = json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open('x',encoding='utf-8') as stream:
            stream.write(raw)
        print(json.dumps(dict(output=str(a.output.resolve()),entries=len(result['entries']),
            native_status=len(result['native_status']),records=len(result['records']),
            native_reports=len(result['native_reports']),map_nodes=len(result['map_state']['nodes']),
            side_effects=result['side_effects'])),flush=True)
    else:
        print(raw,flush=True)


if __name__ == '__main__':main()
