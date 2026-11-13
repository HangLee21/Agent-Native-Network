"""H-only pre-field credential injection. Never logs raw TX, SSID or password."""
import argparse,getpass,json,os,time,uuid
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True);p.add_argument('--node-id',required=True);p.add_argument('--bssid',required=True);p.add_argument('--channel',type=int,required=True);p.add_argument('--pc-ip',required=True);p.add_argument('--pc-id',type=int,default=1);p.add_argument('--listen-port',type=int,default=8792);p.add_argument('--pc-port',type=int,default=8793);a=p.parse_args()
 # --help exits before importing serial or requesting secrets.
 import serial
 ssid=os.environ.get('FIELD_SSID') or getpass.getpass('Hotspot SSID (hidden): ');password=os.environ.get('FIELD_PASSWORD') or getpass.getpass('Hotspot password (hidden): ')
 link=serial.Serial(port=None,baudrate=460800,timeout=.1,write_timeout=2,rtscts=False,dsrdtr=False)
 link.dtr=False;link.rts=False;link.port=a.port;link.open()
 with link:
  def request(cmd,**fields):
   nonce=uuid.uuid4().hex;raw=(json.dumps(dict(cmd=cmd,nonce=nonce,**fields),separators=(',',':'))+'\n').encode();count=link.write(raw)
   if count!=len(raw):raise RuntimeError('short credential write; outcome unknown; do not retry automatically')
   until=time.monotonic()+4
   while time.monotonic()<until:
    line=link.readline()
    try:reply=json.loads(line)
    except (ValueError,UnicodeError):continue
    if reply.get('event')=='command_result' and reply.get('nonce')==nonce:return reply
   raise RuntimeError('credential command timeout; outcome unknown; no automatic retry')
  info=request('info')
  if not info.get('ok') or info.get('node_id','').lower()!=a.node_id.lower() or info.get('field_api')!=2 or info.get('radio') or info.get('stopping'):raise RuntimeError('identity/field firmware/idle prerequisite failed; no credentials sent')
  result=request('ip_config',enabled=True,ssid=ssid,password=password,bssid=a.bssid,channel=a.channel,pc_ip=a.pc_ip,pc_id=a.pc_id,listen_port=a.listen_port,pc_port=a.pc_port)
  if not result.get('ok'):raise RuntimeError('IP configuration rejected; no raw request or secret printed')
  print(json.dumps(dict(node_id=a.node_id,ip_configuration='saved',credentials_logged=False,radio_started=False)))
if __name__=='__main__':main()
