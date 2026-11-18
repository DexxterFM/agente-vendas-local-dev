"""Cadastro persistente de perfis prospectados.

Antes de qualquer interação o agente consulta este módulo para saber se o
perfil já foi classificado, quais ações foram aplicadas e qual foi a última
mensagem enviada. O objetivo é evitar campanha repetida e bolha duplicada
mesmo depois de reiniciar o painel ou o worker.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

KEY_PREFIX = 'sales.profile.memory:'
INDEX_KEY = 'sales.profile.memory.index'
LAST_MESSAGE_KEY = 'sales.profile.last_message'
MAX_MESSAGES = 30

# Especialidades citadas pelo operador. A ordem define a prioridade na leitura
# do perfil; o texto salvo mantém todas as que apareceram.
SPECIALTIES = (
    ('terapia ocupacional', r'terapia\s*ocupacional|terapeuta\s*ocupacional|(?:^|\W)to(?:\W|$)'),
    ('psicomotricidade', r'psicomotricidade|psicomotricista'),
    ('fonoaudiologia', r'fonoaudi[oó]log|fonoaudi[oó]loga|(?:^|\W)fono(?:\W|$)'),
    ('fisioterapia', r'fisioterapia|(?:^|\W)fisio(?:\W|$)'),
    ('psicopedagogia', r'psicopedagog'),
    ('neuropsicologia', r'neuropsic'),
    ('aba', r'(?:^|\W)aba(?:\W|$)|analise do comportamento|an[aá]lise do comportamento'),
    ('psicologia', r'psicolog'),
    ('musicoterapia', r'musicoterap'),
    ('pedagogia', r'pedagog|professor|educador'),
    ('autismo', r'autis|(?:^|\W)tea(?:\W|$)|tdah'),
    ('integração sensorial', r'integra[cç][aã]o sensorial'),
)

CLINIC_TERMS = (
    'clinica', 'consultorio', 'multidisciplinar', 'equipe', 'centro terapeutico',
    'espaco terapeutico', 'atendimento infantil', 'desenvolvimento infantil',
)
THERAPY_TERMS = ('terapeuta', 'terapia', 'atendimento', 'profissional', 'especialista')


def normalize(text) -> str:
    raw = ' '.join(str(text or '').split())
    normalized = unicodedata.normalize('NFKD', raw).encode('ascii', 'ignore').decode('ascii')
    return normalized.casefold()


def message_hash(text) -> str:
    return hashlib.sha256(normalize(text).encode('utf-8')).hexdigest()


def classify(text) -> dict:
    """Classifica o perfil em clinica, clinica multidisciplinar ou terapeuta."""
    value = normalize(text)
    found = [name for name, pattern in SPECIALTIES if re.search(pattern, value)]
    # "psicopedagogia" também contém "pedagog"; "neuropsicologia" contém
    # "psicologia". Guardar as duas formas inflaria o cadastro do perfil.
    if 'psicopedagogia' in found:
        found = [name for name in found if name not in ('pedagogia', 'psicologia')]
    elif 'neuropsicologia' in found:
        found = [name for name in found if name != 'psicologia']
    clinic = any(term in value for term in CLINIC_TERMS)
    therapy = bool(found) or any(term in value for term in THERAPY_TERMS)
    if clinic:
        multi = ('multidisciplinar' in value or 'equipe' in value or len(found) >= 2)
        return {
            'kind': 'clinic_multi' if multi else 'clinic',
            'specialties': found,
            'reason': 'perfil público indica clínica' + (' multidisciplinar' if multi else ''),
        }
    if therapy:
        return {
            'kind': 'therapist',
            'specialties': found,
            'reason': 'perfil público indica terapeuta ou profissional de terapia',
        }
    return {
        'kind': 'community',
        'specialties': found,
        'reason': 'perfil público não indica clínica nem terapeuta',
    }


class ProfileMemory:
    """Leitura e escrita do cadastro na mesma memória persistente do agente."""

    def __init__(self, memory):
        self.memory = memory

    @staticmethod
    def key(username) -> str:
        return KEY_PREFIX + str(username or '').strip().lstrip('@').lower()

    def get(self, username) -> dict:
        username = str(username or '').strip().lstrip('@').lower()
        if not username:
            return {}
        raw = self.memory.get_setting(self.key(username), '')
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except (TypeError, ValueError):
                pass
        return {'username': username, 'kind': '', 'specialties': [],
                'actions': {}, 'messages': [], 'dm_sent': False, 'last_message': ''}

    def all(self) -> list:
        try:
            usernames = json.loads(self.memory.get_setting(INDEX_KEY, '[]') or '[]')
        except (TypeError, ValueError):
            usernames = []
        return [self.get(name) for name in usernames if name]

    def _save(self, record: dict) -> dict:
        username = str(record.get('username') or '').strip().lower()
        self.memory.set_setting(self.key(username), json.dumps(record, ensure_ascii=False))
        try:
            usernames = json.loads(self.memory.get_setting(INDEX_KEY, '[]') or '[]')
        except (TypeError, ValueError):
            usernames = []
        if username not in usernames:
            usernames.append(username)
            self.memory.set_setting(INDEX_KEY, json.dumps(usernames[-2000:], ensure_ascii=False))
        return record

    def observe(self, username, text='', actions=None, message=None, stage='') -> dict:
        username = str(username or '').strip().lstrip('@').lower()
        if not username:
            raise ValueError('Perfil inválido')
        record = self.get(username)
        classified = classify(text)
        record.update({
            'username': username,
            'kind': record.get('kind') or classified['kind'],
            'specialties': sorted(set(list(record.get('specialties') or []) + classified['specialties'])),
            'reason': classified['reason'],
            'segment': str(stage or record.get('segment') or '')[:40],
            'updated_at': __import__('datetime').datetime.now().isoformat(),
        })
        current = dict(record.get('actions') or {})
        for step, done in dict(actions or {}).items():
            if done:
                current[str(step)[:20]] = True
        record['actions'] = current
        if message:
            digest = message_hash(message)
            messages = list(record.get('messages') or [])
            if digest not in messages:
                messages.append(digest)
                record['messages'] = messages[-MAX_MESSAGES:]
                record['last_message'] = digest
                record['dm_sent'] = True
                self.memory.set_setting(LAST_MESSAGE_KEY, json.dumps(
                    {'username': username, 'hash': digest}, ensure_ascii=False))
                self.memory.audit('sales.profile.message', '@' + username, 'ok',
                                  'hash=' + digest[:16] + '; perfil=' + record['kind'])
        self._save(record)
        self.memory.audit('sales.profile.observe', '@' + username, 'ok',
                          'kind=' + str(record['kind']) + '; actions=' + ','.join(sorted(current)))
        return record

    def message_allowed(self, username, text) -> dict:
        username = str(username or '').strip().lstrip('@').lower()
        digest = message_hash(text)
        record = self.get(username)
        messages = list(record.get('messages') or [])
        if record.get('dm_sent') and digest in messages:
            return {'allowed': False, 'reason': 'duplicate-message', 'hash': digest}
        if messages and messages[-1] == digest:
            return {'allowed': False, 'reason': 'consecutive-duplicate', 'hash': digest}
        try:
            last = json.loads(self.memory.get_setting(LAST_MESSAGE_KEY, '') or '{}')
        except (TypeError, ValueError):
            last = {}
        if last.get('hash') == digest and last.get('username') == username:
            return {'allowed': False, 'reason': 'consecutive-duplicate', 'hash': digest}
        return {'allowed': True, 'reason': '', 'hash': digest}

    def already_contacted(self, username) -> bool:
        record = self.get(username)
        return bool(record.get('dm_sent')) or bool((record.get('actions') or {}).get('dm'))
