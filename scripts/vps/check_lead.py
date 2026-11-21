import sqlite3
c = sqlite3.connect('/var/lib/agente-vendas-local/sales_agent.sqlite3')
print("Highest ID lead:", c.execute("SELECT id, name FROM leads ORDER BY id DESC LIMIT 1").fetchone())
print("Messages for that lead:", c.execute("SELECT count(*) FROM conversations WHERE lead_id = (SELECT id FROM leads ORDER BY id DESC LIMIT 1)").fetchone())
# Check a lead with messages
row = c.execute("SELECT lead_id FROM conversations GROUP BY lead_id ORDER BY count(*) DESC LIMIT 1").fetchone()
print("Lead with most messages:", row)
if row:
    lid = row[0]
    print("Lead name:", c.execute("SELECT name FROM leads WHERE id=?", (lid,)).fetchone())
    print("Message count:", c.execute("SELECT count(*) FROM conversations WHERE lead_id=?", (lid,)).fetchone())
