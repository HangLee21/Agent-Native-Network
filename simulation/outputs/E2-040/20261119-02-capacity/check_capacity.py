import json,pathlib,random,sqlite3,sys,tempfile,time,unittest
root=pathlib.Path(r'D:\Multi-Agent Network');sys.path.insert(0,str(root))
from tools.mobile_gateway.replay import Replay
class Checks(unittest.TestCase):
 def test_failure_continues_and_old_text_reads(self):
  count=[0]
  def source():
   count[0]+=1
   if count[0]==2:raise OSError('offline')
   return {'schema':'lora.topology.v1','source':'fixture','receiver':{'gateway_observed':True},'reports':[]}
  with tempfile.TemporaryDirectory() as d:
   r=Replay(pathlib.Path(d)/'db.sqlite3',source,60);ident=r.start();r.sample();r.sample();r.sample();frames=r.session(ident)['frames'];self.assertEqual([x['topology']['receiver']['gateway_observed'] for x in frames],[True,False,True]);self.assertEqual(r.sessions()['active_id'],ident)
   old={'schema':'lora.topology.v1','source':'old','reports':[]};r.db.execute('INSERT INTO frames VALUES(?,?,?)',(ident,1,json.dumps(old)));r.db.commit();self.assertEqual(r.session(ident)['frames'][-1]['topology'],old);r.close()
 def test_30_nodes_1800_samples(self):
  rand=random.Random(52);snapshot={'schema':'lora.topology.v1','source':'fixture','source_id':'udp:test','selection_epoch':1,'receiver':{'gateway_observed':True},'reports':[]}
  for i in range(30):
   rows=[{'peer_id':'02:00:00:00:00:%02x'%j,'peer_boot':1000+j,'state':'bidirectional','seen_age_ms':rand.randrange(10000),'ack_age_ms':rand.randrange(10000),'wifi_rssi_dbm':-rand.randrange(40,95)} for j in range(30) if i!=j]
   snapshot['reports'].append({'pc_receive_age_ms':0,'gateway_id':'test','report':{'observer_id':'02:00:00:00:00:%02x'%i,'observer_boot':1000+i,'report_seq':1,'report_period_ms':10000,'neighbors':rows}})
  with tempfile.TemporaryDirectory() as d:
   path=pathlib.Path(d)/'db.sqlite3';r=Replay(path,lambda:snapshot,60);ident=r.start();start=time.monotonic()
   for n in range(1800):
    for row in snapshot['reports']:
     row['pc_receive_age_ms']=rand.randrange(12000);row['report']['report_seq']=n+1
     for edge in row['report']['neighbors']:
      edge['seen_age_ms']=rand.randrange(10000);edge['ack_age_ms']=rand.randrange(10000);edge['wifi_rssi_dbm']=-rand.randrange(40,95)
    r.sample()
    if not r.active:break
   status=r.sessions();r.stop();size=path.stat().st_size;frames=len(r.session(ident)['frames']);print('frames=%d database_bytes=%d elapsed_s=%.1f'%(frames,size,time.monotonic()-start));self.assertEqual(frames,1800);self.assertLess(size,32*1024*1024);self.assertIsNone(status['error']);r.close()
if __name__=='__main__':unittest.main(verbosity=2)
