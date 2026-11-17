"""Capacity, audit indexing, late receipts and interrupted archive transaction."""
import copy,json,subprocess,sys,tempfile,threading,unittest,urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from .gateway import Gateway,Handler
from .codec import encode_command
from .check_gateway import EUI,A,TX,FakeSocket,pkt,report

class ArchiveChecks(unittest.TestCase):
 def create(self,path,now):
  g=Gateway(EUI,'127.0.0.1',TX,clock=lambda:now[0],encoder=encode_command,state_file=path);g.sock=FakeSocket();return g
 def request(self,i):return dict(cmd_id=f'{i:016x}',target=A,target_boot=1,report_seq=i,operation='status',ttl_ms=1000)
 def fill(self,g,now,count):
  for i in range(1,count+1):
   g.ingest(pkt(report(A,i)));g.pull={'addr':('127.0.0.1',1),'time':now[0]};g.enqueue(self.request(i));g.flush();now[0]+=1.01;g.flush()
 def test_300_commands_restarts_duplicate_and_late_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'commands.json';now=[0.];g=self.create(path,now);self.fill(g,now,300)
   self.assertEqual(len(g.commands),256);self.assertEqual(g.stats['archived_commands'],44);self.assertEqual(g.command(f'{1:016x}')['state'],'execution_unknown_timeout');g.archive.close()
   restored=self.create(path,now);self.assertEqual(len(restored.commands),256);self.assertEqual(restored.enqueue(self.request(1))['state'],'execution_unknown_timeout')
   with self.assertRaisesRegex(ValueError,'different content'):restored.enqueue(dict(self.request(1),ttl_ms=2000))
   restored.ack_decoder=lambda _:dict(cmd_id=f'{1:016x}',target=A,target_boot=1,report_seq=1,operation='status',executed=True)
   restored.ingest(pkt(b'late receipt'));self.assertEqual(restored.command(f'{1:016x}')['state'],'executed');restored.ingest(pkt(b'late receipt'));self.assertEqual(restored.stats['duplicate_receipts'],1);restored.archive.close()
   again=self.create(path,now);self.assertEqual(again.command(f'{1:016x}')['state'],'executed');again.ingest(pkt(report(A,301)));again.enqueue(self.request(301));self.assertLessEqual(len(again.commands),256)
   server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.gateway=again;thread=threading.Thread(target=server.serve_forever);thread.start()
   try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));value=json.load(opener.open(f'http://127.0.0.1:{server.server_port}/api/v1/commands/{1:016x}'));self.assertEqual(value['state'],'executed')
   finally:server.shutdown();server.server_close();thread.join();again.archive.close()
 def test_archive_interruption_reconciles_and_missing_archive_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'commands.json';now=[0.];g=self.create(path,now);self.fill(g,now,256);g.ingest(pkt(report(A,257)))
   with patch.object(g,'persist',side_effect=OSError('interrupted after archive commit')):
    with self.assertRaises(OSError):g.enqueue(self.request(257))
   self.assertEqual(len(g.commands),256);self.assertIsNotNone(g.archive.get(f'{1:016x}'));g.archive.close()
   restored=self.create(path,now);self.assertEqual(len(restored.commands),255);self.assertEqual(restored.command(f'{1:016x}')['state'],'execution_unknown_timeout');restored.ingest(pkt(report(A,257)));restored.enqueue(self.request(257));restored.archive.close()
   archive=path.with_name(path.name+'.archive.sqlite3');archive.rename(archive.with_suffix('.saved'))
   with self.assertRaisesRegex(ValueError,'archive missing'):self.create(path,now)
   archive.write_bytes(b'')
   with self.assertRaisesRegex(ValueError,'archive invalid'):self.create(path,now)
 def test_process_death_between_archive_and_journal_commit(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'commands.json';now=[0.];g=self.create(path,now);g.ingest(pkt(report(A,1)));base=g.enqueue(self.request(1));base['state']='execution_unknown_timeout';base['attempts']=1
   for i in range(1,257):
    item=copy.deepcopy(base);item['cmd_id']=f'{i:016x}';item['request']['cmd_id']=item['cmd_id'];g.commands[item['cmd_id']]=item
   g.persist();g.archive.close()
   code=('import os,sys;from pathlib import Path;from tools.flight_link.gateway import Gateway;'
         'from tools.flight_link.check_gateway import EUI,TX;from tools.flight_link.codec import encode_command;'
         'g=Gateway(EUI,"127.0.0.1",TX,encoder=encode_command,state_file=Path(sys.argv[1]));'
         'g.persist=lambda:os._exit(91);g.archive_one()')
   child=subprocess.run([sys.executable,'-X','utf8','-c',code,str(path)],capture_output=True,timeout=15);self.assertEqual(child.returncode,91,child.stderr)
   restored=self.create(path,now);self.assertEqual(restored.stats['archive_reconciled'],1);self.assertEqual(len(restored.commands),255);self.assertEqual(restored.command(f'{1:016x}')['state'],'execution_unknown_timeout');self.assertEqual(restored.enqueue(self.request(1))['state'],'execution_unknown_timeout');restored.archive.close()

if __name__=='__main__':unittest.main()
