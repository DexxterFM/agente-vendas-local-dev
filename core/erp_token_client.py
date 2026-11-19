"""Geração automática de tokens de demonstração no ERP Clínica TEA.

O agente usa a rota interna oficial do ERP, que aplica a mesma política do
botão "Criar token único" do painel administrativo. O segredo de chamada vem
de ``ERP_DEMO_TOKEN_API_KEY`` e o endpoint de ``ERP_CLINICATEA_API_BASE_URL``.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://erpclinicatea.com"
TOKEN_PATH = "/api/internal/demo-token"


def plan_slug_for_url(url: str | None) -> str:
    """Traduz o plano escolhido no diálogo para o slug do ERP."""
    text = str(url or "").lower()
    if "clinica-multiprofissional" in text or "enterprise" in text:
        return "enterprise"
    if "starter" in text:
        return "starter"
    return "professional"


def generate_demo_token(
    *,
    plan_slug: str = "professional",
    duration_code: str = "3m",
    user_name: str = "Agente de Vendas",
    redeem_within_days: int = 30,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """Cria um token novo de 3 meses no ERP. Retorna ``None`` se falhar."""
    base = str(
        base_url
        or os.getenv("ERP_CLINICATEA_API_BASE_URL", DEFAULT_BASE_URL)
        or DEFAULT_BASE_URL
    ).strip().rstrip("/")
    key = str(
        api_key
        if api_key is not None
        else os.getenv("ERP_DEMO_TOKEN_API_KEY", "")
    ).strip()
    if not key:
        return None

    payload = json.dumps({
        "planSlug": plan_slug,
        "durationCode": duration_code,
        "userName": user_name or "Agente de Vendas",
        # Contas de teste exigem retenção dos dados pela política do ERP.
        "accountKind": "test",
        "dataPolicy": "retain",
        "redeemWithinDays": max(1, min(90, int(redeem_within_days or 30))),
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base}{TOKEN_PATH}",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Agent-Token": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError, OSError):
        return None
    if not isinstance(data, dict) or not data.get("ok") or not data.get("token"):
        return None
    return data
