"""Business application client for the one local serial owner's loopback API."""
import json
import time
import urllib.request
import urllib.parse
import uuid
import urllib.error

class LocalClient:
    def __init__(self,port=8780):
        if type(port) is not int or not 1024<=port<=65535:raise ValueError('local unprivileged port required')
        self.base='http://127.0.0.1:'+str(port);self.cursor=0;self.instance_id=None
    def _call(self,path,body=None):
        request=urllib.request.Request(self.base+path,None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':self.base})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=20) as r:return json.load(r)
    def send(self,dst,payload,request_id=None):
        if not isinstance(payload,bytes):raise ValueError('bytes required')
        return self._call('/api/edge/send',dict(request_id=request_id or uuid.uuid4().hex,dst=dst,payload_hex=payload.hex()))
    def recv(self,timeout=30):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            status=self._call('/api/edge/status')
            if status['instance_id']!=self.instance_id:self.instance_id=status['instance_id'];self.cursor=0
            data=self._call('/api/edge/inbox?after='+str(self.cursor))
            for record in data['records']:
                if record['inbox_cursor']>self.cursor:
                    self.cursor=record['inbox_cursor'];return dict(record,payload=bytes.fromhex(record['payload_hex']))
            time.sleep(min(.1,max(0,end-time.monotonic())))
        raise TimeoutError('no local endpoint delivery')
    def neighbors(self):return self._call('/api/edge/neighbors')
    def _lora_call(self,path,body=None):
        from .client import EdgeError,UnsupportedFirmware
        try:return self._call(path,body)
        except urllib.error.HTTPError as exc:
            try:value=json.load(exc)
            except ValueError:value={}
            message=value.get('error',str(exc))
            if value.get('supported') is False:raise UnsupportedFirmware(message) from exc
            raise EdgeError(message) from exc
    def lora_status(self):return self._lora_call('/api/edge/lora/status')
    def lora_config(self,**fields):
        from .lora import validate_config
        return self._lora_call('/api/edge/lora/config',validate_config(fields))
    def lora_events(self,after=0,wait=0):
        return self._lora_call('/api/edge/lora/events?'+urllib.parse.urlencode(dict(after=after,wait=wait)))
    def node_status(self,mac):return self._call('/api/edge/nodes/'+mac)
    def events(self,after=0,wait=10):return self._call('/api/edge/events?after='+str(after)+'&wait='+str(wait))
    def routes(self):return self._call('/api/edge/routes')
    def request_status(self,request_id):
        return self._call('/api/edge/requests/'+urllib.parse.quote(request_id,safe=''))
    def packet_status(self,origin,origin_boot,seq,dst):
        return self._call('/api/edge/packet?'+urllib.parse.urlencode(dict(origin=origin,origin_boot=origin_boot,seq=seq,dst=dst)))
