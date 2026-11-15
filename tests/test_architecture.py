import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from adapters.browseros import BrowserOSClient
from adapters.mcp import MCPClient, parse_mcp_body
from core.agent import Agent
from core.config import load_config
from core.memory import Memory
from core.persona import build_system_prompt, get_persona
from core.rea import analyze_project, latest_report
from core.supervisor import Supervisor
from core.tools import (
    ActionPolicy,
    extract_mcp_text,
    parse_raw_decision,
    validate_https_url,
)


class ToolsTests(unittest.TestCase):
    def test_https_url_allowlist(self):
        allowed, _ = validate_https_url("https://example.com/path?q=1")
        self.assertTrue(allowed)
        for url in (
            "http://example.com",
            "https://localhost/admin",
            "https://127.0.0.1/",
            "https://user:pass@example.com/",
        ):
            ok, _ = validate_https_url(url)
            self.assertFalse(ok, url)

    def test_extract_mcp_text_removes_untrusted_markers(self):
        result = {
            "structuredContent": {
                "value": (
                    "[UNTRUSTED_PAGE_CONTENT nonce=abc origin=https://example.com/] "
                    "Conteúdo da página "
                    "[END_UNTRUSTED_PAGE_CONTENT nonce=abc]"
                )
            }
        }
        text = extract_mcp_text(result, max_chars=1000)
        self.assertIn("Conteúdo da página", text)
        self.assertNotIn("UNTRUSTED_PAGE_CONTENT", text)

    def test_external_write_requires_confirmation(self):
        raw = parse_raw_decision('{"action":"send_message","text":"oi"}')
        self.assertEqual(raw["action"], "send_message")
        policy = ActionPolicy().evaluate(raw)
        self.assertEqual(policy.status, "confirmation_required")

    def test_sse_parser(self):
        body = (
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        )
        messages = parse_mcp_body(body)
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0]["result"]["ok"])


class MCPClientTests(unittest.TestCase):
    def test_session_metadata_and_tool_call(self):
        calls = []

        def poster(url, payload, headers, timeout):
            calls.append((payload, headers))
            method = payload["method"]
            if method == "initialize":
                return {"mcp-session-id": "sessao-teste"}, (
                    'data: {"jsonrpc":"2.0","id":1,"result":'
                    '{"protocolVersion":"2025-11-25"}}\n\n'
                )
            if method == "notifications/initialized":
                return {}, ""
            if method == "tools/call":
                return {}, (
                    'data: {"jsonrpc":"2.0","id":2,"result":{'
                    '"content":[{"type":"text","text":"ok"}],'
                    '"structuredContent":{"value":"[UNTRUSTED_PAGE_CONTENT nonce=x]'
                    'texto[END_UNTRUSTED_PAGE_CONTENT nonce=x]"}}}\n\n'
                )
            raise AssertionError(method)

        client = MCPClient(
            "http://127.0.0.1:9210/mcp",
            poster=poster,
            require_session=True,
        )
        result = client.call_tool("run", {"code": "return 1"})
        self.assertEqual(client.session_id, "sessao-teste")
        self.assertIn("structuredContent", result)
        initialize_payload, initialize_headers = calls[0]
        self.assertIn("io.modelcontextprotocol/protocolVersion", initialize_payload["params"]["_meta"])
        self.assertEqual(initialize_headers["Mcp-Method"], "initialize")
        tool_payload, tool_headers = calls[-1]
        self.assertEqual(tool_headers["Mcp-Method"], "tools/call")
        self.assertEqual(tool_headers["Mcp-Name"], "run")
        self.assertEqual(tool_payload["params"]["arguments"]["code"], "return 1")
        self.assertEqual(
            tool_payload["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"],
            "2025-11-25",
        )


