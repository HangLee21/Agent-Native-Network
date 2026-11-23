import json,sys
sys.path.insert(0,r"D:\Multi-Agent Network\.worktrees\production\app\flash")
from serial_adapter import Board
r={"port":"COM8","commands":[],"config_written":False}
try:
 b=Board("COM8")
 try:
  r["commands"].append("info");r["info"]=b.info()
  if str(r["info"].get("node_id","")).lower()!="90:da:72:48:a4:f8":raise RuntimeError("identity mismatch; no further commands")
  if r["info"].get("lora_ref_api")!=1:raise RuntimeError("LoRa API unavailable")
  r["commands"].append("lora_ref_status");r["lora_before"]=b.command("lora_ref_status");r["outcome"]="ok"
 finally:b.close()
except Exception as e:r["outcome"]="failed";r["error_type"]=type(e).__name__;r["error"]=str(e)
print(json.dumps(r,ensure_ascii=False),flush=True)
sys.exit(0 if r["outcome"]=="ok" else 1)
