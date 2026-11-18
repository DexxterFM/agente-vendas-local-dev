import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.desktop_rpc import execute
from core.flow_studio import BUILTIN_TEMPLATES, FlowStudio


PROMPT = (
    'Quando o lead disser que já usa outro sistema, responda: '
    '"Que bom! Qual sistema vocês usam hoje?"'
)


class FlowStudioTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(self.folder.name) / "agent.sqlite3")}
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def proposal(self, message=PROMPT, stage='descoberta'):
        # Estes testes validam o roteiro determinístico de regras. Força o
        # fallback para não depender de modelo local estar ligado na máquina.
        return execute('flowChat', {'message': message, 'stage': stage, 'rules_only': True})

    def apply(self, proposal, **extra):
        args = {
            'operations': proposal['operations'],
            'base_revision': proposal['base_revision'],
            'prompt': extra.pop('prompt', PROMPT),
            'summary': proposal['summary'],
            'lesson': proposal['lesson'],
        }
        args.update(extra)
        return execute('flowApply', args)

    def test_fallback_turns_prompt_into_editable_operation(self):
        proposal = self.proposal()
        self.assertEqual('rules', proposal['source'])
        self.assertEqual(0, proposal['base_revision'])
        self.assertEqual(1, len(proposal['operations']))
        operation = proposal['operations'][0]
        self.assertEqual('add', operation['action'])
        self.assertEqual('descoberta', operation['stage'])
        self.assertIn('Qual sistema', operation['response'])
        self.assertIn('sistema', operation['question'])
        self.assertFalse(proposal['needs_review'])

    def test_fallback_without_response_requires_review(self):
        proposal = self.proposal('Quando a clínica perguntar sobre preço, seja mais direto.')
        self.assertTrue(proposal['needs_review'])
        self.assertEqual('', proposal['operations'][0]['response'])
        result = self.apply(proposal)
        self.assertFalse(result['applied'])
        self.assertIn('sem texto', result['reason'])

    def test_apply_versions_library_and_draft_uses_approved_response(self):
        lead_id = execute('create', {'name': 'Clínica Teste', 'contact': 'clinica.teste'})
        proposal = self.proposal()
        result = self.apply(proposal)
        self.assertTrue(result['applied'])
        self.assertEqual(1, result['revision'])
        self.assertEqual(0, result['previous_revision'])
        self.assertEqual(1, len(result['learned']))

        answer = execute('draft', {
            'id': lead_id,
            'browser_history': [
                {'role': 'assistant', 'text': 'Vocês já usam algum app?'},
                {'role': 'user', 'text': 'Já uso o sistema X aqui.'},
            ],
        })
        self.assertEqual('Que bom! Qual sistema vocês usam hoje?', answer)

        state = execute('flowState', {})
        self.assertEqual(1, state['revision'])
        self.assertEqual(1, state['history'][0]['revision'])
        self.assertEqual(1, len(state['lessons']))
        self.assertTrue(any(item.get('custom') for item in state['templates']))

    def test_apply_rejects_stale_base_revision(self):
        first = self.proposal()
        self.apply(first)
        with self.assertRaises(ValueError) as caught:
            self.apply(first)
        self.assertIn('versão 1', str(caught.exception))

    def test_update_and_remove_use_existing_ids(self):
        proposal = self.proposal('Na etapa descoberta, altere a resposta sobre já usar sistema para "Qual sistema a clínica usa hoje?"')
        result = self.apply(proposal)
        self.assertTrue(result['applied'])
        templates = {item['id']: item for item in execute('responseLibrary', {})}
        self.assertEqual('Qual sistema a clínica usa hoje?', templates['existing-app']['response'])
        self.assertTrue(templates['existing-app']['custom'])

        removed = execute('flowApply', {
            'operations': [{'action': 'remove', 'id': 'existing-app'}],
            'base_revision': result['revision'],
            'prompt': 'Remover a resposta de sistema existente',
        })
        self.assertTrue(removed['applied'])
        self.assertNotIn('existing-app', {item['id'] for item in execute('responseLibrary', {})})

    def test_revert_restores_previous_snapshot(self):
        lead_id = execute('create', {'name': 'Clínica Teste', 'contact': 'clinica.teste'})
        proposal = self.proposal()
        result = self.apply(proposal)
        self.assertEqual(1, result['revision'])

        reverted = execute('flowRevert', {'revision': 0})
        self.assertTrue(reverted['applied'])
        self.assertEqual(2, reverted['revision'])
        self.assertEqual([item['id'] for item in BUILTIN_TEMPLATES],
                         [item['id'] for item in execute('responseLibrary', {})])

        answer = execute('draft', {
            'id': lead_id,
            'browser_history': [
                {'role': 'assistant', 'text': 'Vocês já usam algum app?'},
                {'role': 'user', 'text': 'Já uso o sistema X aqui.'},
            ],
        })
        self.assertNotEqual('Que bom! Qual sistema vocês usam hoje?', answer)

    def test_manual_library_save_is_versioned_and_learned(self):
        saved = execute('saveResponseTemplate', {
            'template': {
                'stage': 'objeção',
                'question': 'A clínica diz que o preço está alto',
                'response': 'Entendo. O que mais pesa hoje: o investimento ou o tempo da equipe?',
                'context': 'Reconheça a objeção antes de argumentar.',
            },
        })
        self.assertTrue(saved['custom'])
        self.assertTrue(saved['id'])
        state = execute('flowState', {})
        self.assertEqual(1, state['revision'])
        self.assertEqual('library', state['history'][0]['source'])
        self.assertEqual(1, len(state['lessons']))

    def test_seed_library_does_not_override_validated_flow(self):
        # A biblioteca semente não sobrescreve o roteiro validado; só entra
        # como orientação para o modelo. O ajuste do operador é que assume.
        lead_id = execute('create', {'name': 'Clínica Teste', 'contact': 'clinica.teste'})
        answer = execute('draft', {
            'id': lead_id,
            'browser_history': [
                {'role': 'assistant', 'text': 'Vocês já usam algum app?'},
                {'role': 'user', 'text': 'Já uso o sistema X aqui.'},
            ],
        })
        self.assertIn('Posso comparar rapidamente', answer)

    def test_model_proposal_is_validated_and_normalized(self):
        class FakeClient:
            def chat(self, messages, format_json=True):
                self.messages = messages
                return (
                    '```json\n{"reply":"Vou ajustar a objeção.",'
                    '"summary":"Objeção de preço",'
                    '"lesson":"Reconhecer o preço antes de argumentar.",'
                    '"operations":[{"action":"adicionar","stage":"objecao",'
                    '"question":"A clínica diz que está caro",'
                    '"response":"Entendo. O que pesa mais: o valor ou o tempo da equipe?",'
                    '"match":"está caro | muito caro"}]}\n```'
                )

        from core.memory import Memory
        with Memory(str(Path(self.folder.name) / 'model.sqlite3')) as memory:
            proposal = FlowStudio(memory).interpret('Ajuste a objeção de preço', client=FakeClient())
        self.assertEqual('model', proposal['source'])
        self.assertEqual('objeção', proposal['operations'][0]['stage'])
        self.assertEqual('add', proposal['operations'][0]['action'])
        self.assertIn('caro', proposal['operations'][0]['question'])
        self.assertEqual([], proposal['warnings'])

    def test_invalid_model_output_falls_back_to_rules(self):
        class BrokenClient:
            def chat(self, messages, format_json=True):
                return 'não sei responder em JSON'

        from core.memory import Memory
        with Memory(str(Path(self.folder.name) / 'broken.sqlite3')) as memory:
            proposal = FlowStudio(memory).interpret(
                'Quando o lead disser que já usa sistema, responda: "Qual sistema vocês usam?"',
                client=BrokenClient(),
            )
        self.assertEqual('rules', proposal['source'])
        self.assertTrue(proposal['warnings'])
        self.assertEqual(1, len(proposal['operations']))

    def test_update_proposal_includes_current_preview(self):
        proposal = self.proposal(
            'Na etapa descoberta, altere a resposta sobre já usar sistema para '
            '"Qual sistema a clínica usa hoje?"'
        )
        operation = proposal['operations'][0]
        self.assertEqual('update', operation['action'])
        self.assertEqual('existing-app', operation['id'])
        self.assertEqual('existing-app', operation['preview']['id'])
        self.assertIn('Qual app', operation['preview']['response'])

    def test_teach_saves_response_for_the_client_message_and_repeats(self):
        lead_id = execute('create', {'name': 'Clínica Teste', 'contact': 'clinica.teste'})
        history = [
            {'role': 'assistant', 'text': 'Vocês já usam algum app?'},
            {'role': 'user', 'text': 'Já uso o sistema X aqui.'},
        ]
        saved = execute('flowTeach', {
            'message': 'Já uso o sistema X aqui.',
            'response': 'Qual sistema vocês usam hoje?',
            'lead_id': lead_id,
        })
        self.assertTrue(saved['applied'])
        self.assertEqual(1, saved['revision'])
        self.assertEqual('dialogue', execute('flowState', {})['history'][0]['source'])

        first = execute('draft', {'id': lead_id, 'browser_history': history})
        self.assertEqual('Qual sistema vocês usam hoje?', first)

        updated = execute('flowTeach', {
            'message': 'Já uso o sistema X aqui.',
            'response': 'Entendi. Qual sistema a clínica usa hoje?',
            'lead_id': lead_id,
        })
        self.assertTrue(updated['applied'])
        self.assertEqual(2, updated['revision'])
        self.assertEqual(saved['template']['id'], updated['template']['id'])
        self.assertEqual(
            'Entendi. Qual sistema a clínica usa hoje?',
            execute('draft', {'id': lead_id, 'browser_history': history}),
        )
        templates = execute('responseLibrary', {})
        self.assertEqual(1, len([item for item in templates if item.get('custom')]))

    def test_teach_short_message_matches_exactly(self):
        lead_id = execute('create', {'name': 'Clínica Teste', 'contact': 'clinica.teste'})
        saved = execute('flowTeach', {
            'message': 'oi',
            'response': 'Oi! Tudo bem? Já usa algum app na clínica?',
            'lead_id': lead_id,
        })
        self.assertTrue(saved['applied'])
        answer = execute('draft', {
            'id': lead_id,
            'browser_history': [
                {'role': 'assistant', 'text': 'Olá! Posso falar com você?'},
                {'role': 'user', 'text': 'oi'},
            ],
        })
        self.assertEqual('Oi! Tudo bem? Já usa algum app na clínica?', answer)

    def test_teach_requires_message_and_response(self):
        with self.assertRaises(ValueError):
            execute('flowTeach', {'message': '', 'response': 'Olá'})
        with self.assertRaises(ValueError):
            execute('flowTeach', {'message': 'oi', 'response': '   '})

    def test_teach_never_overrides_safety_rules(self):
        lead_id = execute('create', {'name': 'Clínica Teste', 'contact': 'clinica.teste'})
        execute('flowTeach', {
            'message': 'Vou ser cobrado automaticamente depois dos 3 meses?',
            'response': 'Resposta ensinada pelo operador.',
            'lead_id': lead_id,
        })
        answer = execute('draft', {
            'id': lead_id,
            'browser_history': [
                {'role': 'assistant', 'text': 'Você ganhou 3 meses grátis.'},
                {'role': 'user', 'text': 'Vou ser cobrado automaticamente depois dos 3 meses?'},
            ],
        })
        self.assertIn('não gera cobrança automática', answer)
        self.assertNotIn('Resposta ensinada', answer)


if __name__ == '__main__':
    unittest.main()
