import json,sys,tempfile,unittest,subprocess,types
from pathlib import Path
sys.path.insert(0,r"D:\Multi-Agent Network\.worktrees\production\app\gateway_setup")
import setup_gateway as g
class Diagnostics(unittest.TestCase):
 def test_stage_failure_and_privacy(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"run.jsonl";g.LOG_FILE=str(p)
   def runner(*a,**k):raise subprocess.CalledProcessError(255,["ssh","SECRET_PASSWORD"])
   with self.assertRaises(subprocess.CalledProcessError):g.run_step(runner,"ssh_enumerate",["ssh"],check=True)
   rows=[json.loads(x) for x in p.read_text().splitlines()];self.assertEqual(rows[-1]["exit_code"],255);self.assertEqual(rows[-1]["stage"],"ssh_enumerate");self.assertNotIn("SECRET_PASSWORD",p.read_text())
 def test_stage_success(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"run.jsonl";g.LOG_FILE=str(p);g.run_step(lambda *a,**k:types.SimpleNamespace(returncode=0),"scp_upload",[])
   self.assertEqual(json.loads(p.read_text().splitlines()[-1])["status"],"completed")
if __name__=="__main__":unittest.main(verbosity=2)
