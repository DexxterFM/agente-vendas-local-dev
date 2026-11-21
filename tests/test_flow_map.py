import unittest

from core.flow_map import build_flow_map, STAGE_FLOW, INTERRUPTIONS


class FlowMapTest(unittest.TestCase):
    def test_mapa_tem_todos_os_estagios_em_ordem(self):
        data = build_flow_map([])
        stages = data["stages"]
        self.assertEqual(6, len(stages))
        ids = [s["id"] for s in stages]
        self.assertEqual(
            ["OPENING", "DISCOVERY", "OFFER", "EDITION_SELECT", "TOKEN_SENT", "POST_ACTIVATION"],
            ids,
        )
        self.assertEqual(list(range(1, 7)), [s["order"] for s in stages])

    def test_cada_estagio_tem_objetivo_respostas_e_transicoes(self):
        data = build_flow_map([])
        for stage in data["stages"]:
            self.assertTrue(stage["label"], stage["id"])
            self.assertTrue(stage["objective"], stage["id"])
            self.assertTrue(stage["agent_bubbles"], stage["id"])
            self.assertTrue(stage["waits_for"], stage["id"])

    def test_estagio_edition_select_gera_token_das_duas_edicoes(self):
        data = build_flow_map([])
        edition = next(s for s in data["stages"] if s["id"] == "EDITION_SELECT")
        actions = [t.get("action") for t in edition["transitions"]]
        self.assertTrue(any("Multiprofissional" in (a or "") for a in actions))
        self.assertTrue(any("Profissional" in (a or "") for a in actions))

    def test_interrupcoes_globais_presentes(self):
        data = build_flow_map([])
        intents = {i["intent"] for i in data["interruptions"]}
        self.assertEqual(
            {"OPT_OUT", "HUMAN_HANDOFF", "BILLING_FLOW", "PARTNERSHIP"},
            intents,
        )

    def test_texto_editavel_e_anexado_da_biblioteca(self):
        templates = [
            {"id": "intro-follow-clinic", "response": "Frase customizada", "question": "Pergunta"},
            {"id": "install-support", "response": "Suporte customizado", "question": "Duvida"},
        ]
        data = build_flow_map(templates)
        opening = next(s for s in data["stages"] if s["id"] == "OPENING")
        editable = {e["id"]: e["text"] for e in opening["editable_bubbles"]}
        self.assertEqual("Frase customizada", editable["intro-follow-clinic"])
        token = next(s for s in data["stages"] if s["id"] == "TOKEN_SENT")
        support = {e["id"]: e["text"] for e in token["editable_bubbles"]}
        self.assertEqual("Suporte customizado", support["install-support"])

    def test_resumo_consistente(self):
        data = build_flow_map([])
        self.assertEqual(data["summary"]["total_stages"], len(STAGE_FLOW))
        self.assertEqual(data["summary"]["total_interruptions"], len(INTERRUPTIONS))
        self.assertEqual(
            data["summary"]["total_transitions"],
            sum(len(s["transitions"]) for s in STAGE_FLOW),
        )


if __name__ == "__main__":
    unittest.main()
