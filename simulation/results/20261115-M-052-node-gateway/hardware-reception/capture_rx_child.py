import sys,json,time,importlib.util
from pathlib import Path
sys.path.insert(0,r"D:\Multi-Agent Network\.worktrees\production\app\flash")
from serial_adapter import Board
path=Path(r"D:\Multi-Agent Network\.worktrees\production\app\services\firmware\mid_baseline\field_agent\lora_ref\decoder.py");spec=importlib.util.spec_from_file_location("codec",path);codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(codec)
r={"node_id":"90:da:72:48:a4:f8","duration_seconds":25,"reports":[],"errors":[],"commands_sent":1}
try:
 board=Board("COM8");wire=board.wire
 try:
  info=board.info()
  if info.get("node_id","").lower()!=r["node_id"] or info.get("boot_id")!=2469683011:raise RuntimeError("identity or boot changed")
  end=time.monotonic()+25
  while time.monotonic()<end:
   raw=wire.readline(2049)
   if not raw:continue
   try:
    line=raw.decode("utf-8");value=json.loads(line)
    if value.get("schema")!="lora.ref.v1" or value.get("event")!="lora_ref_rx":continue
    event=codec.decode_serial_line(line)
    if event["gateway_id"].lower()!=r["node_id"]:raise ValueError("gateway identity mismatch")
    report=event["report"];r["reports"].append({"observer_id":report["observer_id"],"observer_boot":report["observer_boot"],"report_seq":report["report_seq"],"gateway_boot":event["gateway_boot"],"rx_seq":event["rx_seq"],"received_at_ms":event["received_at_ms"],"lora":event["lora"],"frame_hex":event["frame_hex"],"received_pc_monotonic":time.monotonic()})
   except (ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as e:r["errors"].append(type(e).__name__)
 finally:board.close()
 r["outcome"]="completed"
except Exception as e:r["outcome"]="failed";r["error_type"]=type(e).__name__;r["error"]=str(e)
print(json.dumps(r,ensure_ascii=False),flush=True)
sys.exit(0 if r["outcome"]=="completed" else 1)
