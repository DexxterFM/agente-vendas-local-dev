import sqlite3
c = sqlite3.connect('/var/lib/agente-vendas-local/sales_agent.sqlite3')
print("SCHEMA:")
print(c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='conversations'").fetchone()[0])
print("---")
print("conversations count:", c.execute("SELECT count(*) FROM conversations").fetchone()[0])
print("leads count:", c.execute("SELECT count(*) FROM leads").fetchone()[0])
print("conversations with lead_id not in leads:", c.execute("SELECT count(*) FROM conversations WHERE lead_id NOT IN (SELECT id FROM leads)").fetchone()[0])
# Show sample
print("\nSample conversations:")
for row in c.execute("SELECT * FROM conversations LIMIT 3").fetchall():
    print("  ", row)
print("\nSample leads:")
for row in c.execute("SELECT id, name FROM leads LIMIT 3").fetchall():
    print("  ", row)
# Check if messages are being stored with correct lead_id
print("\nLeads with conversations:")
for row in c.execute("SELECT lead_id, count(*) as n FROM conversations GROUP BY lead_id ORDER BY n DESC LIMIT 5").fetchall():
    print("  ", row)
