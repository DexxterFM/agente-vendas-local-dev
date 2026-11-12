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
    def __init__(self) -> None:
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.execute("create table if not exists messages (id integer primary key, role text, content text, created_at text)")
        self.db.commit()

    def add(self, role: str, content: str) -> None:
        self.db.execute("insert into messages(role,content,created_at) values(?,?,?)", (role, content, datetime.now(timezone.utc).isoformat()))
        self.db.commit()

    def recent(self, limit: int = 12) -> list[tuple[str, str]]:
        return list(reversed(self.db.execute("select role,content from messages order by id desc limit ?", (limit,)).fetchall()))


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
          "envie mensagens, compre, publique, exclua ou altere dados.")


class Agent:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def run(self, text: str) -> str:
        messages = [{"role": "system", "content": SYSTEM}]
        messages.extend({"role": role, "content": content} for role, content in self.memory.recent())
        messages.append({"role": "user", "content": text})
        _, body = post(OLLAMA_URL, {"model": OLLAMA_MODEL, "stream": False, "messages": messages})
        content = json.loads(body)["message"]["content"]
        match = re.search(r"\{.*\}", content, re.S)
        decision = json.loads(match.group(0)) if match else {"action": "answer", "text": content}
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
        self.chat = tk.Text(self, wrap="word", state="disabled", font=("Segoe UI", 11))
        self.chat.pack(fill="both", expand=True, padx=18, pady=8)
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=18, pady=16)
        self.input = ttk.Entry(bottom)
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Return>", lambda _: self.send())
        ttk.Button(bottom, text="Enviar", command=self.send).pack(side="left", padx=(8, 0))
        self._write("Sistema", "Aplicação pronta. O modelo e o navegador são locais.")

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
