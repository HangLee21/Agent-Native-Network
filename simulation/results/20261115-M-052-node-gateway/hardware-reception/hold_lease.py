import sys,time
sys.path.insert(0,r"D:\Multi-Agent Network")
from tools.mid_hardware.console.lease import HardwareLease
with HardwareLease("H024"):
 print("H024_LEASE_HELD",flush=True)
 time.sleep(55)
