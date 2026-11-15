"""Bounded SSH transport: verified host keys, streamed files and guarded sudo."""
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parent

class TransportError(RuntimeError):pass


def close_bounded(client,force=False):
    def abort_socket():
        try:
            transport=client.get_transport()
            if transport and transport.sock:transport.sock.close()
        except Exception:pass
    if force:abort_socket()
    worker=threading.Thread(target=client.close,daemon=True);worker.start();worker.join(2)
    if worker.is_alive() and not force:
        abort_socket();worker.join(.5)


def bounded_call(client,operation,timeout,late_cleanup=None):
    done=threading.Event();cancelled=threading.Event();state={}
    def work():
        try:
            result=operation()
            if cancelled.is_set() and late_cleanup:
                try:late_cleanup(result)
                except Exception:pass
            else:state['result']=result
        except Exception as exc:state['error']=exc
        finally:done.set()
    worker=threading.Thread(target=work,daemon=True);worker.start()
    if not done.wait(timeout):
        cancelled.set();close_bounded(client,force=True)
        raise TransportError('网关文件传输超时，连接已关闭')
    if 'error' in state:raise state['error']
    return state.get('result')


def open_sftp_bounded(client,timeout=15):
    sftp=bounded_call(client,client.open_sftp,timeout,late_cleanup=lambda x:x.close())
    sftp.get_channel().settimeout(15)
    return sftp


def sftp_call(client,operation,timeout=15):
    return bounded_call(client,operation,timeout)


def load_ssh_library():
    vendor=ROOT/'vendor_ssh'
    manifest=json.loads((ROOT/'ssh_dependencies.json').read_text(encoding='utf-8'))
    expected=manifest.get('files_sha256',{})
    if not expected:raise TransportError('SSH 依赖清单缺失')
    for name,digest in expected.items():
        path=(vendor/name).resolve()
        try:path.relative_to(vendor.resolve())
        except ValueError:raise TransportError('SSH 依赖路径无效')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise TransportError('SSH 依赖校验失败，请更新交付包')
    sys.path.insert(0,str(vendor))
    import paramiko
    return paramiko


def fingerprint(key):
    return 'SHA256:'+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode('ascii').rstrip('=')


def connect(host,user,ask=input,secret=getpass.getpass,known_hosts=None,lib=None):
    lib=lib or load_ssh_library()
    known_hosts=Path(known_hosts) if known_hosts else Path.home()/'.ssh'/'known_hosts'
    class ConfirmUnknown(lib.MissingHostKeyPolicy):
        def missing_host_key(self,owner,hostname,key):
            # An existing host, even with a different key type, must never be silently replaced.
            if owner.get_host_keys().lookup(hostname):raise TransportError('网关身份发生变化，已停止连接')
            print('首次连接网关，身份指纹：'+fingerprint(key),flush=True)
            if ask('请与技术支持核对指纹；确认请输入 YES，其他输入取消：').strip()!='YES':
                raise TransportError('未确认网关身份')
            known_hosts.parent.mkdir(parents=True,exist_ok=True)
            owner.get_host_keys().add(hostname,key.get_name(),key)
            owner.save_host_keys(str(known_hosts))
    for attempt in range(1,4):
        print('网关 {}，登录账户 {}。输入时密码不会显示；直接回车可取消。'.format(host,user),flush=True)
        try:password=secret('网关密码：')
        except (KeyboardInterrupt,EOFError):raise TransportError('已取消网关登录') from None
        if not password:raise TransportError('已取消网关登录')
        client=lib.SSHClient()
        try:
            if known_hosts.is_file():client.load_host_keys(str(known_hosts))
            client.set_missing_host_key_policy(ConfirmUnknown())
            client.connect(hostname=host,username=user,password=password,timeout=5,auth_timeout=30,banner_timeout=10,look_for_keys=False,allow_agent=False)
            return client,password
        except lib.BadAuthenticationType:
            password=None;close_bounded(client)
            raise TransportError('网关 {} 的账户 {} 不支持当前密码认证方式，请联系技术支持。'.format(host,user)) from None
        except lib.AuthenticationException:
            password=None;close_bounded(client)
            print('网关 {} 拒绝了账户 {} 的认证（第 {} 次）。'.format(host,user,attempt),flush=True)
            if attempt==3:raise TransportError('网关认证未通过，已停止；请核对账户信息或联系技术支持。') from None
        except KeyboardInterrupt:
            password=None;close_bounded(client)
            raise TransportError('已取消网关登录') from None
        except BaseException:
            password=None;close_bounded(client);raise


