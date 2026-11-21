import json
import urllib.request

def rpc(command, args):
    data = json.dumps({"command": command, "args": args}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8787/api/rpc", data=data,
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())

# Verifica se o painel consegue chamar messages
leads = rpc("leads", {})["result"]
print("TOTAL LEADS:", len(leads))

# Encontra um lead com mensagens
for l in leads:
    msgs = rpc("messages", {"id": l["id"]})["result"]
    if msgs:
        print(f"\nLEAD COM MSGS: {l['id']} {l['name']} ({len(msgs)} msgs)")
        for m in msgs[:3]:
            print(f"  role={m[0]} text={m[1][:60]}")
        break
else:
    print("NENHUM LEAD COM MSGS")
