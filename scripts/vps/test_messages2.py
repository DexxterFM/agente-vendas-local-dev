import json
import sqlite3
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
with_msgs = 0
for l in leads[:20]:
    msgs = rpc("messages", {"id": l["id"]})["result"]
    if msgs:
        with_msgs += 1
        print(f"  LEAD {l['id']} {l['name']}: {len(msgs)} msgs")
        for m in msgs[:3]:
            print(f"    {m}")
print(f"\nLeads com mensagens (dos 20 primeiros): {with_msgs}")
# Check DB directly
c = sqlite3.connect("/var/lib/agente-vendas-local/sales_agent.sqlite3")
print("\nDB conversations count:", c.execute("select count(*) from conversations").fetchone()[0])
print("DB leads count:", c.execute("select count(*) from leads").fetchone()[0])
# Check a lead with conversations
rows = c.execute("select lead_id, count(*) as n from conversations group by lead_id order by n desc limit 5").fetchall()
print("Top leads by conversation count:", rows)
