"""Optional E2 subprocess boundary; JSON stdin/stdout, no device access."""
import json,sys
from plans import PlanLibrary

def main():
    try:
        text=sys.stdin.read(65537)
        if len(text)>65536:raise ValueError('input exceeds64KiB')
        envelope=json.loads(text)
        library=PlanLibrary()
        if envelope.get('action')=='models':result=dict(ok=True,models=library.list_models())
        else:result=library.plan(envelope['request'],available_nodes=envelope.get('available_nodes'),live_status=envelope.get('live_status'))
    except Exception as e:result=dict(ok=False,error=dict(code='planner_unavailable_or_invalid_input',message=str(e)))
    print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 0 if result.get('ok') else 2

if __name__=='__main__':raise SystemExit(main())
