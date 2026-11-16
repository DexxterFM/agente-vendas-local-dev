"""Read-only aggregate prospecting status for operational diagnosis."""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.desktop_rpc import execute
state = execute('agentStatus', {})
print(json.dumps({key: state.get(key) for key in ('active', 'prospecting_active', 'automatic_replies')}, ensure_ascii=False))
