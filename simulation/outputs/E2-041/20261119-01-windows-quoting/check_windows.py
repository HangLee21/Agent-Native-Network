import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
root=pathlib.Path(r'D:\Multi-Agent Network');path=root/'tools/mid_baseline/gateway_probe/start_frontend.py';spec=importlib.util.spec_from_file_location('start_frontend',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Checks(unittest.TestCase):
 def test_real_start_process_paths_and_exit(self):
  parent=root/'simulation/outputs/E2-041/20261119-01-windows-quoting'
  with tempfile.TemporaryDirectory(prefix="space and 'quote' ",dir=parent) as temp:
   folder=pathlib.Path(temp);script=folder/"safe ' inner.ps1";script.write_text('param([string]$Out,[string]$Value,[int]$Code)\n@{value=$Value;script=$PSCommandPath} | ConvertTo-Json -Compress | Set-Content -LiteralPath $Out -Encoding UTF8\nexit $Code\n',encoding='utf8');resultfile=folder/'output result.json';value="test 'quote' \u4e2d\u6587 $dollar"
   for code in (0,23):
    result=module.run_netmode_script(script,['-Out',str(resultfile),'-Value',value,'-Code',str(code)],elevate=False,timeout=20)
    self.assertEqual(result.returncode,code,result.stderr);contents=json.loads(resultfile.read_text(encoding='utf-8-sig'));self.assertEqual(contents['value'],value);self.assertEqual(pathlib.Path(contents['script']),script)
 def test_failure_returns_without_polling(self):
  with patch.object(module,'gateway_nic_present',return_value=False) as nic,patch.object(module,'run_netmode_script',return_value=type('R',(),dict(returncode=23,stderr='failed',stdout=''))()),patch.object(module.time,'sleep') as sleep:
   self.assertFalse(module.ensure_lab_mode());self.assertEqual(nic.call_count,1);sleep.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
