import json,sys,time
sys.path.insert(0,r"D:\Multi-Agent Network\.worktrees\production\app\flash")
from serial_adapter import Board
r={"port":"COM8","commands":[],"configuration_attempted":False,"flash_writes":0}
try:
 b=Board("COM8")
 try:
  r["commands"].append("info");i=b.info()
  if str(i.get("node_id","")).lower()!="90:da:72:48:a4:f8" or i.get("boot_id")!=2469683011 or i.get("lora_ref_api")!=1:raise RuntimeError("node identity or boot changed; no config")
  r["commands"].append("lora_ref_status");before=b.command("lora_ref_status");r["before"]=before
  expected={"lora_ref_requested_role":"tx","start_on_boot":True,"report_period_ms":10000,"jitter_ms":250,"frequency_hz":470500000,"tx_power_dbm":0,"sync_word":52,"preamble_symbols":8,"sf":7,"bandwidth_hz":125000,"coding_rate":5}
  if any(before.get(k)!=v for k,v in expected.items()):raise RuntimeError("configuration changed since backup; no config")
  r["configuration_attempted"]=True;r["commands"].append("lora_ref_config role=rx");r["config_result"]=b.command("lora_ref_config",role="rx")
  end=time.monotonic()+4
  while time.monotonic()<end:
   r["commands"].append("lora_ref_status");after=b.command("lora_ref_status");r["after"]=after
   if after.get("lora_ref_requested_role")=="rx" and after.get("lora_ref_worker_state")==1 and after.get("requested_generation")==after.get("applied_generation"):break
   time.sleep(.2)
  else:raise RuntimeError("RX role not confirmed applied")
  if any(after.get(k)!=v for k,v in expected.items() if k!="lora_ref_requested_role"):raise RuntimeError("other LoRa parameters changed")
  r["outcome"]="rx_confirmed"
 finally:b.close()
except Exception as e:r["outcome"]="failed";r["error_type"]=type(e).__name__;r["error"]=str(e)
print(json.dumps(r,ensure_ascii=False),flush=True)
sys.exit(0 if r["outcome"]=="rx_confirmed" else 1)
