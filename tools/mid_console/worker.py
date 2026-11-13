"""Fixed, stdin-only planner entry point; never opens devices."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.mid_baseline.planner.console.plans import PlanLibrary

if __name__ == '__main__':
    data = json.load(sys.stdin)
    lib = PlanLibrary(ROOT)
    if data.get('catalog'):
        result = lib.list_models()
    else:
        result = lib.plan(data['request'], available_nodes=data.get('available_nodes'),
                          live_status=data.get('live_status'))
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