class MemoryTests(unittest.TestCase):
    def test_extended_sales_entities_and_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "test.sqlite3")
            try:
                lead_id = memory.add_lead("Maria", "maria@example.com", "indicação")
                self.assertEqual(memory.get_lead(lead_id)[3:5], ("new", "indicação"))
                memory.add_customer("Maria", "maria@example.com", "Empresa X")
                consent_id = memory.add_consent(lead_id, "email", True, "autorizou por email")
                self.assertGreater(consent_id, 0)
                self.assertTrue(memory.latest_consent(lead_id)["granted"])
                followup_id = memory.add_followup(
                    lead_id,
                    "2030-01-01T10:00:00+00:00",
                    "Retornar",
                    draft="Olá, Maria!",
                    channel="email",
                )
                followup = memory.latest_followup(lead_id)
                self.assertEqual(followup["id"], followup_id)
                self.assertEqual(followup["draft"], "Olá, Maria!")
                self.assertEqual(followup["status"], "draft")
                self.assertEqual(followup["channel"], "email")
                pending_id = memory.create_pending_action(
                    "send_message", {"text": "oi"}, "teste de confirmação"
                )
                self.assertTrue(
                    any(row[0] == pending_id for row in memory.list_pending_actions())
                )
                memory.decide_pending_action(pending_id, False, "não enviar")
                self.assertEqual(memory.list_pending_actions(), [])
                actions = {row[2] for row in memory.list_audit(50)}
                self.assertIn("action.confirmation_required", actions)
                self.assertIn("action.decision", actions)
                memory.set_setting("persona", "conciso")
                self.assertEqual(memory.get_setting("persona"), "conciso")
                counts = memory.counts()
                self.assertGreaterEqual(counts["leads"], 1)
                self.assertGreaterEqual(counts["audit_events"], 1)
            finally:
                memory.close()

    def test_legacy_database_is_migrated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.sqlite3"
            db = sqlite3.connect(path)
            db.execute(
                "create table leads (id integer primary key, name text not null, "
                "contact text, stage text not null default 'new', notes text, "
                "created_at text not null)"
            )
            db.execute(
                "insert into leads(name,contact,stage,notes,created_at) "
                "values('Legado','','new','', '2026-01-01T00:00:00+00:00')"
            )
            db.commit()
            db.close()
            memory = Memory(path)
            try:
                detail = memory.get_lead_detail(1)
                self.assertEqual(detail["name"], "Legado")
                self.assertEqual(detail["score"], 0)
                self.assertTrue(detail["next_action"])
                self.assertEqual(memory.get_lead(1)[3:5], ("new", ""))
            finally:
                memory.close()


class SupervisorTests(unittest.TestCase):
    def test_start_services_does_not_duplicate_running_processes(self):
        calls = []
        supervisor = Supervisor(
            load_config(),
            port_checker=lambda _port: True,
            popen=lambda *args, **kwargs: calls.append(args),
        )
        # The packaged desktop version owns llama.cpp.  It must not launch a
        # second Ollama process or a separate browser process beside it.
        with patch.dict(os.environ, {"LOCAL_LLM_URL": "http://127.0.0.1:19090"}):
            results = supervisor.start_services()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Motor de IA embutido")
        self.assertTrue(results[0]["running"])
        self.assertEqual(calls, [])

    def test_health_shape(self):
        supervisor = Supervisor(load_config(), port_checker=lambda _port: True)
        supervisor._ollama_health = lambda: {
            "status": "connected",
            "detail": "ok",
            "meta": {},
        }
        supervisor._browser_health = lambda deep: {
            "status": "connected",
            "detail": "ok",
            "meta": {},
        }
        supervisor._memory_health = lambda: {
            "status": "connected",
            "detail": "ok",
            "meta": {},
        }
        supervisor._rea_health = lambda: {
            "status": "attention",
            "detail": "sem relatório",
            "meta": {},
        }
        health = supervisor.health(deep=True)
        for key in ("ollama", "model", "browseros", "memory", "rea", "privacy"):
            self.assertIn(key, health)
            self.assertIn("status", health[key])


class ReaTests(unittest.TestCase):
    def test_analyze_project_writes_evidence_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "core").mkdir()
            (root / "core" / "memory.py").write_text(
                "create table if not exists leads (id integer primary key)\n",
                encoding="utf-8",
            )
            (root / "app.py").write_text("import core.memory\n", encoding="utf-8")
            output = root / "audit" / "rea"
            result = analyze_project(root=root, output_dir=output)
            self.assertTrue(Path(result["path"]).is_file())
            report = result["report"]
            self.assertEqual(len(report["evidence_id"]), 64)
            self.assertIn("leads", report["metrics"]["sqlite_tables"])
            self.assertTrue(report["limitations"])
            self.assertTrue((output / "latest.json").is_file())
            loaded = latest_report(SimpleNamespace(rea_dir=output))
            self.assertIsInstance(loaded, dict)
            self.assertEqual(loaded["evidence_id"], report["evidence_id"])


