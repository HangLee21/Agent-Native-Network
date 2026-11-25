"""Serialized, identity-checked startup of the real PC upstream and studio."""
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid
from .server import ROOT


class StartupError(RuntimeError):
    pass


@dataclass
class Bench:
    pc_id: int = 310031
    pc_port: int = 8791
    udp_port: int = 8793
    udp_host: str = '0.0.0.0'
    studio_port: int = 8794
    demo_port: int = 8795
    state: str = '.local/mid/H-017/formal-pc-310031'
    maintenance: str = '.local/mid/H-017/maintenance-control.json'
    fault: str = '.local/mid/H-017/formal-lease-control.json'
    provisioning: str = '.local/mid/H-017/hotspot-20261109-14/board-ip-config.private.json'
    manage_hotspot: bool = sys.platform == 'win32'

    def path(self, name):
        path=(ROOT/getattr(self,name)).resolve()
        if not path.is_relative_to(ROOT): raise StartupError('Runtime paths must stay in this repository.')
        return path

    def validate(self):
        ports=[self.pc_port,self.udp_port,self.studio_port,self.demo_port]
        if any(type(p) is not int or not 1024<=p<=65535 for p in ports) or len(set(ports))!=4: raise StartupError('Four distinct service ports required.')
        if type(self.pc_id) is not int or not 1<=self.pc_id<=0xffffffff: raise StartupError('Invalid PC identity.')
        if self.udp_host not in ('127.0.0.1','0.0.0.0') or type(self.manage_hotspot) is not bool: raise StartupError('Invalid local transport.')
        for name in ('state','maintenance','fault','provisioning'): self.path(name)
        return self


def local_port_free(url):
    address=urlsplit(url)
    if address.hostname!='127.0.0.1': return False
    try:
        with socket.socket() as probe:
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            probe.bind(('127.0.0.1',address.port))
        return True
    except OSError:
        return False


def read_json(url,timeout=1):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url,timeout=timeout) as response: return json.load(response)
    except urllib.error.HTTPError as exc:
        raise StartupError(f'Existing service returned HTTP {exc.code}; it was preserved.') from exc
    except urllib.error.URLError as exc:
        reason=exc.reason
        if isinstance(reason,ConnectionRefusedError) or getattr(reason,'winerror',None)==10061 or getattr(reason,'errno',None)==errno.ECONNREFUSED: return None
        # Some Windows network filters silently drop connects to unused ports.
        # Only an exclusive local bind proves absence; an occupied timeout is preserved.
        if isinstance(reason,(TimeoutError,socket.timeout)) and local_port_free(url): return None
        raise StartupError('Cannot inspect readiness; existing processes preserved: '+str(reason)) from exc
    except TimeoutError as exc:
        if local_port_free(url): return None
        raise StartupError('Existing port timed out; its owner was preserved.') from exc
    except ValueError as exc:
        raise StartupError('Existing port identity/readiness could not be confirmed; it was preserved.') from exc


@contextmanager
def startup_lock(path,timeout=90):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        if path.stat().st_size==0: handle.write(b'0'); handle.flush()
        until=time.monotonic()+timeout
        while True:
            try:
                handle.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=until: raise StartupError('Another startup is preparing dependencies; try again shortly.')
                time.sleep(.1)
        try: yield
        finally:
            handle.seek(0)
            if os.name=='nt': msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def pc_identity(status,bench):
    w=status.get('wireless',{})
    if not (status.get('pc_id')==bench.pc_id and status.get('serial_access') is False and w.get('wire_protocol')=='field.ip.v2' and w.get('udp_bind')==[bench.udp_host,bench.udp_port] and isinstance(w.get('H017_fault'),dict)):
        raise StartupError('PC port belongs to an incompatible upstream; no process or state replaced.')
    return status


def spawn(command,output,name):
    with (output/(name+'.stdout.txt')).open('xb') as stdout,(output/(name+'.stderr.txt')).open('xb') as stderr:
        return subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,close_fds=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))


def wait_ready(url,process,validate,timeout=12):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        if process is not None and process.poll() is not None: raise StartupError('New service exited; inspect preserved stderr.')
        status=read_json(url)
        if status is not None: return validate(status)
        time.sleep(.1)
    raise StartupError('Dependency readiness timeout.')


