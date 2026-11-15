import json,sys,datetime
from pathlib import Path
root=Path(r"D:\Multi-Agent Network");sys.path.insert(0,str(root));sys.path.insert(0,str(root/".worktrees/production/app/flash"))
from tools.mid_hardware.console.lease import HardwareLease
from serial_adapter import Board
out=Path(__file__).resolve().parent; result={"port":"COM8","expected_node":"90:da:72:48:a4:f8","started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"commands":[],"config_written":False,"flash_writes":0}
try:
 with HardwareLease("H024"):
  b=Board("COM8")
  try:
   result["commands"].append("info");info=b.info();result["info"]=info
   if str(info.get("node_id","")).lower()!=result["expected_node"]:raise RuntimeError("node identity mismatch; no further commands")
   if info.get("lora_ref_api")!=1:raise RuntimeError("LoRa reference API unavailable; no further commands")
   result["commands"].append("lora_ref_status");result["lora_before"]=b.command("lora_ref_status")
   result["outcome"]="identity_and_status_read"
  finally:b.close()
except Exception as exc:result["outcome"]="failed";result["error_type"]=type(exc).__name__;result["error"]=str(exc)
finally:
 result["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
 try:(out/("identity-status-"+str(__import__("os").getpid())+".json")).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
 except OSError:pass
print(json.dumps(result,ensure_ascii=False))
sys.exit(0 if result["outcome"]=="identity_and_status_read" else 1)
