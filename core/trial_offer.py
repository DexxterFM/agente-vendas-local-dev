"""Oferta oficial de três meses e roteamento por perfil comercial."""
from __future__ import annotations

import json
import copy
from urllib.parse import urlparse


DEFAULT_TRIAL_OFFER = {
    "company_name": "AvanthCode",
    "company_url": "https://avanthcode.com",
    "months_free": 3,
    "clinic": {
        "name": "ERP Clínica TEA Multiprofissional",
        "url": (
            "https://erpclinicatea.com/ativacao?plano=clinica-multiprofissional"
            "&convite=3-meses&utm_source=instagram&utm_campaign=convite_tres_meses"
        ),
    },
    "professional": {
        "name": "Clínica TEA Profissional",
        "url": (
            "https://erpclinicatea.com/ativacao?plano=profissional"
            "&convite=3-meses&utm_source=instagram&utm_campaign=convite_tres_meses"
        ),
    },
    "activation": (
        "Os três meses começam após a ativação acompanhada. "
        "O link da campanha deve ser usado em até 3 dias."
    ),
    "billing_policy": {
        "automatic_charge": False,
        "warning_days": 10,
        "data_grace_days": 15,
        "summary": (
            "O teste não vira assinatura paga automaticamente. Dez dias antes do fim, "
            "enviamos um aviso e oferecemos a continuidade. Ao terminar, o acesso é bloqueado, "
            "os dados são disponibilizados em exportação bruta criptografada e há 15 dias para "
            "confirmar o pagamento antes da exclusão segura na nuvem."
        ),
    },
}


def get_trial_offer(memory) -> dict:
    raw = memory.get_setting("sales.trial.offer", "")
    if raw:
        try:
            value = json.loads(raw)
            if isinstance(value, dict) and value.get("clinic") and value.get("professional"):
                # Migração idempotente: ofertas antigas recebem a política
                # transparente sem alterar os links já configurados.
                if "billing_policy" not in value:
                    value["billing_policy"] = DEFAULT_TRIAL_OFFER["billing_policy"]
                    memory.set_setting("sales.trial.offer", json.dumps(value, ensure_ascii=False))
                return value
        except (TypeError, ValueError):
            pass
    # Evita que um operador/teste altere os dicionários aninhados do padrão
    # enquanto valida uma URL inválida.
    value = copy.deepcopy(DEFAULT_TRIAL_OFFER)
    memory.set_setting("sales.trial.offer", json.dumps(value, ensure_ascii=False))
    return value


def save_trial_offer(memory, offer: dict) -> dict:
    """Salva somente URLs HTTPS explícitas que o agente pode encaminhar."""
    current = get_trial_offer(memory)
    if not isinstance(offer, dict):
        raise ValueError("Configuração de teste inválida.")
    result = {
        **current,
        "company_name": str(offer.get("company_name", current["company_name"]))[:120].strip(),
        "company_url": str(offer.get("company_url", current["company_url"]))[:1200].strip(),
        "months_free": 3,
        "activation": str(offer.get("activation", current["activation"]))[:800].strip(),
        "billing_policy": {
            **current.get("billing_policy", DEFAULT_TRIAL_OFFER["billing_policy"]),
            "automatic_charge": False,
            "warning_days": 10,
            "data_grace_days": 15,
            "summary": str(
                (offer.get("billing_policy") or {}).get(
                    "summary",
                    current.get("billing_policy", DEFAULT_TRIAL_OFFER["billing_policy"])["summary"],
                )
            )[:1200].strip(),
        },
        "clinic": {**current["clinic"], **(offer.get("clinic") if isinstance(offer.get("clinic"), dict) else {})},
        "professional": {**current["professional"], **(offer.get("professional") if isinstance(offer.get("professional"), dict) else {})},
    }
    for key in ("company_url",):
        parsed = urlparse(result[key])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Informe URL HTTPS oficial da empresa.")
    for segment in ("clinic", "professional"):
        result[segment]["name"] = str(result[segment].get("name", ""))[:160].strip()
        result[segment]["url"] = str(result[segment].get("url", ""))[:1200].strip()
        parsed = urlparse(result[segment]["url"])
        if not result[segment]["name"] or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Informe nome e URL HTTPS para os dois links de três meses.")
    if not result["company_name"] or not result["activation"]:
        raise ValueError("Informe a empresa e a orientação de ativação.")
    memory.set_setting("sales.trial.offer", json.dumps(result, ensure_ascii=False))
    memory.audit("sales.trial_offer.updated", "sales.trial.offer", "ok", "links=clinic,professional")
    return result
