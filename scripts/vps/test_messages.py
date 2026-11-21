import json
import sqlite3
import urllib.request

# Test RPC messages for a lead
def rpc(command, args):
    data = json.dumps({"command": command, "args": args}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8787/api/rpc", data=data,
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())

# Get leads
leads = rpc("leads", {})["result"]
print("TOTAL LEADS:", len(leads))
if leads:
    lid = leads[0]["id"]
    print("LEAD:", leads[0]["name"], leads[0]["contact"])
    msgs = rpc("messages", {"id": lid})["result"]
    print("MESSAGES:", len(msgs))
    for m in msgs[:5]:
        print("  ", m)
else:
    print("NO LEADS")
