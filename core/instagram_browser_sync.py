"""Sincronização de DMs do Instagram pelo navegador interno.

Substitui a dependência da API Meta no fluxo de mensagens: o agente já lê a
caixa de entrada e as conversas pela sessão persistente (CDP) e já envia
digitando no campo da conversa. Este módulo concentra a parte determinística —
validação, deduplicação por thread+mensagem, gravação com horário e registro do
status de envio — para poder ser testada sem navegador.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Iterable

_HEX64 = re.compile(r"[0-9a-f]{64}")
_USERNAME = re.compile(r"[^a-z0-9._]")
SYNC_LAST_KEY = "instagram.sync.last"
THREAD_KEY = "instagram.thread:"
SEND_STATUS_KEY = "instagram.send_status:"
IMPORT_PREFIX = "instagram.browser_import:"
MAX_TEXT = 3500


def normalize_username(value: Any) -> str:
    """Normaliza @usuario do Instagram para a chave usada na memória."""
    return _USERNAME.sub("", str(value or "").lstrip("@").lower())[:30]


def normalize_timestamp(value: Any) -> str:
    """Aceita apenas ISO-8601 completo; horário relativo ("há 2 h") é ignorado.

    O DOM do Instagram expõe `datetime` absoluto em `<time>`; quando a página
    mostra apenas texto relativo não há data confiável, e gravar um palpite
    estragaria a ordenação do histórico.
    """
    raw = str(value or "").strip()
    if not raw or len(raw) > 40:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if not parsed.tzinfo:
        return ""
    return parsed.isoformat()


def message_key(thread_id: str, direction: str, text: str, ordinal: int) -> str:
    """Chave estável de uma bolha: thread + direção + texto + ocorrência.

    O mesmo cálculo roda no agente (`_thread_snapshot`) e aqui; é o que torna
    a importação idempotente entre ciclos, mesmo relendo a conversa inteira.
    """
    return hashlib.sha256(
        f"{thread_id}\0{direction}\0{text}\0{int(ordinal)}".encode()
    ).hexdigest()


def iter_valid_messages(raw: Any, limit: int = 80, thread_id: str = "") -> Iterable[dict[str, str]]:
    """Valida o snapshot vindo do DOM e devolve mensagens utilizáveis.

    Aceita tanto o payload já identificado pelo agente quanto o resultado cru
    do script injetado na página; quando o `id` não vem pronto, ele é
    recalculado com `message_key`, então os dois caminhos deduplicam igual.
    """
    items = raw if isinstance(raw, list) else []
    for item in items[-max(1, int(limit)):]:
        if not isinstance(item, dict):
            continue
        direction = str(item.get("direction") or "").strip().lower()
        text = " ".join(str(item.get("text") or "").split())[:MAX_TEXT]
        if direction not in ("incoming", "outgoing") or not text:
            continue
        external_id = str(item.get("id") or "").strip().lower()
        if not _HEX64.fullmatch(external_id):
            try:
                ordinal = int(item.get("ordinal") or 1)
            except (TypeError, ValueError):
                ordinal = 1
            external_id = message_key(thread_id, direction, text, ordinal)
        yield {
            "id": external_id,
            "direction": direction,
            "text": text,
            "ts": normalize_timestamp(item.get("ts")),
        }


def store_messages(memory: Any, lead_id: int, thread_id: str, raw: Any, limit: int = 80) -> dict[str, int]:
    """Grava as mensagens novas de uma conversa e devolve a contagem."""
    thread = str(thread_id or "").strip()
    stored = 0
    seen = 0
    for message in iter_valid_messages(raw, limit, thread):
        seen += 1
        key = IMPORT_PREFIX + hashlib.sha256((thread + "\0" + message["id"]).encode()).hexdigest()
        if memory.get_setting(key, "") == "stored":
            continue
        role = "user" if message["direction"] == "incoming" else "assistant"
        memory.add_conversation(lead_id, role, message["text"], created_at=message["ts"] or None)
        memory.set_setting(key, "stored")
        stored += 1
    return {"stored": stored, "seen": seen}


def record_send_status(memory: Any, lead_id: int, result: dict[str, Any]) -> None:
    """Persiste o resultado do envio para o painel acompanhar o andamento."""
    payload = {
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sent": bool(result.get("sent")),
        "bubbles": int(result.get("bubbles") or 0),
        "reason": str(result.get("reason") or "")[:120],
        "thread_id": str(result.get("thread_id") or "")[:40],
        "channel": "browser",
    }
    memory.set_setting(SEND_STATUS_KEY + str(int(lead_id)), str(payload))


def read_send_status(memory: Any, lead_id: int) -> dict[str, Any]:
    import ast
    raw = memory.get_setting(SEND_STATUS_KEY + str(int(lead_id)), "")
    if not raw:
        return {}
    try:
        parsed = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def browser_sync(memory: Any, username: str = "", thread_id: str = "", limit: int = 6) -> dict[str, Any]:
    """Ponto único usado pelo RPC: uma conversa específica ou a caixa inteira."""
    from scripts.vps import internal_browser_agent as agent
    if str(username or "").strip() or str(thread_id or "").strip():
        return agent.sync_thread(username=username, thread_id=thread_id)
    return agent.sync_inbox(limit_threads=int(limit or 6))


def browser_send(memory: Any, lead_id: int, text: str) -> dict[str, Any]:
    """Envia pelo navegador interno, sem API Meta, e registra o status."""
    from scripts.vps import internal_browser_agent as agent
    lead = memory.get_lead_detail(int(lead_id)) or {}
    username = normalize_username(lead.get("contact") or lead.get("name") or "")
    thread = memory.get_setting(THREAD_KEY + str(int(lead_id)), "")
    try:
        result = agent.send_reply(text=text, username=username, thread_id=thread, lead_id=int(lead_id))
    except Exception as exc:
        result = {"sent": False, "reason": str(exc)[:120], "bubbles": 0}
    record_send_status(memory, int(lead_id), result)
    try:
        memory.audit(
            "instagram.dm_browser_send", "@" + (username or "?"), "ok" if result.get("sent") else "blocked",
            "channel=browser; bubbles=%d; %s" % (int(result.get("bubbles") or 0), str(result.get("reason") or "")[:200]),
        )
    except Exception:
        pass
    return result


def message_status(memory: Any, lead_id: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"last_sync": memory.get_setting(SYNC_LAST_KEY, "")}
    if lead_id:
        payload["lead"] = read_send_status(memory, int(lead_id))
        payload["thread_id"] = memory.get_setting(THREAD_KEY + str(int(lead_id)), "")
    return payload
