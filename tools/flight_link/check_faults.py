"""Bounded synthetic faults; models missed downlinks, not real RF."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from .check_gateway import EUI,TX,FakeSocket,pkt,report
from .gateway import Gateway
from .codec import encode_command

class Faults(unittest.TestCase):
 def test_30_targets_fair_first_attempt_and_half_duplex_misses(self):
  now=[0.];g=Gateway(EUI,'127.0.0.1',TX,clock=lambda:now[0],encoder=encode_command)
  g.sock=FakeSocket();g.pull={'addr':('127.0.0.1',1),'time':0}
  for i in range(1,31):
   mac=f'02:00:00:00:00:{i:02x}';g.ingest(pkt(report(mac)))
   g.enqueue(dict(cmd_id=f'{i:016x}',target=mac,target_boot=1,report_seq=1,operation='status',ttl_ms=60000))
  # Simulate all first downlinks missing while each receiver transmits; no receipt.
  for tick in range(30):
   now[0]=tick;g.pull['time']=tick;g.flush()
  self.assertEqual([c['attempts'] for c in g.commands.values()],[1]*30)
  self.assertTrue(all(c['receipt'] is None for c in g.commands.values()))
  for tick in range(30,60):
   now[0]=tick;g.pull['time']=tick;g.flush()
  self.assertEqual([c['attempts'] for c in g.commands.values()],[2]*30)
  now[0]=60;g.flush()
  self.assertTrue(all(c['state']=='execution_unknown_timeout' for c in g.commands.values()))

 def test_restart_preserves_ids_no_retransmit_and_late_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'commands.json';now=[0.]
   def decode(data):return dict(cmd_id='0000000000000001',target='02:00:00:00:00:01',target_boot=1,report_seq=1,operation='status',executed=True)
   g=Gateway(EUI,'127.0.0.1',TX,clock=lambda:now[0],encoder=encode_command,ack_decoder=decode,state_file=path);g.sock=FakeSocket();g.pull={'addr':('127.0.0.1',1),'time':0}
   for i in (1,2):
    mac=f'02:00:00:00:00:{i:02x}';g.ingest(pkt(report(mac)));g.enqueue(dict(cmd_id=f'{i:016x}',target=mac,target_boot=1,report_seq=1,operation='status',ttl_ms=60000))
   g.flush();g2=Gateway(EUI,'127.0.0.1',TX,clock=lambda:now[0],encoder=encode_command,ack_decoder=decode,state_file=path);g2.sock=FakeSocket();g2.pull={'addr':('127.0.0.1',1),'time':0};g2.flush()
   self.assertEqual(g2.sock.sent,[]);self.assertEqual(g2.commands['0000000000000001']['state'],'execution_unknown_restart');self.assertEqual(g2.commands['0000000000000002']['state'],'restart_not_sent')
   self.assertEqual(g2.enqueue(g.commands['0000000000000001']['request'])['state'],'execution_unknown_restart')
   g2.ingest(pkt(b'late-synthetic-receipt'));self.assertEqual(g2.commands['0000000000000001']['state'],'executed')
   g3=Gateway(EUI,'127.0.0.1',TX,encoder=encode_command,ack_decoder=decode,state_file=path);self.assertEqual(g3.commands['0000000000000001']['state'],'executed');g.archive.close();g2.archive.close();g3.archive.close()

 def test_journal_failure_prevents_udp_send(self):
  g=Gateway(EUI,'127.0.0.1',TX,encoder=encode_command);g.sock=FakeSocket();g.pull={'addr':('127.0.0.1',1),'time':g.clock()};mac='02:00:00:00:00:01'
  g.ingest(pkt(report(mac)));g.enqueue(dict(cmd_id='0000000000000001',target=mac,target_boot=1,report_seq=1,operation='status',ttl_ms=60000))
  with patch.object(g,'persist',side_effect=OSError('disk failure')):
   with self.assertRaises(OSError):g.flush()
  self.assertEqual(g.sock.sent,[])

 def test_corrupt_primary_recovers_verified_backup_without_replay(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'commands.json';now=[0.];mac='02:00:00:00:00:01'
   g=Gateway(EUI,'127.0.0.1',TX,clock=lambda:now[0],encoder=encode_command,state_file=path);g.sock=FakeSocket();g.pull={'addr':('127.0.0.1',1),'time':0};g.ingest(pkt(report(mac)));g.enqueue(dict(cmd_id='0000000000000001',target=mac,target_boot=1,report_seq=1,operation='status',ttl_ms=60000));g.flush()
   path.write_text('{broken',encoding='utf-8')
   restored=Gateway(EUI,'127.0.0.1',TX,clock=lambda:now[0],encoder=encode_command,state_file=path);restored.sock=FakeSocket();restored.pull={'addr':('127.0.0.1',1),'time':0};restored.flush()
   self.assertEqual(restored.commands['0000000000000001']['state'],'execution_unknown_restart');self.assertFalse(restored.sock.sent);self.assertEqual(restored.stats['journal_backup_restored'],1);self.assertEqual(len(list(Path(d).glob('commands.json.corrupt.*'))),1);g.archive.close();restored.archive.close()
   path.write_text('{broken',encoding='utf-8');path.with_name(path.name+'.bak').write_text('{broken',encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'no verified backup'):Gateway(EUI,'127.0.0.1',TX,encoder=encode_command,state_file=path)

 def test_interrupted_mirror_preserves_both_command_ids(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'commands.json';mac='02:00:00:00:00:01';g=Gateway(EUI,'127.0.0.1',TX,encoder=encode_command,state_file=path)
   g.ingest(pkt(report(mac)));g.enqueue(dict(cmd_id='0000000000000001',target=mac,target_boot=1,report_seq=1,operation='status',ttl_ms=60000));old=path.with_name(path.name+'.bak').read_bytes()
   g.commands['0000000000000001']['attempts']=1;g.commands['0000000000000001']['state']='gateway_sent';g.persist();path.with_name(path.name+'.bak').write_bytes(old)
   recovered=Gateway(EUI,'127.0.0.1',TX,encoder=encode_command,state_file=path)
   self.assertEqual(recovered.commands['0000000000000001']['state'],'execution_unknown_restart');self.assertEqual(recovered.stats['journal_copies_reconciled'],1);g.archive.close();recovered.archive.close()

if __name__=='__main__':unittest.main()
