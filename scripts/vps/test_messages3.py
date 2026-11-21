import json
import urllib.request

def rpc(command, args):
    data = json.dumps({"command": command, "args": args}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8787/api/rpc", data=data,
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())

# Test messages for lead 281 (which has 5 msgs)
result = rpc("messages", {"id": 281})
print("RESULT:", json.dumps(result, ensure_ascii=False)[:500])
print()
# Test leads
leads = rpc("leads", {})["result"]
print("LEADS COUNT:", len(leads))
print("FIRST LEAD:", json.dumps(leads[0] if leads else {}, ensure_ascii=False)[:200])
