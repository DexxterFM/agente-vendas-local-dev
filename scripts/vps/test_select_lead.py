import json
import urllib.request

def rpc(command, args):
    data = json.dumps({"command": command, "args": args}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8787/api/rpc", data=data,
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())

leads = rpc("leads", {})["result"]
print("TOTAL LEADS:", len(leads))

for l in leads:
    msgs = rpc("messages", {"id": l["id"]})["result"]
    if msgs:
        print("LEAD:", l["id"], l["name"], len(msgs), "msgs")
        for m in msgs[:3]:
            print("  role=", m[0], "text=", str(m[1])[:80])
        break
else:
    print("NENHUM LEAD COM MSGS")

result = rpc("messages", {"id": leads[0]["id"]})
print("Raw messages response for lead", leads[0]["id"], ":", json.dumps(result)[:300])