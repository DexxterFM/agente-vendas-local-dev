"""Contexto de conversa e validação de respostas.

Centraliza as regras que impedem o agente de repetir mensagens em conversas já
em andamento ou de enviar uma mensagem de primeiro contato quando o histórico
mostra que o diálogo já começou. Todos os pontos de envio (DM, prospecção e
notificações) devem passar por ``can_send`` antes de digitar no navegador.
"""
from __future__ import annotations

import hashlib
import re

# Assinaturas de mensagens de abertura / primeiro contato. Se qualquer uma
# aparecer numa resposta proposta para uma conversa que já tem histórico, o
# envio é bloqueado — o agente deve continuar o diálogo, não reiniciá-lo.
_OPENING_PATTERNS = (
    r'\bvi o trabalho\b',
    r'\bachei (?:muito )?bonito\b',
    r'\bobrigado por seguir\b',
    r'\bparab[eé]ns pelo (?:trabalho|seu trabalho|da cl[ií]nica)\b',
    r'\btenho um presente\b',
    r'\bj[áa] usa algum app\b',
    r'\bj[áa] possui algum app\b',
    r'\bvoc[eê]s j[áa] usam algum app\b',
)


def normalize(text) -> str:
    """Normaliza texto para comparação estável (espaços e caixa)."""
    return ' '.join(str(text or '').split()).casefold()


def fingerprint(text) -> str:
    """Hash estável de uma mensagem, usado para detectar reenvio exato."""
    return hashlib.sha256(normalize(text).encode('utf-8')).hexdigest()


def is_opening(text) -> bool:
    """True se a mensagem é uma saudação/abertura de primeiro contato."""
    value = normalize(text)
    return any(re.search(pattern, value) for pattern in _OPENING_PATTERNS)


def has_prior_exchange(history) -> bool:
    """True se já houve pelo menos uma resposta do agente ou duas falas do lead."""
    if not history:
        return False
    roles = [str(row[0]) for row in history]
    return 'assistant' in roles or roles.count('user') >= 2


def can_send(memory, lead_id, username, proposed, screen_history=None, *, require_history: bool = False):
    """Decide se a resposta proposta pode ser enviada.

    Args:
        memory: instância de Memory.
        lead_id: id do lead (pode ser None).
        username: usuário Instagram (pode ser None).
        proposed: texto que seria digitado no navegador.
        screen_history: mensagens visíveis na tela (lista de dicts com 'text'/'role').
        require_history: se True, bloqueia quando não há nenhum histórico e a
            mensagem é de abertura (usado no fluxo de prospecção, onde a tela
            pode não ter carregado as mensagens a tempo).

    Returns:
        (allowed: bool, reason: str)
    """
    proposed_norm = normalize(proposed)
    if not proposed_norm:
        return False, 'empty'

    fingerprint_proposed = fingerprint(proposed)

    # 1) Reenvio exato: mensagem já aparece na tela.
    for item in (screen_history or []):
        if normalize(item.get('text', '')) == proposed_norm:
            return False, 'duplicate-on-screen'

    # 2) Reenvio exato: mensagem já está no histórico persistido do lead.
    db_history = []
    if lead_id:
        db_history = list(reversed(memory.list_conversations(int(lead_id), 200)))
        for _role, text, _created in db_history:
            if normalize(text) == proposed_norm:
                return False, 'duplicate-in-history'

    # 3) Mensagem de abertura em conversa já iniciada.
    combined = list(screen_history or []) + list(db_history)
    if is_opening(proposed) and has_prior_exchange(combined):
        return False, 'opening-in-existing-conversation'

    # 4) Prospecção sem histórico visível: não reinicie uma conversa existente.
    if require_history and not combined and is_opening(proposed):
        return False, 'opening-without-history'

    return True, ''
