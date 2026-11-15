"""Small in-place console display. Detailed device output belongs in a log."""
import ctypes
import os
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path


def enable_vt(stream):
    if not stream.isatty(): return False,lambda:None
    if os.name!='nt': return True,lambda:None
    try:
        import msvcrt
        from ctypes import wintypes
        handle=msvcrt.get_osfhandle(stream.fileno())
        mode=wintypes.DWORD()
        kernel=ctypes.windll.kernel32
        kernel.GetConsoleMode.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        if not kernel.GetConsoleMode(handle,ctypes.byref(mode)):return False,lambda:None
        previous=mode.value
        if not kernel.SetConsoleMode(handle,previous|4):return False,lambda:None
        return True,lambda:kernel.SetConsoleMode(handle,previous)
    except (OSError,AttributeError,ValueError): return False,lambda:None


def clip(value,width):
    value=re.sub(r'[\x00-\x1f\x7f-\x9f]',' ',str(value))
    result='';cells=0
    for ch in value:
        size=2 if unicodedata.east_asian_width(ch) in ('W','F') else 1
        if cells+size>max(0,width-2): return result+'…'
        result+=ch;cells+=size
    return result


class ConsolePanel:
    def __init__(self,stream=None,*,clock=time.monotonic,tty=None,size=None):
        self.stream=stream or sys.stdout;self.clock=clock
        self.tty,self.restore_mode=enable_vt(self.stream) if tty is None else (tty,lambda:None)
        self.size=size or (lambda:shutil.get_terminal_size((100,30)))
        self.rows={};self.active={};self.last=0;self.lines=0;self.note='正在识别设备';self.log='';self.finished=False
        self.plain_last={}
        if self.tty: self.stream.write('\x1b[?25l');self.stream.flush()

    def record(self,event):
        if event.get('event')=='discovered':
            for port in event.get('ports',[]):
                if port not in self.active:
                    key=f'{port}#{len(self.rows)}';self.active[port]=key
                    self.rows[key]={'port':port,'node':'?','state':'等待处理','detail':'','result':'等待'}
        port=event.get('port')
        if port:
            if port not in self.active or (event.get('event')=='starting' and self.rows[self.active[port]].get('result') not in ('等待',)):
                key=f'{port}#{len(self.rows)}';self.active[port]=key
                self.rows[key]={'port':port,'node':'?','state':'正在识别','detail':'','result':'进行中'}
            row=self.rows[self.active[port]]
            if event.get('event')=='starting':row['_started']=self.clock()
            if event.get('node_id') is not None:row['node']=str(event['node_id'])
            if event.get('mac'):row['mac']=event['mac']
            if event.get('step'):row['state']=event['step']
            if event.get('event')=='finished':
                if '_started' in row:row['elapsed']=f"耗时 {max(0,self.clock()-row['_started']):.1f} 秒"
                result=event.get('result')
                row['result']='完成' if result=='success' else ('跳过' if result=='skipped' else '失败')
                row['state']='已停止' if result=='failed' else '已完成'
                row['detail']=event.get('error','')
        self.render(force=event.get('event')=='finished')

    def progress(self,number,message):
        match=re.search(r'\]\s+(COM\d+)\s+',message,re.I)
        if not match:
            self.note=message;self.render();return
        port=match.group(1)
        if port not in self.active:
            key=f'{port}#{len(self.rows)}';self.active[port]=key;self.rows[key]={'port':port,'node':'?','result':'进行中','state':'正在识别','detail':''}
        row=self.rows[self.active[port]]
        if str(number)!='未识别':row['node']=str(number)
        text=message[match.end():]
        row['state']=text;row['result']='失败' if '已停止' in text else '进行中'
        self.render(force='已停止' in text)

    def notify(self,message):
        self.note=message
        if not self.tty:self.stream.write(clip(message,200)+'\n');self.stream.flush()
        self.render(force=True)

    def final(self,rows,log):
        self.log='data/logs/'+Path(log).name;self.note='操作结束；详情见日志';self.finished=True
        previous=list(self.rows.values());self.rows={};self.active={}
        for item in rows:
            port=item.get('port') or '未知';mac=item.get('mac')
            row=next((dict(r) for r in reversed(previous) if mac and r.get('mac')==mac),None)
            if row is None and not mac:
                row=next((dict(r) for r in reversed(previous) if r.get('port')==port and not r.get('mac')),None)
            if row is None:
                row={'port':port,'node':'?'}
            key=f'{port}#{len(self.rows)}';self.rows[key]=row
            if item.get('port'):row['port']=port
            if item.get('node_id') is not None:row['node']=str(item['node_id'])
            result=item.get('result')
            row['result']={'success':'完成','failed':'失败','unknown':'未知'}.get(result,'未知')
            elapsed=re.search(r'耗时\s*[\d.]+\s*秒',row.get('state',''))
            elapsed_text=row.get('elapsed') or (elapsed.group(0) if elapsed else '')
            row['state']=('已完成' if result=='success' else '已停止')+(' '+elapsed_text if elapsed_text else '')
            row['detail']=item.get('error') or item.get('last_error') or item.get('pending_reason') or ''
        self.render(force=True)

    def render(self,force=False):
        now=self.clock()
        if not force and now-self.last<(.25 if self.tty else 1.0):return
        self.last=now
        if not self.tty:
            for key,row in self.rows.items():
                line=f"节点 {row.get('node','?')} {row['port']} {row.get('state','')} {row.get('result','')} {row.get('detail','')}"
                if self.plain_last.get(key)!=line:
                    self.stream.write(clip(line,200)+'\n');self.plain_last[key]=line
            if self.finished:self.stream.write('详情日志：'+self.log+'\n')
            self.stream.flush();return
        width,height=self.size(); width=max(20,width-1);height=max(5,height)
        rows=list(self.rows.values());done=sum(x.get('result')=='完成' for x in rows)
        fail=sum(x.get('result')=='失败' for x in rows);unknown=sum(x.get('result')=='未知' for x in rows)
        lines=['节点烧录',f'发现 {len(rows)}  完成 {done}  失败 {fail}  未知 {unknown}',self.note]
        capacity=max(0,height-6)
        for row in (rows[-capacity:] if capacity else []):
            lines.append(f"节点 {row.get('node','?')} | {row['port']} | {row.get('result','')} | {row.get('state','')} {row.get('detail','')}")
        if len(rows)>capacity:lines.append(f'另有 {len(rows)-capacity} 个节点，详见日志')
        if self.log:lines.append('详情日志：'+self.log)
        if self.lines:self.stream.write(f'\x1b[{self.lines}A')
        count=max(self.lines,len(lines))
        for i in range(count):self.stream.write('\r\x1b[2K'+(clip(lines[i],width) if i<len(lines) else '')+'\n')
        if count>len(lines):self.stream.write(f'\x1b[{count-len(lines)}A')
        self.lines=len(lines);self.stream.flush()

    def close(self):
        try:
            if not self.finished:self.render(force=True)
        finally:
            try:
                if self.tty:self.stream.write('\x1b[?25h');self.stream.flush()
            finally:self.restore_mode()
