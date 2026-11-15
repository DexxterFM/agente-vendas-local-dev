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
    return os.getenv("POSTFLOW_BASE_URL", "https://postflow.avanthcode.com").rstrip("/")


def configured() -> bool:
    if os.getenv("POSTFLOW_API_TOKEN", "").strip() or os.getenv("POSTFLOW_SESSION_COOKIE", "").strip():
        return True
    # O PostFlow pode ser consumido pelo agente como serviço local da mesma
    # VPS. Isso é opt-in e só aceita loopback; não abre um bypass para hosts
    # públicos e não copia credenciais entre projetos.
    if os.getenv("POSTFLOW_TRUSTED_LOCAL", "").strip().lower() not in {"1", "true", "yes"}:
        return False
    return urlparse(_base()).hostname in {"127.0.0.1", "localhost", "::1"}


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    token = os.getenv("POSTFLOW_API_TOKEN", "").strip()
    cookie = os.getenv("POSTFLOW_SESSION_COOKIE", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie
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
    return {"status": "connected" if result.get("connected", result.get("ok", False)) else "unavailable", "postflow": result}


def threads() -> list[dict[str, Any]]:
    result = _request("GET", "engagement/threads")
    value = result.get("threads", result.get("data", []))
    return value if isinstance(value, list) else []


def messages(thread_id: str) -> list[dict[str, Any]]:
    result = _request("GET", f"engagement/threads/{thread_id}/messages")
    value = result.get("messages", result.get("data", []))
    return value if isinstance(value, list) else []


def create_reply(thread_id: str, text: str, original_text: str = "") -> dict[str, Any]:
    return _request("POST", "engagement/create", {"kind": "dm_reply", "threadId": thread_id, "finalText": text, "originalText": original_text})


def approve_reply(item_id: str, text: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"itemId": item_id}
    if text is not None:
        body["finalText"] = text
    return _request("POST", "engagement/approve", body)


def send_approved(item_id: str) -> dict[str, Any]:
    return _request("POST", "worker/publish-due", {"onlyIds": [item_id]})
