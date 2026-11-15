"""Ponte oficial entre o aplicativo local e o PostFlow.

O PostFlow é a fonte de verdade da conexão Meta: este módulo não copia tokens
nem tenta fazer login no Instagram. Ele consulta as rotas de engajamento do
PostFlow usando a sessão/API configurada pelo operador e normaliza os dados
para a memória local do vendedor.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse


def _base() -> str:
    # O canal interno é explícito e só é permitido no PostFlow local oficial.
    # Evita que uma configuração legada de loopback envie a ingestão para outro
    # processo na mesma VPS.
    if os.getenv("POSTFLOW_TRUSTED_LOCAL", "").strip().lower() in {"1", "true", "yes"} and os.getenv("SALES_AGENT_INTERNAL_TOKEN", "").strip():
        return "http://127.0.0.1:3110"
    return os.getenv("POSTFLOW_BASE_URL", "https://postflow.avanthcode.com").rstrip("/")


def configured() -> bool:
    if os.getenv("POSTFLOW_API_TOKEN", "").strip() or os.getenv("POSTFLOW_SESSION_COOKIE", "").strip():
        return True
    # O PostFlow pode ser consumido pelo agente como serviço local da mesma
    # VPS. Isso é opt-in e só aceita loopback; não abre um bypass para hosts
    # públicos e não copia credenciais entre projetos.
    if os.getenv("POSTFLOW_TRUSTED_LOCAL", "").strip().lower() not in {"1", "true", "yes"}:
        return False
    return bool(os.getenv("SALES_AGENT_INTERNAL_TOKEN", "").strip()) and urlparse(_base()).hostname in {"127.0.0.1", "localhost", "::1"}


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    token = os.getenv("POSTFLOW_API_TOKEN", "").strip()
    cookie = os.getenv("POSTFLOW_SESSION_COOKIE", "").strip()
    internal_token = os.getenv("SALES_AGENT_INTERNAL_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie
    if internal_token and urlparse(_base()).hostname in {"127.0.0.1", "localhost", "::1"}:
        headers["X-Sales-Agent-Token"] = internal_token
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{_base()}/api/instagram-agent/{path.lstrip('/')}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=float(os.getenv("POSTFLOW_TIMEOUT", "20"))) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"PostFlow HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"PostFlow indisponível: {exc.reason}") from exc


def status() -> dict[str, Any]:
    if not configured():
        return {"status": "not_configured", "detail": "Configure credencial PostFlow ou POSTFLOW_TRUSTED_LOCAL para um endpoint loopback."}
    result = _request("GET", "health")
    connected = result.get("connected", result.get("ok", False))
    if not connected:
        return {"status": "unavailable", "postflow": result}
    rows = _request("GET", "engagement/threads")
    thread_list = rows.get("threads", rows.get("data", []))
    thread_count = len(thread_list) if isinstance(thread_list, list) else 0
    return {
        "status": "connected",
        "postflow": result,
        "threads": thread_count,
        "detail": f"PostFlow conectado • {thread_count} conversa(s) disponíveis.",
    }


def threads() -> list[dict[str, Any]]:
    result = _request("GET", "engagement/threads")
    value = result.get("threads", result.get("data", []))
    return value if isinstance(value, list) else []


def messages(thread_id: str) -> list[dict[str, Any]]:
    result = _request("GET", f"engagement/threads/{thread_id}/messages")
    value = result.get("messages", result.get("data", []))
    return value if isinstance(value, list) else []


def sync_ingestion() -> dict[str, Any]:
    """Solicita a importação inicial do PostFlow sem expor o retorno bruto.

    A rota pode consultar a API Meta. Por isso o chamador recebe somente
    contagens e uma categoria operacional, nunca a mensagem de erro, token,
    identificador de conta ou conteúdo de conversa.
    """
    try:
        result = _request("POST", "engagement/sync", {})
    except RuntimeError as exc:
        detail = str(exc).lower()
        if "401" in detail or "403" in detail:
            category = "authorization_rejected"
        elif "timeout" in detail or "indisponível" in detail:
            category = "service_unavailable"
        else:
            category = "request_failed"
        return {"status": "attention", "category": category, "synced": False}
    if result.get("error"):
        return {"status": "attention", "category": "source_rejected", "synced": False}
    stats = result.get("stats") if isinstance(result.get("stats"), dict) else {}
    reason = str(result.get("reason") or "")
    if result.get("synced") is True:
        category = "browser_dm_fallback" if result.get("dm_history_source") == "browser" else "imported"
    elif "desabilitado" in reason.lower():
        category = "disabled"
    elif "realizado" in reason.lower():
        category = "already_current"
    else:
        category = "no_change"
    return {
        "status": "connected",
        "category": category,
        "synced": result.get("synced") is True,
        "threads": max(0, int(stats.get("threads", 0) or 0)),
        "messages": max(0, int(stats.get("messages", 0) or 0)),
        "comments": max(0, int(stats.get("comments", 0) or 0)),
    }


def create_reply(thread_id: str, text: str, original_text: str = "") -> dict[str, Any]:
    return _request("POST", "engagement/create", {"kind": "dm_reply", "threadId": thread_id, "finalText": text, "originalText": original_text})


def approve_reply(item_id: str, text: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"itemId": item_id}
    if text is not None:
        body["finalText"] = text
    return _request("POST", "engagement/approve", body)


def send_approved(item_id: str) -> dict[str, Any]:
    return _request("POST", "worker/publish-due", {"onlyIds": [item_id]})