class PersonaTests(unittest.TestCase):
    def test_prompt_contains_allowlist_and_persona(self):
        prompt = build_system_prompt(get_persona("conciso"), "Plano X")
        self.assertIn("quatro frases", prompt)
        self.assertIn("navigate", prompt)
        self.assertIn("confirmação humana", prompt)


class FakeOllama:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def chat(self, messages, format_json=True):
        self.calls += 1
        return self.content


class FakeBrowser:
    def __init__(self):
        self.urls = []

    def open_and_read(self, url):
        from adapters.browseros import BrowserRead

        self.urls.append(url)
        return BrowserRead(url=url, text="texto de exemplo")


class AgentTests(unittest.TestCase):
    def _agent(self, content, browser=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        memory = Memory(Path(folder.name) / "agent.sqlite3")
        self.addCleanup(memory.close)
        fake_browser = browser or FakeBrowser()
        agent = Agent(
            memory,
            load_config(),
            ollama=FakeOllama(content),
            browser_factory=lambda: fake_browser,
        )
        return agent, memory, fake_browser

    def test_answer_flow(self):
        agent, memory, _browser = self._agent('{"action":"answer","text":"Olá!"}')
        self.assertEqual(agent.run("Oi"), "Olá!")
        self.assertEqual(memory.recent()[-1], ("assistant", "Olá!"))

    def test_explicit_navigation_bypasses_model(self):
        from adapters.browseros import BrowserRead

        class RaisingOllama:
            def chat(self, *args, **kwargs):
                raise AssertionError("Ollama não deveria ser chamado")

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        memory = Memory(Path(folder.name) / "agent.sqlite3")
        self.addCleanup(memory.close)
        browser = FakeBrowser()
        agent = Agent(
            memory,
            load_config(),
            ollama=RaisingOllama(),
            browser_factory=lambda: browser,
        )
        answer = agent.run("Abra https://example.com e leia")
        self.assertIn("https://example.com", answer)
        self.assertEqual(browser.urls, ["https://example.com"])

    def test_write_action_is_pending_not_executed(self):
        agent, memory, browser = self._agent(
            '{"action":"send_message","text":"Olá, cliente"}'
        )
        answer = agent.run("Envie uma mensagem para o cliente")
        self.assertIn("pendente", answer.lower())
        self.assertIn("não será executada", answer.lower())
        self.assertEqual(browser.urls, [])
        pending = memory.list_pending_actions()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0][2], "send_message")

    def test_navigation_not_explicit_is_blocked(self):
        agent, _memory, browser = self._agent(
            '{"action":"navigate","url":"https://example.com"}'
        )
        answer = agent.run("Leia essa página para mim")
        self.assertIn("não abro", answer)
        self.assertEqual(browser.urls, [])


class BrowserOSAdapterTests(unittest.TestCase):
    def test_open_and_read_extracts_value(self):
        calls = []

        class FakeMCP:
            timeout = 30.0

            def call_tool(self, name, arguments, timeout=None):
                calls.append((name, arguments))
                return {
                    "structuredContent": {
                        "value": (
                            "[UNTRUSTED_PAGE_CONTENT nonce=x origin=https://example.com/] "
                            "Conteúdo de teste "
                            "[END_UNTRUSTED_PAGE_CONTENT nonce=x]"
                        )
                    }
                }

        client = BrowserOSClient(
            "http://127.0.0.1:9210/mcp", max_chars=1000, mcp=FakeMCP()
        )
        result = client.open_and_read("https://example.com")
        self.assertIn("Conteúdo de teste", result.text)
        self.assertEqual(calls[0][0], "run")

    def test_open_and_read_rejects_local_url(self):
        class FakeMCP:
            timeout = 30.0

            def call_tool(self, *args, **kwargs):
                raise AssertionError("não deveria chamar o MCP")

        client = BrowserOSClient(
            "http://127.0.0.1:9210/mcp", max_chars=1000, mcp=FakeMCP()
        )
        with self.assertRaises(ValueError):
            client.open_and_read("http://127.0.0.1/")


if __name__ == "__main__":
    unittest.main()