def ensure_hotspot(bench,output):
    if not bench.manage_hotspot: return dict(managed=False,reason='explicit profile uses an existing LAN')
    if sys.platform!='win32' or not bench.path('provisioning').is_file(): raise StartupError('Existing private board provisioning required for hotspot recovery.')
    private=ROOT/'.local/mid/H-017'/('launcher-hotspot-'+uuid.uuid4().hex)
    command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/mobile_gateway/ensure_hotspot.ps1'),'-Provisioning',str(bench.path('provisioning')),'-PrivateDirectory',str(private)]
    r=subprocess.run(command,capture_output=True,text=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (output/'hotspot.stdout.txt').write_text(r.stdout,encoding='utf-8'); (output/'hotspot.stderr.txt').write_text(r.stderr,encoding='utf-8')
    if r.returncode: raise StartupError('Hotspot not compatible/ready; inspect hotspot.stderr.txt. No board or credentials changed.')
    return dict(json.loads(r.stdout),private_session=str(private))


def ensure_runtime(bench=None,*,runtime_dir=None,output=None,entry_wait=5):
    bench=(bench or Bench()).validate()
    runtime_dir=Path(runtime_dir or ROOT/'.local/mid/H-016')
    output=Path(output or ROOT/'simulation/outputs/H-016'/('startup-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])).resolve()
    if not any(output.is_relative_to(ROOT/'simulation/outputs'/task) for task in ('H-016','H-018','H-019','H-020')): raise StartupError('Use a new H-016, H-018, H-019 or H-020 startup output.')
    output.mkdir(parents=True,exist_ok=False)
    result=dict(status='starting',output=str(output),serial_opens=0,physical_business_sends=0,processes_started=[])
    try:
        with startup_lock(runtime_dir/'studio-launch.lock'):
            # Common dependency preparation for BOTH existing and absent 8794.
            result['hotspot']=ensure_hotspot(bench,output)
            pc_url=f'http://127.0.0.1:{bench.pc_port}/api/pc/status'
            pc=read_json(pc_url)
            if pc is None:
                try:
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe: probe.bind((bench.udp_host,bench.udp_port))
                except OSError as exc: raise StartupError('UDP port occupied; existing owner preserved.') from exc
                bench.path('maintenance').parent.mkdir(parents=True,exist_ok=True)
                bench.path('fault').parent.mkdir(parents=True,exist_ok=True)
                if not bench.path('fault').exists(): bench.path('fault').write_text('{"withhold_lease_nodes":[]}',encoding='utf-8')
                if json.loads(bench.path('fault').read_text()).get('withhold_lease_nodes'): raise StartupError('An experiment fault is configured; it was preserved, not cleared.')
                command=[sys.executable,'-X','utf8','-m','tools.mid_hardware.field_agent.lease_fault_server','--fault-file',str(bench.path('fault')),'--fault-log',str(output/'lease-faults.jsonl'),'--maintenance-file',str(bench.path('maintenance')),'serve','--state',str(bench.path('state')),'--pc-id',str(bench.pc_id),'--http-port',str(bench.pc_port),'--udp-host',bench.udp_host,'--udp-port',str(bench.udp_port),'--stop-file',str(output/'PC_STOP'),'--neighbor-snapshots']
                process=spawn(command,output,'pc')
                result['processes_started'].append(dict(role='pc',pid=process.pid,command=command,stop_file=str(output/'PC_STOP')))
                pc=wait_ready(pc_url,process,lambda s:pc_identity(s,bench))
            else: pc_identity(pc,bench)
            result['pc_instance_id'],result['pc_session']=pc['instance_id'],pc['pc_session']
            base=f'http://127.0.0.1:{bench.studio_port}'
            def valid_studio(value):
                if not value.get('capabilities',{}).get('demo_control'): raise StartupError('Studio port belongs to another service; preserved.')
                upstream=read_json(base+'/api/pc/status')
                if not upstream or upstream.get('instance_id')!=pc['instance_id']: raise StartupError('Existing studio uses another upstream; preserved.')
                return value
            studio=read_json(base+'/api/studio/status')
            if studio is None:
                command=[sys.executable,'-X','utf8','-m','tools.mobile_gateway.studio','--port',str(bench.studio_port),'--demo-port',str(bench.demo_port),'--pc-port',str(bench.pc_port),'--output',str(output/'studio'),'--stop-file',str(output/'STUDIO_STOP')]
                process=spawn(command,output,'studio')
                result['processes_started'].append(dict(role='studio',pid=process.pid,command=command,stop_file=str(output/'STUDIO_STOP')))
                studio=wait_ready(base+'/api/studio/status',process,valid_studio)
            else: valid_studio(studio)
            until=time.monotonic()+max(0,entry_wait)
            while not any(e['connected'] for e in pc['entries']) and time.monotonic()<until:
                time.sleep(.2); pc=pc_identity(read_json(pc_url) or {},bench)
            result.update(status='ready',url=base+'/',connected_entries=sum(e['connected'] for e in pc['entries']),waiting_for_boards=not any(e['connected'] for e in pc['entries']),studio_mode=studio['mode'])
            temp=runtime_dir/'studio-runtime.tmp'; temp.write_text(json.dumps(result,indent=2),encoding='utf-8'); temp.replace(runtime_dir/'studio-runtime.json')
    except Exception as exc:
        result.update(status='failed',error=str(exc)); raise
    finally: (output/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
