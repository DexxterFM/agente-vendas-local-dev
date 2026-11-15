"""Adaptador seguro para o CRM comercial do ERP ClinicaTEA."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

import requests


@dataclass
class CommercialLead:
    nome: str
    instagram: str = ""
    segmento: str = ""
    etapa: str = "Aguardando"
    score: int = 0
    origem: str = "Instagram"
    proxima_acao: str = "Responder DM"
    data_proximo_contato: str = ""
    observacoes: str = ""
    email: str = ""
    telefone: str = ""
    cidade: str = ""
    site: str = ""
    plano_interesse: str = ""
    valor_previsto: float | None = None
    responsavel_comercial: str = "Agente Local"

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        for source, target in {
            "proxima_acao": "proximaAcao",
            "data_proximo_contato": "dataProximoContato",
            "plano_interesse": "planoInteresse",
            "valor_previsto": "valorPrevisto",
            "responsavel_comercial": "responsavelComercial",
        }.items():
            payload[target] = payload.pop(source)
        return payload


class ClinicaTeaCrmAdapter:
    """Cliente HTTP; credenciais vêm apenas do ambiente e nunca são logadas."""

    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: int | None = None):
        self.base_url = (base_url or os.getenv("ERP_CLINICATEA_API_BASE_URL", "https://api.erpclinicatea.com")).rstrip("/")
        self.token = token or os.getenv("ERP_CLINICATEA_API_TOKEN", "")
        self.timeout = timeout or int(os.getenv("ERP_CLINICATEA_API_TIMEOUT", "30"))

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        headers.setdefault("Accept", "application/json")
        response = requests.request(method, f"{self.base_url}/{path.lstrip('/')}", headers=headers, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_leads(self, status: str | None = None) -> dict[str, Any]:
        return self._request("GET", "/api/comercial/leads", params={"status": status} if status else None)

    def create_lead(self, lead: CommercialLead) -> dict[str, Any]:
        return self._request("POST", "/api/comercial/leads", json=lead.to_payload())

    def update_lead(self, lead_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/api/comercial/leads/{lead_id}", json=changes)

    def generate_reply(self, lead_id: str, message: str) -> dict[str, Any]:
        return self._request("POST", f"/api/comercial/leads/{lead_id}/generate-reply", json={"message": message})

    def queue_instagram_dm(self, lead_id: str, text: str) -> dict[str, Any]:
        return self._request("POST", f"/api/comercial/leads/{lead_id}/instagram-dm", json={"text": text, "approvalRequired": True})
