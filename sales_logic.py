from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeadQualification:
    stage: str
    score: int
    reasons: tuple[str, ...]


def qualify_lead(text: str) -> LeadQualification:
    """Classificação determinística inicial; o modelo pode explicar, mas não decide sozinho."""
    value = text.lower()
    score = 0
    reasons: list[str] = []
    if any(word in value for word in ("preço", "valor", "orçamento", "quanto")):
        score += 25
        reasons.append("perguntou sobre preço")
    if any(word in value for word in ("comprar", "contratar", "fechar", "pix", "pagamento")):
        score += 40
        reasons.append("demonstrou intenção de compra")
    if any(word in value for word in ("dúvida", "como funciona", "informação", "conhecer")):
        score += 10
        reasons.append("está buscando informação")
    if any(word in value for word in ("agora", "hoje", "urgente", "prazo")):
        score += 15
        reasons.append("indicou urgência")
    stage = "hot" if score >= 60 else "warm" if score >= 25 else "new"
    return LeadQualification(stage, min(score, 100), tuple(reasons))


def draft_followup(name: str, product: str, stage: str) -> str:
    if stage == "hot":
        return f"Olá, {name}! Posso concluir sua contratação de {product} agora. Quer que eu envie as opções de pagamento?"
    if stage == "warm":
        return f"Olá, {name}! Separei as informações de {product}. Qual é a sua principal dúvida para eu te orientar?"
    return f"Olá, {name}! Posso te explicar como funciona {product} e entender o que você procura."
