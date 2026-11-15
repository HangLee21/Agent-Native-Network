"""One local board, one serial owner. No HTTP, routing controller or IP transport."""
import collections
import json
import queue
import threading
import time
import uuid
import re


class EdgeError(RuntimeError):
    pass


class UnsupportedFirmware(EdgeError):
    pass


class Edge:
    def __init__(self, port, node_id, baudrate=115200, *, transport=None, log=None):
        self.node_id = node_id.lower()
        self._condition = threading.Condition()
        self._commands = threading.RLock()
        self._events = collections.deque(maxlen=4096)
        self._rx = queue.Queue(maxsize=256)
        self._replies = {}
        self._waiting = set()
        self._closed = False
        self._fault = None
        self._cursor = 0
        self._lora_cursor = 0
        self._lora_events = collections.deque(maxlen=256)
        self._lora_rejected = 0
        self._log = open(log, 'x', encoding='utf-8') if log else None
        if transport is None:
            import serial
            import os
            transport = serial.Serial(port=None, baudrate=baudrate, timeout=.1,
                                      write_timeout=1, **({'exclusive': True} if os.name != 'nt' else {}))
            transport.dtr = transport.rts = False
            transport.port = port
            try:
                transport.open()
            except Exception:
                if self._log: self._log.close()
                raise
        self._serial = transport
        self._reader = threading.Thread(target=self._read, name='mid-edge-reader', daemon=True)
        self._reader.start()

    def _read(self):
        buffer = bytearray()
        try:
            while not self._closed:
                part = self._serial.read(4096)
                if not part: continue
                buffer.extend(part)
                if len(buffer) > 65536: raise EdgeError('serial line buffer overflow')
                while b'\n' in buffer:
                    line, _, tail = buffer.partition(b'\n'); buffer[:] = tail
                    try: event = json.loads(line)
                    except (ValueError, UnicodeError): continue  # ROM boot text
                    if not isinstance(event, dict):continue
                    if event.get('schema')=='lora.ref.v1':
                        from .lora import decode_event
                        try:value=decode_event(line.decode('utf-8'),self.node_id)
                        except (ValueError,KeyError,TypeError):
                            with self._condition:self._lora_rejected+=1
                            continue
                        with self._condition:
                            self._lora_cursor+=1
                            value=dict(value,lora_cursor=self._lora_cursor,host_monotonic_ns=time.monotonic_ns(),host_received_ms=int(time.time()*1000))
                            if self._log:
                                self._log.write(json.dumps(dict(event=value))+'\n');self._log.flush()
                            self._lora_events.append(value);self._condition.notify_all()
                        continue
                    if event.get('schema') != 'mid.serial.v1': continue
                    if event.get('node_id', '').lower() != self.node_id:
                        raise EdgeError('serial board identity mismatch')
                    with self._condition:
                        self._cursor += 1
                        event = dict(event, edge_cursor=self._cursor)
                        if self._log:
                            self._log.write(json.dumps(dict(event=event, host_monotonic_ns=time.monotonic_ns()))+'\n')
                            self._log.flush()
                        self._events.append(event)
                        if event.get('event') == 'command_result' and event.get('nonce') in self._waiting:
                            self._replies[event['nonce']] = event
                        if event.get('event') == 'rx_local':
                            raw = bytes.fromhex(event['payload_hex'])
                            if not isinstance(event.get('origin'),str) or any(type(event.get(k)) is not int or not 1<=event[k]<=0xffffffff for k in ['origin_boot','seq']) or event.get('dst', '').lower() != self.node_id or len(raw)>160:
                                raise EdgeError('invalid endpoint payload event')
                            self._rx.put_nowait(dict(event, payload=raw, delivery_status='destination_received'))
                        self._condition.notify_all()
        except Exception as exc:
            with self._condition:
                if not self._closed: self._fault = str(exc) or type(exc).__name__
                self._condition.notify_all()

    def _check(self):
        if self._fault: raise EdgeError(self._fault)
        if self._closed: raise EdgeError('edge closed')

    def command(self, cmd, timeout=4, **fields):
        if 'cmd' in fields or 'nonce' in fields: raise ValueError('reserved fields')
        nonce = uuid.uuid4().hex
        packet = dict(schema='mid.serial.v1', cmd=cmd, nonce=nonce, **fields)
        wire = (json.dumps(packet, separators=(',', ':'))+'\n').encode()
        if len(wire)>1025: raise ValueError('command exceeds firmware line bound')
        with self._commands:
            with self._condition:
                self._check(); self._waiting.add(nonce)
            try:
                for offset in range(0,len(wire),32):
                    part=wire[offset:offset+32]
                    if self._serial.write(part)!=len(part): raise EdgeError('short serial write; command outcome unknown')
                    time.sleep(.012)
                end = time.monotonic()+timeout
                with self._condition:
                    while nonce not in self._replies:
                        self._check()
                        remaining=end-time.monotonic()
                        if remaining<=0: raise TimeoutError('command outcome unknown; do not automatically resend')
                        self._condition.wait(remaining)
                    reply = self._replies.pop(nonce)
                    if not reply.get('ok'): raise EdgeError(json.dumps(reply))
                    return reply
            finally:
                with self._condition:
                    self._waiting.discard(nonce); self._replies.pop(nonce,None)

    def info(self):
        return self.command('info')

    def identify(self):
        """Read-only project/STA identity check; never starts radio or configures."""
        reply=self.info()
        if reply.get('firmware')!='mid-espnow' or reply.get('chip')!='esp32s3' or reply.get('node_id','').lower()!=self.node_id:
            raise EdgeError('not the registered MID ESP32-S3 firmware/STA identity')
        return reply

    def health(self):
        with self._condition:self._check()
        return dict(connected=True,node_id=self.node_id)

    def neighbors(self):
        return self.command('neighbors')  # local firmware table; no RF probe

    def telemetry(self):
        return self.command('telemetry')  # E1-026 local read; no RF transmission

    def lora_status(self):
        try:reply=self.command('lora_ref_status')
        except EdgeError as exc:
            if 'unknown_command' in str(exc):raise UnsupportedFirmware('firmware does not support lora_ref_status; install the matching E1-029 firmware') from exc
            raise
        if reply.get('lora_ref_requested_role') not in ('off','rx','tx'):
            raise UnsupportedFirmware('firmware did not return the LoRa reference status contract')
        from .lora import application_verified
        return dict(reply,driver_configuration_verified=application_verified(reply))

    def lora_config(self,**fields):
        from .lora import validate_config,readback
        fields=validate_config(fields)
        with self._commands:
            self.lora_status() # Reject older firmware before attempting any change.
            acknowledgement=self.command('lora_ref_config',**fields)
            status=self.lora_status()
        return dict(acknowledgement=acknowledgement,status=status,readback=readback(fields,status),
                    persistence_acknowledged=True,driver_configuration_verified=status['driver_configuration_verified'],
                    note='Configuration is saved by firmware; worker application is asynchronous. No reset or automatic retry.')

    def lora_events(self,after=0,wait=0):
        if type(after) is not int or after<0 or type(wait) not in (int,float) or not 0<=wait<=10:
            raise ValueError('after>=0 and wait0..10 required')
        deadline=time.monotonic()+wait
        with self._condition:
            while self._lora_cursor<=after:
                self._check();remaining=deadline-time.monotonic()
                if remaining<=0:break
                self._condition.wait(remaining)
            self._check()
            oldest=self._lora_events[0]['lora_cursor'] if self._lora_events else self._lora_cursor+1
            return dict(records=[dict(event) for event in self._lora_events if event['lora_cursor']>after],
                cursor=self._lora_cursor,oldest_cursor=oldest,truncated=after>0 and after<oldest-1,
                rejected_events=self._lora_rejected,source='local_board_reference_channel',wifi_delivery_evidence=False)

    def set_position(self, **fields):
        from .mobile_position import validate_position
        return self.command('position_set', **validate_position(fields))

    def node_status(self,node_id):
        if not isinstance(node_id,str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',node_id):raise ValueError('valid STA MAC required')
        return dict(self.command('neighbor',node_id=node_id.lower()),source='local_firmware_table',rf_probe_started=False)

    def neighbor_probe(self,node_id):
        if not isinstance(node_id,str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',node_id):raise ValueError('valid STA MAC required')
        return self.command('neighbor_probe',node_id=node_id.lower())

    def discover_config(self,group,channel,autostart=True):
        if type(group) is not int or not 1<=group<=0xffffffff or type(channel) is not int or not 1<=channel<=13 or type(autostart) is not bool:raise ValueError('valid group/channel/autostart required')
        self.identify()
        return self.command('discover_config',group=group,channel=channel,autostart=autostart)

    def route_config(self,group,channel,autostart=True):
        if type(group) is not int or not 1<=group<=0xffffffff or type(channel) is not int or not 1<=channel<=13 or type(autostart) is not bool:raise ValueError('valid group/channel/autostart required')
        self.identify()
        return self.command('route_config',group=group,channel=channel,autostart=autostart)

    def routes(self):return self.command('routes')  # native board cache, never host planning

    def route_start(self):
        if self.identify().get('deployment_mode')!='autonomous':raise EdgeError('no saved autonomous profile; no other mode started')
        return self.command('route_start')

    def route_clear(self):
        if self.identify().get('deployment_mode')!='autonomous':raise EdgeError('not autonomous mode; no other profile cleared')
        return self.command('route_clear')

    def wait_events(self,after=0,timeout=10):
        if type(after) is not int or after<0 or not 0<=timeout<=10:raise ValueError('after>=0 and wait0..10 required')
        end=time.monotonic()+timeout
        with self._condition:
            while self._cursor<=after:
                self._check();remaining=end-time.monotonic()
                if remaining<=0:break
                self._condition.wait(remaining)
            return self.events(after)

    def deploy(self, profile):
        """Explicit locally provisioned deployment; no remote publisher boot cache."""
        if 'node_id' in profile and profile['node_id'].lower()!=self.node_id: raise ValueError('profile board mismatch')
        command=profile.get('command',profile)
        if command.get('cmd')!='deploy': raise ValueError('expected local deploy command')
        fields={k:command[k] for k in ['profile_id','table_hex','autostart']}
        return self.command('deploy', **fields)

    def send(self, dst, payload, timeout=4):
        if not isinstance(payload, bytes) or len(payload)>160: raise ValueError('payload must be bytes, length0..160')
        with self._commands:
            with self._condition: start=self._cursor
            reply=self.command('send',timeout,dst=dst,payload_hex=payload.hex())
            with self._condition:
                candidates=[e for e in self._events if e['edge_cursor']>start and e.get('event')=='tx_queued' and e.get('origin','').lower()==self.node_id and e.get('dst','').lower()==dst.lower() and self._business_event(e)]
            if 'packet_seq' in reply:
                if any(type(reply.get(k)) is not int or not 1<=reply[k]<=0xffffffff for k in ['packet_seq','origin_boot']):raise EdgeError('invalid accepted packet identity')
                if reply.get('origin',self.node_id).lower()!=self.node_id or reply.get('dst',dst).lower()!=dst.lower():raise EdgeError('send reply endpoint mismatch')
                identity=dict(origin=self.node_id,origin_boot=reply['origin_boot'],seq=reply['packet_seq'],dst=dst.lower())
                queued=next((e for e in candidates if all(e.get(k)==v for k,v in identity.items())),None)
            else:
                if len(candidates)!=1:raise EdgeError('send accepted without unambiguous source admission identity')
                queued=candidates[0];identity={k:queued[k] for k in ['origin','origin_boot','seq','dst']}
            return dict(accepted=True, delivery_status='destination_unconfirmed',
                        **identity,admission_state=('next_hop_queued' if queued.get('next_hop') else 'locally_queued') if queued else 'accepted_pending_events',
                        admission=queued,command_result=reply)

    def packet_status(self,origin,origin_boot,seq,dst):
        for value in [origin,dst]:
            if not isinstance(value,str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',value):raise ValueError('valid packet endpoint MAC required')
        if any(type(v) is not int or not 1<=v<=0xffffffff for v in [origin_boot,seq]):raise ValueError('valid packet boot/sequence required')
        identity=dict(origin=origin.lower(),origin_boot=origin_boot,seq=seq,dst=dst.lower())
        with self._condition:
            self._check();events=[dict(e) for e in self._events if all(e.get(k)==v for k,v in identity.items()) and self._business_event(e)]
            complete=not self._events or self._events[0]['edge_cursor']==1
            rounds={e['request'] for e in events if e['event']=='route_waiting' and e.get('request')}
            history=[dict(e) for e in self._events if e.get('event') in ['route_request','route_candidate','route_selected','route_no_route','route_invalidated'] and e.get('origin')==identity['origin'] and e.get('origin_boot')==origin_boot and e.get('dst')==identity['dst'] and e.get('request') in rounds]
        names={e['event'] for e in events}
        callbacks=[e for e in events if e['event'] in ['tx_link_ok','tx_link_fail']]
        destination=[e for e in events if e['event']=='rx_local' and e.get('node_id')==identity['dst'] and 'payload_hex' in e]
        no_route=[e for e in events if e['event']=='route_no_route' and e.get('request') in rounds]
        cancelled=any(e['event']=='route_no_route' and e.get('reason')==6 for e in events)
        terminal='cancelled_by_stop' if cancelled and 'tx_submit' not in names else 'route_no_route' if no_route and 'tx_submit' not in names else 'delivery_unknown' if 'delivery_unknown' in names else None
        return dict(identity=identity,source='local_board_events',evidence_scope='local_board_retained_serial_only',packet_observed=bool(events),events=events,evidence_complete=complete,
            queue_status='closed_cancelled' if terminal=='cancelled_by_stop' else 'closed_no_route' if terminal=='route_no_route' else 'closed_delivery_unknown' if terminal=='delivery_unknown' else 'waiting_route' if 'route_waiting' in names and 'tx_submit' not in names else 'next_hop_queued' if any(e['event']=='tx_queued' and e.get('next_hop') for e in events) else 'locally_queued' if 'tx_queued' in names else 'not_observed',
            transmission_status='radio_api_accepted' if 'tx_submit' in names else 'not_observed',
            link_callback=('success' if callbacks[-1]['event']=='tx_link_ok' else 'failure') if callbacks else 'not_observed',
            delivery_status='destination_received' if destination else 'destination_unconfirmed',
            destination_evidence=destination,endpoint_ack_observed=False,board_terminal=terminal,
            route_history=history,board_selected_paths=[dict(path=e['path'],request=e['request'],edge_cursor=e['edge_cursor'],scope='board_choice_not_hop_receipts') for e in history if e['event']=='route_selected' and e.get('path')])

    @staticmethod
    def _business_event(event):
        # Legacy MID business events have no packet_kind; their control records lack dst.
        # Autonomous frames must mark their kind: a RREQ sequence can equal DATA seq.
        kind=event.get('packet_kind')
        return kind is None or kind in ['DATA','data']

    def wait_packet(self,origin,origin_boot,seq,dst,timeout=10):
        if type(timeout) not in [int,float] or not 0<=timeout<=60:raise ValueError('wait0..60 seconds required')
        end=time.monotonic()+timeout
        while True:
            status=self.packet_status(origin,origin_boot,seq,dst)
            if status['delivery_status']=='destination_received' or status['board_terminal']:return dict(status,observation_timeout=False)
            remaining=end-time.monotonic()
            if remaining<=0:return dict(status,observation_timeout=True)
            with self._condition:self._condition.wait(min(remaining,.2))

    def recv(self, timeout=None):
        end=None if timeout is None else time.monotonic()+timeout
        while True:
            self._check()
            try: return self._rx.get(timeout=.1 if end is None else max(0,min(.1,end-time.monotonic())))
            except queue.Empty:
                if end is not None and time.monotonic()>=end: raise TimeoutError('no endpoint delivery')

    def events(self, after=0):
        with self._condition:
            self._check()
            if self._events and after and after<self._events[0]['edge_cursor']-1:
                raise EdgeError('event cursor expired; consult persistent log')
            return [dict(e) for e in self._events if e['edge_cursor']>after]

    def close(self):
        self._closed=True
        self._serial.close()
        self._reader.join(timeout=2)
        if self._reader.is_alive(): raise EdgeError('reader did not exit')
        if self._log: self._log.close()

    def __enter__(self): return self
    def __exit__(self,*args): self.close()