def upload_verified(client,local_file,remote_file,expected_sha256,timeout=180):
    local_file=Path(local_file)
    digest=hashlib.sha256()
    with local_file.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    if digest.hexdigest()!=expected_sha256:raise TransportError('交付包校验失败，未上传')
    sftp=open_sftp_bounded(client)
    def transfer():
        with local_file.open('rb') as source, sftp.open(remote_file,'wb') as target:
            for chunk in iter(lambda:source.read(1024*1024),b''):target.write(chunk)
        with sftp.open(remote_file,'rb') as remote:
            digest=hashlib.sha256()
            for chunk in iter(lambda:remote.read(1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=expected_sha256:raise TransportError('网关文件校验失败，未安装')
    try:bounded_call(client,transfer,timeout)
    finally:
        # Never let an unresponsive remote session block the caller's cleanup.
        threading.Thread(target=sftp.close,daemon=True).start()


def readonly_command(client,command,limit=65536):
    stdin,stdout,stderr=client.exec_command(command,timeout=20)
    try:
        stdout.channel.set_combine_stderr(True)
        data=stdout.read(limit+1)
        if len(data)>limit:raise TransportError('网关检查结果过长，已停止')
        code=stdout.channel.recv_exit_status()
        if code:raise TransportError('网关检查失败（退出码 {}）'.format(code))
        return data.decode('utf-8','replace') if isinstance(data,bytes) else data
    finally:
        stdout.channel.close()


def sudo_command(client,argv,password,timeout=120,output=None,secret=getpass.getpass,sudo_path='/usr/bin/sudo'):
    if not argv or any(not isinstance(x,str) or '\x00' in x for x in argv):raise TransportError('管理员命令无效')
    if not re.fullmatch(r'/[A-Za-z0-9_./+-]+',sudo_path):raise TransportError('管理员程序路径无效')
    output=output or sys.stdout
    nonce='ANN_SUDO_'+uuid.uuid4().hex+':'
    command='stty -echo && '+shlex.quote(sudo_path)+' -S -p '+shlex.quote(nonce)+' -- '+' '.join(shlex.quote(x) for x in argv)+'; rc=$?; stty echo; exit $rc'
    chan=client.get_transport().open_session();chan.get_pty();chan.settimeout(1);chan.exec_command(command)
    marker=nonce.encode('ascii');pending=b'';attempts=0;deadline=time.monotonic()+timeout
    try:
        while True:
            if time.monotonic()>deadline:raise TransportError('网关管理员操作超时')
            if chan.recv_ready():
                chunk=chan.recv(4096)
                if not chunk:break
                pending+=chunk
                while marker in pending:
                    before,pending=pending.split(marker,1)
                    output.write(before.decode('utf-8','replace'));output.flush()
                    if attempts>=2:raise TransportError('管理员认证未通过')
                    credential=password if attempts==0 else secret('请输入网关管理员密码（输入不显示）：')
                    chan.sendall((credential+'\n').encode('utf-8'));credential=None;attempts+=1
                # Keep only a possible prefix of the marker; never print a partial prompt.
                keep=0
                for size in range(1,min(len(marker),len(pending))+1):
                    if pending[-size:]==marker[:size]:keep=size
                if len(pending)>keep:
                    data=pending[:-keep] if keep else pending
                    output.write(data.decode('utf-8','replace'));output.flush()
                    pending=pending[-keep:] if keep else b''
            elif chan.exit_status_ready():break
            else:time.sleep(.05)
        if pending:output.write(pending.decode('utf-8','replace'));output.flush()
        code=chan.recv_exit_status()
        if code:raise TransportError('网关管理员操作未完成（退出码 {}）'.format(code))
    finally:chan.close()
