import hashlib,json,os,shutil,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PKG=ROOT/'.local/mid/E1-016/package-01'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class NativePackageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=Path(os.environ['E2_MID_TEST_OUTPUT']);m=PKG/'PACKAGE_MANIFEST.json'
  if sha(m)!='d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683':raise RuntimeError('package drift')
  v=json.loads(m.read_text());assert len(v['files'])==52
  for x in v['files']:
   p=(PKG/x['path']).resolve();assert p.is_relative_to(PKG.resolve()) and sha(p)==x['sha256'] and p.stat().st_size==x['bytes']
  f=ROOT/'firmware/mid_baseline/FREEZE.json';assert sha(f)=='95e7499f8e5c1469af4a36b29b52e5522a44bf9e19a17497df559dd58d686f40'
  cls.inputs=json.loads(f.read_text())['source_hashes'];assert all(sha(ROOT/n)==h for n,h in cls.inputs.items())
  src=cls.out/'native-source';src.mkdir()
  paths=['firmware/mid_baseline/idf/main/app_main.c','firmware/mid_baseline/mid.c','firmware/mid_baseline/mid.h','firmware/mid_display/include/mid_display.h','firmware/mid_display/src/mid_display_model.c']
  for n in paths:shutil.copyfile(ROOT/n,src/Path(n).name)
  sdk=ROOT/'.local/espnow/E1-015/sdk/esp-idf-v5.5.1/components/json/cJSON'
  for n in ['cJSON.c','cJSON.h']:shutil.copyfile(sdk/n,src/n)
  own=Path(__file__).parent;shutil.copyfile(own/'native_platform.h',src/'native_platform.h')
  for n in ['freertos/FreeRTOS.h','freertos/task.h','freertos/queue.h','esp_wifi.h','esp_now.h','esp_event.h','esp_netif.h','esp_timer.h','esp_random.h','esp_mac.h','nvs_flash.h']:
   p=src/n;p.parent.mkdir(exist_ok=True);p.write_text('#include "native_platform.h"\n')
  cls.exe=cls.out/'native_app_probe.exe';cmd=[shutil.which('gcc'),'-std=c11','-Wall','-Wextra','-Werror','-I'+str(src),'-DMID_BUILD_ID="mid-v1-99e77eba7e472bd687ea18321d6ac566e9e8b21d764431e1b42ec7fee945c2f3"',str(own/'native_app_probe.c'),str(src/'mid.c'),str(src/'mid_display_model.c'),str(src/'cJSON.c'),'-o',str(cls.exe)]
  p=subprocess.run(cmd,capture_output=True,timeout=30);(cls.out/'compile.stdout').write_bytes(p.stdout);(cls.out/'compile.stderr').write_bytes(p.stderr)
  (cls.out/'native_build.json').write_text(json.dumps(dict(command=cmd,exit_code=p.returncode,source_hashes={str(p.relative_to(cls.out)):sha(p) for p in src.rglob('*') if p.is_file()},package_manifest_sha256=sha(m),E1_source_hashes=cls.inputs,ESP_target_compilation=False,hardware_operations=0),indent=2))
  if p.returncode:raise RuntimeError('native host probe compile failed')
  p=subprocess.run([str(cls.exe),'0'],capture_output=True,timeout=5);(cls.out/'native-A.stdout').write_bytes(p.stdout);(cls.out/'native-A.stderr').write_bytes(p.stderr)
  if p.returncode:raise RuntimeError('native A probe failed')
  cls.A=p.stdout.decode();cls.wires=[json.loads(s)['probe_wire_hex'] for s in cls.A.splitlines() if s.startswith('{"probe_wire_hex"')]
  assert len(cls.wires)==5;(cls.out/'A-data-wires.txt').write_text('\n'.join(cls.wires)+'\n')
 @classmethod
 def tearDownClass(cls):assert all(sha(ROOT/n)==h for n,h in cls.inputs.items())
 def rows(self,text):return [json.loads(s) for s in text.splitlines() if s.startswith('{') and 'mid.serial.v1' in s]
 def invoke(self,mode):
  cmd=[str(self.exe),str(mode)]+([str(self.out/'A-data-wires.txt')] if mode==1 else []);p=subprocess.run(cmd,capture_output=True,timeout=5)
  (self.out/f'native-{mode}.stdout').write_bytes(p.stdout);(self.out/f'native-{mode}.stderr').write_bytes(p.stderr);self.assertEqual(p.returncode,0,p.stderr.decode());return self.rows(p.stdout.decode())
 def test_native_command_parser_and_source(self):
  rows=self.rows(self.A);self.assertEqual(sum(r['event']=='tx_queued' and 'dst'in r for r in rows),5)
  self.assertTrue(any(r.get('cmd')=='send' and r.get('error')=='inactive_or_no_config' for r in rows))
  self.assertTrue(any(r.get('event')=='command_result' and r.get('ok') is False and r.get('nonce') is None for r in rows))
  self.assertTrue(all(r.get('destination_confirmed') is False for r in rows if r['event']=='tx_link_ok'))
 def test_actual_source_wire_to_actual_destination_rx(self):
  rows=self.invoke(1);rx=[r for r in rows if r['event']=='rx_local'];self.assertEqual(len(rx),5)
  self.assertEqual([r['seq'] for r in rx],[1,2,3,4,5]);self.assertTrue(all(r['origin_boot']==101 and r['origin']=='90:da:72:48:a4:f8' and len(bytes.fromhex(r['payload_hex']))==16 for r in rx))
 def test_B_is_also_a_source(self):self.assertEqual(sum(r['event']=='tx_queued' and r.get('flow')==1 for r in self.invoke(2)),5)
 def test_missing_callback_locks_without_automatic_restart(self):
  rows=self.invoke(3);self.assertTrue(any(r['event']=='callback_timeout' for r in rows));self.assertTrue(any(r.get('nonce')=='restart' and r.get('error')=='busy_or_locked' for r in rows))
