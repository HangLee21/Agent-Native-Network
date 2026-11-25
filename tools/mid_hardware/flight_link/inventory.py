"""H-021 single serial inventory; only info and status commands, no gateway."""
import datetime,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'.worktrees/production/production/flash'))
from serial_adapter import Board,ports
from tools.mid_hardware.console.lease import HardwareLease

def main():
 out=ROOT/'simulation/outputs/H-021'/('inventory-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir(parents=True,exist_ok=False)
 result={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ports':[],'device_commands':['info','field_status','lora_ref_status'],'flash_writes':0,'configuration_writes':0,'gateway_probes':0}
 try:
  with HardwareLease('H021'):
   for port in ports():
    row={'port':port};board=None
    try:
     board=Board(port)
     for cmd in ('info','field_status','lora_ref_status'):
      try:
       data=board.info() if cmd=='info' else board.command(cmd)
       fields=('node_id','node_mac','boot_id','build_id','firmware','chip','node_number','node_number_source','discovery_saved','discovery_fault','discovery_autostart','group','channel','configured','start_on_boot','running','radio','ip_enabled','lora_ref_requested_role','lora_ref_worker_state','frequency_hz','sf','bandwidth_hz','coding_rate','sync_word','report_period_ms','start_on_boot')
       row[cmd]={k:data[k] for k in fields if k in data}
      except Exception as exc: row[cmd+'_error']=str(exc)
    except Exception as exc: row['error']=str(exc)
    finally:
     if board: board.close()
    result['ports'].append(row)
 except Exception as exc: result['error']=str(exc)
 result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (out/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'output':str(out),'result':result},ensure_ascii=False))
if __name__=='__main__':main()
