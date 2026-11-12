from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import urllib.request
import uuid
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk
from sales_logic import draft_followup, qualify_lead

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")
BROWSEROS_MCP_URL = os.getenv("BROWSEROS_MCP_URL", "http://127.0.0.1:9210/mcp")
DB_PATH = os.path.join(os.path.dirname(__file__), "sales_agent.sqlite3")


def post(url: str, payload: dict, headers: dict | None = None) -> tuple[dict, str]:
    request = urllib.request.Request(url, json.dumps(payload).encode(), method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=60) as response:
        return dict(response.headers), response.read().decode("utf-8", "replace")


def sse_json(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data: {"):
            return json.loads(line[6:])
    raise RuntimeError("Resposta MCP inválida")


class Memory:
    def __init__(self, db_path: str | None = None) -> None:
        self.db = sqlite3.connect(db_path or DB_PATH, check_same_thread=False)
        self.db.execute("create table if not exists messages (id integer primary key, role text, content text, created_at text)")
        self.db.execute("create table if not exists leads (id integer primary key, name text not null, contact text, stage text not null default 'new', notes text, created_at text not null)")
        self.db.execute("create table if not exists products (id integer primary key, name text not null, price real, active integer not null default 1, created_at text not null)")
        self.db.execute("create table if not exists opportunities (id integer primary key, lead_id integer not null, product_id integer, stage text not null default 'qualification', value real, next_action text, created_at text not null)")
        self.db.execute("create table if not exists followups (id integer primary key, lead_id integer not null, due_at text not null, task text not null, done integer not null default 0, created_at text not null)")
        self.db.commit()

    def add(self, role: str, content: str) -> None:
        self.db.execute("insert into messages(role,content,created_at) values(?,?,?)", (role, content, datetime.now(timezone.utc).isoformat()))
        self.db.commit()

    def recent(self, limit: int = 12) -> list[tuple[str, str]]:
        return list(reversed(self.db.execute("select role,content from messages order by id desc limit ?", (limit,)).fetchall()))

    def add_lead(self, name: str, contact: str = "", notes: str = "") -> int:
        cursor = self.db.execute("insert into leads(name,contact,notes,created_at) values(?,?,?,?)", (name, contact, notes, datetime.now(timezone.utc).isoformat()))
        self.db.commit()
        return int(cursor.lastrowid)

    def list_leads(self) -> list[tuple]:
        return self.db.execute("select id,name,contact,stage,notes from leads order by id desc").fetchall()

    def get_lead(self, lead_id: int) -> tuple | None:
        return self.db.execute("select id,name,contact,stage,notes from leads where id=?", (lead_id,)).fetchone()

    def update_lead_stage(self, lead_id: int, stage: str, notes: str = "") -> None:
        self.db.execute("update leads set stage=?, notes=? where id=?", (stage, notes, lead_id))
        self.db.commit()

    def add_product(self, name: str, price: float | None = None) -> int:
        cursor = self.db.execute("insert into products(name,price,created_at) values(?,?,?)", (name, price, datetime.now(timezone.utc).isoformat()))
        self.db.commit()
        return int(cursor.lastrowid)

    def add_opportunity(self, lead_id: int, product_id: int | None = None, value: float | None = None, next_action: str = "") -> int:
        cursor = self.db.execute("insert into opportunities(lead_id,product_id,value,next_action,created_at) values(?,?,?,?,?)", (lead_id, product_id, value, next_action, datetime.now(timezone.utc).isoformat()))
        self.db.commit()
        return int(cursor.lastrowid)

    def add_followup(self, lead_id: int, due_at: str, task: str) -> int:
        cursor = self.db.execute("insert into followups(lead_id,due_at,task,created_at) values(?,?,?,?)", (lead_id, due_at, task, datetime.now(timezone.utc).isoformat()))
        self.db.commit()
        return int(cursor.lastrowid)


class BrowserOS:
    def __init__(self) -> None:
        headers, _ = post(BROWSEROS_MCP_URL, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2026-07-28", "capabilities": {}, "clientInfo": {"name": "sales-agent-unified", "version": "0.1"}}}, {"Accept": "application/json, text/event-stream"})
        self.session = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
        if not self.session:
            raise RuntimeError("BrowserOS MCP não devolveu sessão")

    def run(self, code: str) -> dict:
        _, body = post(BROWSEROS_MCP_URL, {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/call", "params": {"name": "run", "arguments": {"code": code, "timeout": 30000, "maxChars": 10000}}}, {"Accept": "application/json, text/event-stream", "mcp-session-id": self.session})
        result = sse_json(body)
        if "error" in result:
            raise RuntimeError(result["error"].get("message", "Erro BrowserOS"))
        return result.get("result", {})


SYSTEM = ("Você é o agente de vendas local. Responda apenas JSON válido.\n"
          "Formato: {\\\"action\\\":\\\"answer\\\",\\\"text\\\":\\\"...\\\"} ou "
          "{\\\"action\\\":\\\"navigate\\\",\\\"url\\\":\\\"https://...\\\"}.\n"
          "Use navigate somente para URL HTTPS fornecida pelo usuário. Não faça login, "
          "envie mensagens, compre, publique, exclua ou altere dados.\n"
          "Seja cordial, objetivo, consultivo e nunca invente preço, prazo ou condição.\n"
          "Qualifique o interesse, identifique a necessidade e proponha o próximo passo.")


def parse_decision(content: str) -> dict:
    """Extrai a decisão JSON sem permitir que texto livre vire ação externa."""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {"action": "answer", "text": content.strip()}
    try:
        decision = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"action": "answer", "text": content.strip()}
    if decision.get("action") not in {"answer", "navigate"}:
        return {"action": "answer", "text": "Ação não autorizada nesta versão."}
    return decision


class Agent:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def run(self, text: str) -> str:
        messages = [{"role": "system", "content": SYSTEM}]
        messages.extend({"role": role, "content": content} for role, content in self.memory.recent())
        messages.append({"role": "user", "content": text})
        _, body = post(OLLAMA_URL, {"model": OLLAMA_MODEL, "stream": False, "messages": messages})
        content = json.loads(body)["message"]["content"]
        decision = parse_decision(content)
        if decision.get("action") != "navigate":
            return str(decision.get("text", "Não consegui concluir a solicitação."))
        url = str(decision.get("url", ""))
        if not url.lower().startswith("https://"):
            return "Por segurança, somente URLs HTTPS são permitidas."
        result = BrowserOS().run(f"const page = await browser.open({json.dumps(url)}); return await page.read();")
        return json.dumps(result, ensure_ascii=False)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Agente de Vendas Local")
        self.geometry("980x680")
        self.memory = Memory()
        self.agent = Agent(self.memory)
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="Agente de Vendas Local", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
        ttk.Label(self, text=f"Ollama: {OLLAMA_MODEL} | BrowserOS MCP: {BROWSEROS_MCP_URL}").pack(anchor="w", padx=18, pady=(0, 10))
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=18, pady=8)
        chat_frame = ttk.Frame(notebook)
        crm_frame = ttk.Frame(notebook)
        notebook.add(chat_frame, text="Conversa")
        notebook.add(crm_frame, text="CRM")

        self.chat = tk.Text(chat_frame, wrap="word", state="disabled", font=("Segoe UI", 11))
        self.chat.pack(fill="both", expand=True, pady=8)
        bottom = ttk.Frame(chat_frame)
        bottom.pack(fill="x", pady=8)
        self.input = ttk.Entry(bottom)
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Return>", lambda _: self.send())
        ttk.Button(bottom, text="Enviar", command=self.send).pack(side="left", padx=(8, 0))

        form = ttk.LabelFrame(crm_frame, text="Novo lead")
        form.pack(fill="x", padx=8, pady=8)
        ttk.Label(form, text="Nome").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Label(form, text="Contato").grid(row=0, column=2, padx=6, pady=6, sticky="w")
        self.lead_name = ttk.Entry(form, width=30)
        self.lead_contact = ttk.Entry(form, width=24)
        self.lead_name.grid(row=0, column=1, padx=6, pady=6)
        self.lead_contact.grid(row=0, column=3, padx=6, pady=6)
        ttk.Button(form, text="Salvar lead", command=self.save_lead).grid(row=0, column=4, padx=8, pady=6)
        ttk.Label(form, text="Mensagem para qualificar").grid(row=1, column=0, padx=6, pady=6, sticky="w")
        self.lead_message = ttk.Entry(form, width=58)
        self.lead_message.grid(row=1, column=1, columnspan=3, padx=6, pady=6, sticky="ew")
        ttk.Button(form, text="Qualificar selecionado", command=self.qualify_selected).grid(row=1, column=4, padx=8, pady=6)
        self.leads_tree = ttk.Treeview(crm_frame, columns=("id", "name", "contact", "stage", "notes"), show="headings")
        for column, label, width in (("id", "ID", 50), ("name", "Nome", 220), ("contact", "Contato", 170), ("stage", "Etapa", 120), ("notes", "Notas", 260)):
            self.leads_tree.heading(column, text=label)
            self.leads_tree.column(column, width=width)
        self.leads_tree.pack(fill="both", expand=True, padx=8, pady=8)
        actions = ttk.Frame(crm_frame)
        actions.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(actions, text="Gerar follow-up", command=self.generate_followup).pack(side="left")
        ttk.Button(actions, text="Atualizar lista", command=self.refresh_leads).pack(side="right")
        self.refresh_leads()
        self._write("Sistema", "Aplicação pronta. O modelo e o navegador são locais.")

    def save_lead(self) -> None:
        name = self.lead_name.get().strip()
        contact = self.lead_contact.get().strip()
        if not name:
            self._write("CRM", "Informe o nome do lead antes de salvar.")
            return
        self.memory.add_lead(name, contact)
        self.lead_name.delete(0, "end")
        self.lead_contact.delete(0, "end")
        self.refresh_leads()
        self._write("CRM", f"Lead salvo: {name}")

    def refresh_leads(self) -> None:
        if not hasattr(self, "leads_tree"):
            return
        for item in self.leads_tree.get_children():
            self.leads_tree.delete(item)
        for lead in self.memory.list_leads():
            self.leads_tree.insert("", "end", values=lead)

    def _selected_lead(self) -> tuple | None:
        selected = self.leads_tree.selection()
        if not selected:
            return None
        values = self.leads_tree.item(selected[0], "values")
        return self.memory.get_lead(int(values[0]))

    def qualify_selected(self) -> None:
        lead = self._selected_lead()
        message = self.lead_message.get().strip()
        if not lead:
            self._write("CRM", "Selecione um lead antes de qualificar.")
            return
        if not message:
            self._write("CRM", "Informe a mensagem recebida do lead.")
            return
        result = qualify_lead(message)
        notes = f"score={result.score}; " + (", ".join(result.reasons) or "sem sinais detectados")
        self.memory.update_lead_stage(int(lead[0]), result.stage, notes)
        self.refresh_leads()
        self._write("CRM", f"{lead[1]} classificado como {result.stage} ({result.score}/100). {notes}")

    def generate_followup(self) -> None:
        lead = self._selected_lead()
        if not lead:
            self._write("CRM", "Selecione um lead para gerar o follow-up.")
            return
        product = "seu produto"
        draft = draft_followup(str(lead[1]), product, str(lead[3]))
        self._write("CRM", f"Rascunho (não enviado): {draft}")

    def _write(self, role: str, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", f"\n{role}:\n{text}\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def send(self) -> None:
        text = self.input.get().strip()
        if not text:
            return
        self.input.delete(0, "end")
        self._write("Você", text)
        self.memory.add("user", text)
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text: str) -> None:
        try:
            answer = self.agent.run(text)
            self.memory.add("assistant", answer)
            self.after(0, lambda: self._write("Agente", answer))
        except Exception as exc:
            self.after(0, lambda: self._write("Erro", str(exc)))


if __name__ == "__main__":
    App().mainloop()
