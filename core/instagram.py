"""Planejamento assistido para Instagram, sem execução automática.

A aplicação lê apenas o perfil público que o operador abrir no BrowserOS e
transforma o contexto em rascunhos. Seguir, comentar, repostar e enviar DM são
ações externas: ficam pendentes de confirmação imediata e não são executadas
por esta versão. Não há scraping em massa, follow em massa nem DMs em série.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from core.playbook import (
    PlaybookEntry,
    build_playbook_context,
    comparison_checklist,
    draft_initial_message,
    draft_objection_reply,
    search_playbook,
)
from core.style import StyleProfile, human_delay_seconds

_HANDLE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
_RESERVED_PATHS = {
    "accounts",
    "api",
    "about",
    "explore",
    "direct",
    "p",
    "reel",
    "reels",
    "stories",
    "tv",
    "share",
}
_NICHE_WORDS = {
    "moda": ("moda", "roupa", "look", "fashion"),
    "beleza": ("beleza", "maquiagem", "cosmético", "cosmetico", "skincare"),
    "estética": ("estética", "estetica", "clínica", "clinica", "harmonização"),
    "saúde": ("saúde", "saude", "nutrição", "nutricao", "fisioterapia", "psicologia"),
    "fitness": ("fitness", "treino", "academia", "personal", "emagrecimento"),
    "advocacia": ("advocacia", "advogado", "jurídico", "juridico", "direito"),
    "arquitetura": ("arquitetura", "arquiteto", "interiores", "design de interiores"),
    "imóveis": ("imóvel", "imovel", "imobiliária", "imobiliaria", "corretor"),
    "marketing": ("marketing", "tráfego", "trafego", "social media", "publicidade"),
    "consultoria": ("consultoria", "consultor", "mentoria", "coach"),
    "loja": ("loja", "e-commerce", "ecommerce", "produto", "vendas"),
    "restaurante": ("restaurante", "café", "cafe", "confeitaria", "food"),
    "educação": ("educação", "educacao", "curso", "escola", "professor", "aula"),
    "tecnologia": ("tecnologia", "software", "saas", "app", "automação", "automacao"),
}
_SIGNAL_WORDS = {
    "link na bio": ("link na bio", "link abaixo", "clique no link"),
    "whatsapp": ("whatsapp", "whats", "zap"),
    "agendamento": ("agende", "agendamento", "agenda", "horário", "horario"),
    "atendimento": ("atendimento", "atende", "consulta", "orçamento", "orcamento"),
    "loja virtual": ("loja", "compre", "carrinho", "e-commerce", "ecommerce"),
    "conteúdo educativo": ("dica", "aprenda", "conteúdo", "conteudo", "aula"),
    "mentoria": ("mentoria", "consultoria", "acompanhamento"),
}
_SENSITIVE_HINTS = (
    "religião",
    "religiao",
    "política",
    "politica",
    "partido",
    "sexualidade",
    "diagnóstico",
    "diagnostico",
)


@dataclass(frozen=True)
class ProfileInsight:
    handle: str
    url: str
    niche: str
    signals: tuple[str, ...]
    notes: tuple[str, ...]

    def summary(self) -> str:
        signals = ", ".join(self.signals) if self.signals else "sem sinais comerciais claros"
        notes = " ".join(self.notes)
        return (
            f"@{self.handle} • nicho provável: {self.niche or 'não identificado'} • "
            f"sinais: {signals}." + (f" {notes}" if notes else "")
        )


@dataclass(frozen=True)
class SuggestedAction:
    action: str
    title: str
    draft: str
    rationale: str
    requires_confirmation: bool = True

    def payload(self, insight: ProfileInsight) -> dict:
        return {
            "channel": "instagram",
            "action": self.action,
            "profile_url": insight.url,
            "handle": insight.handle,
            "draft": self.draft,
            "requires_confirmation": True,
            "execution": "disabled",
        }


@dataclass(frozen=True)
class InstagramPlan:
    insight: ProfileInsight
    initial_message: str
    comment_draft: str
    objection_guidance: str
    actions: tuple[SuggestedAction, ...]
    checklist: tuple[str, ...]
    playbook: tuple[PlaybookEntry, ...]
    delay_seconds: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        return (
            f"Plano para @{self.insight.handle}: {len(self.actions)} ação(ões) sugerida(s), "
            f"todas pendentes de confirmação. Ritmo estimado do primeiro DM: "
            f"{self.delay_seconds}s de digitação."
        )


def extract_handle(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("@"):
        text = text[1:]
    if "instagram.com" in text.lower():
        return _handle_from_url(text)
    return text.strip().rstrip("/")


def _handle_from_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    return parts[0] if parts else ""


def normalize_profile_url(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("Informe um perfil ou URL do Instagram.")
    if "instagram.com" in text.lower():
        allowed, reason = validate_instagram_url(text)
        if not allowed:
            raise ValueError(reason)
        handle = _handle_from_url(text)
        return f"https://www.instagram.com/{handle}/"
    handle = extract_handle(text)
    if not _HANDLE.match(handle) or handle.lower() in _RESERVED_PATHS:
        raise ValueError("Informe um @perfil válido do Instagram.")
    return f"https://www.instagram.com/{handle}/"


def validate_instagram_url(url: str) -> tuple[bool, str]:
    candidate = (url or "").strip()
    if not candidate:
        return False, "Informe uma URL do Instagram."
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return False, "A URL não é válida."
    if parsed.scheme.lower() != "https":
        return False, "Somente HTTPS é permitido."
    if parsed.username or parsed.password:
        return False, "URLs com credenciais não são permitidas."
    host = (parsed.hostname or "").lower()
    if host not in {"instagram.com", "www.instagram.com"}:
        return False, "Somente perfis do Instagram são permitidos neste fluxo."
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 1 or parts[0].lower() in _RESERVED_PATHS:
        return False, "Abra a página principal de um perfil, não um post ou atalho."
    if not _HANDLE.match(parts[0]):
        return False, "O nome do perfil do Instagram não é válido."
    return True, ""


def profile_insight(profile_url: str, text: str) -> ProfileInsight:
    handle = _handle_from_url(profile_url) or extract_handle(profile_url)
    lowered = (text or "").lower()
    niche = ""
    for name, words in _NICHE_WORDS.items():
        if any(word in lowered for word in words):
            niche = name
            break
    signals = tuple(
        label for label, words in _SIGNAL_WORDS.items() if any(word in lowered for word in words)
    )
    notes: list[str] = []
    if any(word in lowered for word in _SENSITIVE_HINTS):
        notes.append(
            "O texto contém temas sensíveis; eles não serão usados para segmentação "
            "nem citados na abordagem."
        )
    if not niche:
        notes.append("Nicho não confirmado; evite suposições na primeira mensagem.")
    if len(text or "") < 80:
        notes.append("Pouco texto público legível; confirme o contexto com o operador.")
    return ProfileInsight(
        handle=handle,
        url=normalize_profile_url(profile_url),
        niche=niche,
        signals=signals,
        notes=tuple(notes),
    )


def build_plan(
    profile_url: str,
    profile_text: str,
    *,
    product: str,
    hour: int | None = None,
    style: StyleProfile | None = None,
    custom_knowledge: list[dict] | None = None,
    name: str = "",
) -> InstagramPlan:
    insight = profile_insight(profile_url, profile_text)
    context = insight.niche or "seu trabalho"
    initial = draft_initial_message(
        name=name or insight.handle,
        product=product,
        hour=hour,
        profile=style,
        context=context,
        channel="dm",
    )
    comment = draft_initial_message(
        name="",
        product=product,
        hour=hour,
        profile=style,
        context=context,
        channel="comment",
    )
    objection = draft_objection_reply("já uso outro aplicativo", product)
    actions = (
        SuggestedAction(
            "follow",
            "Seguir o perfil",
            "",
            f"Acompanhar conteúdo público de {insight.niche or 'um perfil de interesse'}.",
        ),
        SuggestedAction(
            "comment",
            "Comentar um post relevante",
            comment,
            "Comentar apenas depois de ler o post e confirmar que o comentário agrega.",
        ),
        SuggestedAction(
            "send_message",
            "Enviar mensagem inicial",
            initial,
            "Mensagem inicial curta, com saudação pelo horário e uma pergunta objetiva.",
        ),
        SuggestedAction(
            "repost",
            "Avaliar repost",
            "",
            "Repostar somente conteúdo próprio ou com autorização explícita do autor.",
        ),
    )
    entries = search_playbook(
        f"instagram {insight.niche} abordagem objeção comparativo",
        custom_knowledge,
        limit=4,
    )
    return InstagramPlan(
        insight=insight,
        initial_message=initial,
        comment_draft=comment,
        objection_guidance=objection,
        actions=actions,
        checklist=comparison_checklist(),
        playbook=tuple(entries),
        delay_seconds=human_delay_seconds(initial),
        notes=insight.notes,
    )


def plan_prompt_context(plan: InstagramPlan) -> str:
    return (
        f"Contexto do Instagram: @{plan.insight.handle}; nicho {plan.insight.niche or 'não confirmado'}; "
        f"sinais {', '.join(plan.insight.signals) or 'nenhum'}. "
        "Toda ação externa exige confirmação imediata; não execute follow, comentário, "
        "repost ou DM automaticamente."
    )


def playbook_prompt(plan: InstagramPlan) -> str:
    return build_playbook_context(list(plan.playbook))
