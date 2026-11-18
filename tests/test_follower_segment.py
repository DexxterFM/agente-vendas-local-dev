import unittest

from core.desktop_rpc import _follower_segment


class FollowerSegmentTests(unittest.TestCase):
    """Perfis públicos com sinais fortes não podem cair em 'community'."""

    def test_strong_public_signals_are_classified(self):
        cases = [
            ("seinformapsi", "VAGA | Psicologia — Acompanhante Terapêutica", "professional_pro"),
            ("autisfera", "Seu filho cresceu. E o cuidado?", "professional_pro"),
            ("harmonia.musicoterapia", "AUTISMO E MUSICOTERAPIA | AGENDA 2027", "professional_pro"),
            ("coordenacao.easm", "Coordenação Pedagógica", "professional_pro"),
            ("andrea.ludica.criativa12", "Professora de Educação Infantil", "professional_pro"),
            ("clinica.aflorar", "Clínica multidisciplinar atendimento infantil", "clinic_multi"),
            ("claudiaxavier.fono", "Fonoaudióloga", "professional_pro"),
        ]
        for username, text, expected in cases:
            with self.subTest(username=username):
                result = _follower_segment({"username": username, "text": text})
                self.assertEqual(expected, result["segment"])

    def test_unrelated_profiles_remain_community(self):
        for username, text in [
            ("mayumirubia", "Mayumi Rubia Followed by guilherme_caria"),
            ("drclaudiomessias", "REPARE NO TIPO DE PESSOA QUE ELE DESCREVE AQUI"),
        ]:
            with self.subTest(username=username):
                self.assertEqual(
                    "community",
                    _follower_segment({"username": username, "text": text})["segment"],
                )

    def test_editor_phrases_override_defaults(self):
        templates = [
            {"id": "intro-follow-clinic", "response": "Frase editada para clínica"},
            {"id": "intro-follow-professional", "response": "Frase editada para profissional"},
            {"id": "intro-follow-community", "response": "Frase editada para comunidade"},
        ]
        self.assertEqual(
            "Frase editada para clínica",
            _follower_segment({"text": "Clínica multidisciplinar"}, templates)["text"],
        )
        self.assertEqual(
            "Frase editada para profissional",
            _follower_segment({"text": "Psicóloga"}, templates)["text"],
        )
        self.assertEqual(
            "Frase editada para comunidade",
            _follower_segment({"text": "Perfil sem segmento"}, templates)["text"],
        )

    def test_short_terms_do_not_match_inside_longer_words(self):
        self.assertEqual("community", _follower_segment({"text": "Teatro e abater"})["segment"])


if __name__ == "__main__":
    unittest.main()
