"""Offline default-entry tests. No real browser, receiver, NIC or field-device startup."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('vue_default_launcher', ROOT / 'tools/release/start_vue_studio.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def test_legacy_cmd_is_exact_original_bytes(self):
        self.assertEqual(hashlib.sha256((ROOT/'START_STUDIO_LEGACY.cmd').read_bytes()).hexdigest(),
                         '40074f56fdfcb569a0902bc7fe0bcb83c3c98eb58df39944f4888494b7b2dbcf')

    def test_real_preview_requires_baseline_and_no_mock(self):
        source = {'schema':'baseline.frontend.import.v1'}
        config = {'schema':'network.config.v2', 'gatewayRelayPath':'/__network_gateway'}
        with patch.object(launcher, 'http_json', side_effect=[source,config,{'enabled':False},source]):
            self.assertTrue(launcher.real_preview(ROOT,10518))
        with patch.object(launcher, 'http_json', side_effect=[source,config,{'enabled':True},source]):
            self.assertFalse(launcher.real_preview(ROOT,10518))

    def test_real_preview_rejects_other_checkout(self):
        source = {'schema':'baseline.frontend.import.v1'}
        with patch.object(launcher, 'http_json', side_effect=[source,{'schema':'network.config.v2','gatewayRelayPath':'/__network_gateway'},{'enabled':False},None]):
            self.assertFalse(launcher.real_preview(ROOT,10518))

    def test_real_preview_rejects_missing_identity(self):
        with patch.object(launcher, 'http_json', return_value=None):
            self.assertFalse(launcher.real_preview(ROOT,10518))

    def test_known_services_are_reused(self):
        with patch.object(launcher, 'http_json', return_value={'schema':'lora.topology.v1'}), patch.object(launcher.subprocess,'call') as child:
            self.assertEqual(launcher.ensure_services(ROOT),0)
            child.assert_not_called()

    def test_unknown_backend_port_is_not_replaced(self):
        with patch.object(launcher,'http_json',return_value=None),patch.object(launcher,'port_open',return_value=True),patch.object(launcher.subprocess,'call') as child:
            with self.assertRaises(RuntimeError): launcher.ensure_services(ROOT)
            child.assert_not_called()

    def test_missing_services_use_old_backend_headless_without_nic_changes(self):
        with patch.object(launcher,'http_json',return_value=None),patch.object(launcher,'port_open',return_value=False),patch.object(launcher.subprocess,'call',return_value=0) as child:
            self.assertEqual(launcher.ensure_services(ROOT,'fresh output with spaces'),0)
            args=child.call_args.args[0]
            self.assertIn('--no-browser',args);self.assertIn('--skip-lab',args)
            self.assertEqual(args[-1],'fresh output with spaces')
            self.assertTrue(args[3].endswith('start_frontend.py'))

    def test_service_start_error_is_propagated(self):
        with patch.object(launcher,'port_open',return_value=False),patch.object(launcher,'ensure_services',return_value=17):
            self.assertEqual(launcher.main(['--no-browser']),17)

    def test_occupied_foreign_or_mock_web_port_stops_before_backend_actions(self):
        with patch.object(launcher,'port_open',return_value=True),patch.object(launcher,'real_preview',return_value=False),patch.object(launcher,'ensure_services') as services:
            self.assertEqual(launcher.main(['--no-browser']),1)
            services.assert_not_called()

    def test_existing_preview_no_browser_never_spawns(self):
        with patch.object(launcher,'port_open',return_value=True),patch.object(launcher,'real_preview',return_value=True),patch.object(launcher,'ensure_services',return_value=0),patch.object(launcher.subprocess,'call') as child,patch.object(launcher.webbrowser,'open') as browser:
            self.assertEqual(launcher.main(['--no-browser']),0)
            child.assert_not_called();browser.assert_not_called()

    def test_existing_preview_opens_only_studio_real_url(self):
        with patch.object(launcher,'port_open',return_value=True),patch.object(launcher,'real_preview',return_value=True),patch.object(launcher,'ensure_services',return_value=0),patch.object(launcher.webbrowser,'open') as browser:
            self.assertEqual(launcher.main(['--web-port','10518']),0)
            browser.assert_called_once_with('http://127.0.0.1:10518/studio.html')

    def test_invalid_port_stops_before_starting_anything(self):
        with patch.object(launcher,'ensure_services') as services:
            self.assertEqual(launcher.main(['--web-port','80','--no-browser']),1)
            services.assert_not_called()
        with patch.dict(os.environ,{'NETWORK_WEB_PORT':'invalid'}),patch.object(launcher,'ensure_services') as services:
            self.assertEqual(launcher.main(['--no-browser']),1)
            services.assert_not_called()

    @unittest.skipUnless(os.name=='nt','Windows CMD contract')
    def test_new_frontend_exit_code_and_port_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix='M064 launch space ') as directory:
            root=Path(directory);(root/'START_NETWORK_STUDIO.cmd').write_text('@exit /b 0\n')
            with patch.object(launcher,'port_open',return_value=False),patch.object(launcher,'ensure_services',return_value=0),patch.object(launcher.subprocess,'call',return_value=23) as child:
                self.assertEqual(launcher.main(['--no-browser','--web-port','10525'],root),23)
                self.assertEqual(child.call_args.kwargs['env']['NETWORK_WEB_PORT'],'10525')
                self.assertIn(str(root/'START_NETWORK_STUDIO.cmd'),child.call_args.args[0])

    @unittest.skipUnless(os.name=='nt','Windows CMD contract')
    def test_actual_cold_frontend_delegation_with_spaces_and_punctuation(self):
        with tempfile.TemporaryDirectory(prefix='M064 cold CMD space ') as directory:
            root=Path(directory)/'checkout & bang!';root.mkdir()
            (root/'START_NETWORK_STUDIO.cmd').write_bytes(b'@exit /b 23\r\n')
            with patch.object(launcher,'port_open',return_value=False),patch.object(launcher,'ensure_services',return_value=0):
                self.assertEqual(launcher.main(['--no-browser','--web-port','10525'],root),23)

    @unittest.skipUnless(os.name=='nt','Windows CMD contract')
    def test_real_cmd_quoting_arguments_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory(prefix='M064 CMD space ') as directory:
            root=Path(directory)/'checkout with spaces & bang!';(root/'tools/release').mkdir(parents=True)
            shutil.copyfile(ROOT/'START_STUDIO.cmd',root/'START_STUDIO.cmd')
            record=root/'args.json'
            (root/'tools/release/start_vue_studio.py').write_text('import json,sys\nfrom pathlib import Path\nPath(__file__).resolve().parents[2].joinpath("args.json").write_text(json.dumps(sys.argv[1:]),encoding="utf-8")\nraise SystemExit(23)\n',encoding='utf-8')
            cmd='"%s" /d /s /c ""%s" --no-browser --output "value with spaces and 中文""'%(os.environ.get('COMSPEC','cmd.exe'),root/'START_STUDIO.cmd')
            result=subprocess.run(cmd,cwd=directory,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            self.assertEqual(result.returncode,23)
            self.assertEqual(json.loads(record.read_text('utf-8')),['--no-browser','--output','value with spaces and 中文'])

    @unittest.skipUnless(os.name=='nt','Windows CMD contract')
    def test_packaged_dispatch_is_preserved_without_vue_files(self):
        with tempfile.TemporaryDirectory(prefix='M064 packaged space ') as directory:
            root=Path(directory);(root/'app/start').mkdir(parents=True)
            shutil.copyfile(ROOT/'START_STUDIO.cmd',root/'START_STUDIO.cmd')
            (root/'app/start/launcher.py').write_text('raise SystemExit(17)\n',encoding='utf-8')
            cmd='"%s" /d /s /c ""%s" --no-browser"'%(os.environ.get('COMSPEC','cmd.exe'),root/'START_STUDIO.cmd')
            result=subprocess.run(cmd,cwd=directory,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            self.assertEqual(result.returncode,17)


if __name__=='__main__':
    unittest.main()
