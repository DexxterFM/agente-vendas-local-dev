"""Fluxo de mensagens sem API Meta, validado contra fixtures do DOM.

As fixtures reproduzem o retorno do script injetado na página por
`scripts/vps/internal_browser_agent.py` (snapshot da conversa e lista da caixa
de entrada). O Instagram real não é exercitado aqui.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.instagram_browser_sync import (
    iter_valid_messages,
    message_key,
    message_status,
    normalize_timestamp,
    normalize_username,
    record_send_status,
    store_messages,
)
from core.memory import Memory

FIXTURES = Path(__file__).parent / "fixtures"


class UsernameTest(unittest.TestCase):
    def test_normaliza_arroba_e_caixa(self):
        self.assertEqual(normalize_username("@Fono.ComGabriela"), "fono.comgabriela")
        self.assertEqual(normalize_username("  @clinica_lumi  "), "clinica_lumi")
        self.assertEqual(normalize_username(None), "")


class TimestampTest(unittest.TestCase):
    def test_aceita_iso8601(self):
        self.assertEqual(normalize_timestamp("2026-11-20T14:05:40.123456+00:00"),
                         "2026-11-20T14:05:40.123456+00:00")
        self.assertEqual(normalize_timestamp("2026-11-20T14:02:11Z"), "2026-11-20T14:02:11+00:00")

    def test_descarta_horario_relativo_e_lixo(self):
        for raw in ("há 2 h", "Agora", "", None, "2026-11-20T14:02:11", "x" * 60):
            self.assertEqual(normalize_timestamp(raw), "", raw)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((FIXTURES / "thread_snapshot.json").read_text(encoding="utf-8"))

    def test_filtra_bolhas_invalidas(self):
        messages = list(iter_valid_messages(self.snapshot["messages"], thread_id=self.snapshot["thread_id"]))
        # 8 entradas: texto vazio e direção "system" caem; a bolha sem id
        # recebe a chave recalculada e é mantida.
        self.assertEqual(len(messages), 6)
        for message in messages:
            self.assertIn(message["direction"], ("incoming", "outgoing"))
            self.assertRegex(message["id"], r"^[0-9a-f]{64}$")
            self.assertTrue(message["text"])

    def test_nao_confunde_horario_relativo_com_data(self):
        messages = list(iter_valid_messages(self.snapshot["messages"], thread_id="t"))
        relativo = [m for m in messages if m["text"] == "há 2 h"][0]
        self.assertEqual(relativo["ts"], "")

    def test_bolha_repetida_com_ordinal_diferente_gera_ids_distintos(self):
        messages = list(iter_valid_messages(self.snapshot["messages"], thread_id="t"))
        repetidas = [m for m in messages if m["text"] == "Queria saber valores e horários"]
        self.assertEqual(len(repetidas), 2)
        self.assertNotEqual(repetidas[0]["id"], repetidas[1]["id"])

    def test_chave_e_estavel_e_depende_da_thread(self):
        a = message_key("111", "incoming", "oi", 1)
        self.assertEqual(a, message_key("111", "incoming", "oi", 1))
        self.assertNotEqual(a, message_key("222", "incoming", "oi", 1))
        self.assertNotEqual(a, message_key("111", "outgoing", "oi", 1))

    def test_snapshot_do_agente_e_snapshot_cru_deduplicam_igual(self):
        """O agente envia ids prontos; o ajuste aceita o payload cru também."""
        bruto = [
            {"text": "oi", "direction": "incoming", "ordinal": 1},
            {"text": "tudo bem?", "direction": "outgoing", "ordinal": 1},
        ]
        ids = [m["id"] for m in iter_valid_messages(bruto, thread_id="555")]
        self.assertEqual(ids, [message_key("555", "incoming", "oi", 1),
                               message_key("555", "outgoing", "tudo bem?", 1)])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(str(Path(self.tmp.name) / "sync.sqlite3"))
        self.snapshot = json.loads((FIXTURES / "thread_snapshot.json").read_text(encoding="utf-8"))
        self.thread = self.snapshot["thread_id"]
        self.lead = self.memory.add_lead("fono.comgabriela", "fono.comgabriela", "importado")

    def tearDown(self):
        self.memory.close()
        self.tmp.cleanup()

    def test_grava_uma_vez_e_deduplica(self):
        first = store_messages(self.memory, self.lead, self.thread, self.snapshot["messages"])
        self.assertEqual(first, {"stored": 6, "seen": 6})
        second = store_messages(self.memory, self.lead, self.thread, self.snapshot["messages"])
        self.assertEqual(second["stored"], 0, "segunda passagem não pode duplicar")
        self.assertEqual(len(self.memory.list_conversations(self.lead, 50)), 6)

    def test_direcao_vira_papel(self):
        store_messages(self.memory, self.lead, self.thread, self.snapshot["messages"])
        papeis = {row[1]: row[0] for row in self.memory.list_conversations(self.lead, 50)}
        self.assertEqual(papeis["Oi! Vi que vocês atendem TEA"], "user")
        self.assertEqual(papeis["Oi! Tudo bem? Como posso ajudar?"], "assistant")

    def test_horario_do_instagram_prevalece(self):
        store_messages(self.memory, self.lead, self.thread, self.snapshot["messages"])
        rows = self.memory.db.execute(
            "select created_at from conversations where content=? order by id",
            ("Queria saber valores e horários",),
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(str(rows[0][0]).startswith("2026-11-20T14:05:40"), rows[0][0])
        # a segunda cópia não tinha data no DOM e recebe o horário da importação
        self.assertTrue(str(rows[1][0]).startswith("2026-11-"), rows[1][0])

    def test_thread_diferente_nao_herda_dedupe(self):
        store_messages(self.memory, self.lead, self.thread, self.snapshot["messages"])
        outra = store_messages(self.memory, self.lead, "999999", self.snapshot["messages"])
        self.assertEqual(outra["stored"], 6)

    def test_status_de_envio_fica_registrado(self):
        record_send_status(self.memory, self.lead, {"sent": True, "bubbles": 2, "thread_id": "111"})
        status = message_status(self.memory, self.lead)
        self.assertTrue(status["lead"]["sent"])
        self.assertEqual(status["lead"]["bubbles"], 2)
        self.assertEqual(status["lead"]["channel"], "browser")
        self.assertIn("at", status["lead"])


class InboxFixtureTest(unittest.TestCase):
    def test_fixture_da_caixa_tem_campos_que_o_agente_usa(self):
        rows = json.loads((FIXTURES / "inbox_targets.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIn("key", row)
            self.assertIsInstance(row["x"], float)
            self.assertIsInstance(row["y"], float)
        self.assertTrue(rows[0]["unread"])
        self.assertFalse(rows[1]["unread"])


class SemApiMetaTest(unittest.TestCase):
    def test_fluxo_de_mensagens_nao_usa_graph_api(self):
        root = Path(__file__).resolve().parents[1]
        for relative in ("core/instagram_browser_sync.py",
                         "scripts/vps/internal_browser_agent.py",
                         "scripts/vps/sales_agent_worker.py"):
            texto = (root / relative).read_text(encoding="utf-8")
            for proibido in ("graph.facebook.com", "graph.instagram.com", "INSTAGRAM_ACCESS_TOKEN"):
                self.assertNotIn(proibido, texto, f"{relative} não pode depender de {proibido}")


if __name__ == "__main__":
    unittest.main()
