"""H013 fault check: failed serial cleanup must still close and retain unknown stop."""
import io,time
from adapter import _cleanup
class Wire:
 def __init__(self):self.ports={'aa':io.BytesIO(),'bb':io.BytesIO()};self.raw={};self.log=io.BytesIO();self.lease=None;self.tx={'aa':[],'bb':[]};self.replies={};self.calls=[]
 def submit(self,mac,cmd):self.calls.append(mac)
 def poll(self):raise RuntimeError('synthetic port failure')
 def close(self):
  for p in self.ports.values():p.close()
  self.log.close()
w=Wire();stopped,errors=_cleanup(w,'test',time.monotonic()+.1)
assert w.calls==['aa','bb'] and not stopped and errors and all(p.closed for p in w.ports.values()) and w.log.closed
print('PASS synthetic cleanup failure closes all handles, attempts both stops, preserves unconfirmed state')
