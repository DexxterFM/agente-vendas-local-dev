"""Entrada oficial de eventos Instagram/Meta para o agente hospedado.

O módulo não automatiza navegador nem aceita eventos sem assinatura.  Ele
converte apenas mensagens privadas do webhook oficial em histórico local;
curtidas, menções e demais atividades são conscientemente ignoradas.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

from core.sales_intelligence import SalesIntelligence


def _value(name: str) -> str:
    return os.getenv(name, "").strip()


def verify_subscription(query: dict[str, str]) -> str | None:
    """Retorna o challenge apenas para a verificação legítima da Meta."""
    expected = _value("META_WEBHOOK_VERIFY_TOKEN")
    if not expected:
        return None
    if query.get("hub.mode") != "subscribe":
        return None
    if not hmac.compare_digest(query.get("hub.verify_token", ""), expected):
        return None
    challenge = query.get("hub.challenge", "")
    return challenge if challenge and len(challenge) <= 4096 else None


def verify_signature(body: bytes, header: str | None) -> bool:
    """Exige X-Hub-Signature-256 assinado pelo segredo do aplicativo Meta."""
    secret = _value("INSTAGRAM_APP_SECRET") or _value("META_APP_SECRET")
    if not secret or not header or not header.startswith("sha256="):
        return False
    received = header.removeprefix("sha256=").strip().lower()
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return bool(received) and hmac.compare_digest(received, expected)


def _created_at(timestamp: Any) -> str:
    try:
        value = float(timestamp)
        if value > 100_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return datetime.now(timezone.utc).isoformat()


def ingest(memory, payload: dict[str, Any]) -> dict[str, int]:
    """Importa DMs recebidas/eco da conta sem expor conteúdo no retorno.

    O webhook pode ser reenviado pela Meta; o ``mid`` compõe a chave externa e
    mantém a importação idempotente. Eventos sem ``message.text`` (curtidas,
    reações, anexos sem texto etc.) são contabilizados somente como ignorados.
    """
    if not isinstance(payload, dict) or payload.get("object") not in {"instagram", "page"}:
        raise ValueError("Objeto de webhook Meta inválido")
    configured_account = _value("IG_BUSINESS_ACCOUNT_ID") or _value("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    intelligence = SalesIntelligence(memory)
    imported = duplicate = ignored = 0
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            ignored += 1
            continue
        for event in entry.get("messaging", []):
            if not isinstance(event, dict):
                ignored += 1
                continue
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            mid = str(message.get("mid") or "").strip()
            text = str(message.get("text") or "").strip()
            sender = str((event.get("sender") or {}).get("id") or "").strip()
            recipient = str((event.get("recipient") or {}).get("id") or "").strip()
            if not mid or not text or not sender or not recipient:
                ignored += 1
                continue
            account = configured_account or recipient
            echo = bool(message.get("is_echo"))
            outbound = echo or sender == account
            peer = recipient if outbound else sender
            if not peer:
                ignored += 1
                continue
            # Webhooks não fornecem o ID de conversação em todas as versões
            # da Graph API. A chave estável conta+perfil preserva o diálogo.
            thread = f"webhook:{account}:{peer}"
            result = intelligence.import_thread(
                account,
                thread,
                peer,
                [{
                    "id": mid,
                    "role": "assistant" if outbound else "user",
                    "text": text,
                    "created_at": _created_at(event.get("timestamp")),
                }],
                coverage="meta_webhook",
            )
            lead_id = int(result["lead_id"])
            memory.set_setting(
                "instagram.recipient:" + str(lead_id),
                json.dumps({"account": account, "recipient": peer}, separators=(",", ":")),
            )
            memory.set_setting("instagram.thread:" + str(lead_id), thread)
            if int(result.get("inserted", 0)):
                imported += 1
            else:
                duplicate += 1
    memory.audit(
        "meta.webhook.ingested",
        "instagram",
        "ok",
        f"imported={imported}; duplicate={duplicate}; ignored={ignored}",
    )
    return {"imported": imported, "duplicate": duplicate, "ignored": ignored}
