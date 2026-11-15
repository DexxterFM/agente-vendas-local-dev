"""Playbook comercial local: objeções, ganchos e gatilhos éticos.

O playbook orienta o modelo e os rascunhos, mas não executa ações e não
inventa preço, prazo, escassez, depoimento ou comparação. Conhecimentos
adicionais ficam no SQLite e são pesquisados por palavras-chave.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from core.style import StyleProfile, draft_with_style, greeting_for_hour


@dataclass(frozen=True)
class PlaybookEntry:
    key: str
    title: str
    category: str
    keywords: tuple[str, ...]
    guidance: str

    def prompt_line(self) -> str:
        return f"- {self.title} ({self.category}): {self.guidance}"


BUILTIN_ENTRIES: tuple[PlaybookEntry, ...] = (
    PlaybookEntry(
        "objection-other-app",
        "Já uso outro aplicativo",
        "objeção",
        ("já uso", "outro app", "outro aplicativo", "concorrente", "já tenho", "uso outro"),
        "Reconheça o que a pessoa já usa, pergunte o que ela mais valoriza e o que "
        "sente falta. Compare somente fatos verificáveis do seu produto. Nunca ataque "
        "o concorrente nem prometa migração sem suporte.",
    ),
    PlaybookEntry(
        "objection-price",
        "Preço ou orçamento",
        "objeção",
        ("preço", "valor", "caro", "orçamento", "quanto custa", "desconto"),
        "Explique o valor antes de falar de desconto. Faça uma pergunta sobre o "
        "orçamento e o resultado esperado. Nunca invente desconto, condição ou prazo.",
    ),
    PlaybookEntry(
        "objection-later",
        "Vou pensar / depois",
        "objeção",
        ("vou pensar", "depois", "mais tarde", "amanhã", "sem tempo", "agora não"),
        "Respeite o tempo da pessoa. Pergunte qual informação falta para decidir e "
        "proponha um próximo passo pequeno e específico. Não insista repetidamente.",
    ),
    PlaybookEntry(
        "objection-trust",
        "Falta de confiança",
        "objeção",
        ("não confio", "golpe", "seguro", "garantia", "referência", "funciona mesmo"),
        "Ofereça prova verificável: garantia, política de suporte, demonstração ou "
        "referência com autorização. Não fabrique depoimentos, números ou prints.",
    ),
    PlaybookEntry(
        "hook-specific",
        "Gancho específico",
        "gancho",
        ("gancho", "abordagem", "primeira mensagem", "intro", "apresentação"),
        "Abra com uma observação específica e verdadeira sobre o contexto público da "
        "pessoa, uma frase de valor e uma pergunta curta. Evite elogio genérico e "
        "não finja intimidade.",
    ),
    PlaybookEntry(
        "trigger-reciprocity",
        "Reciprocidade",
        "gatilho ético",
        ("reciprocidade", "ajudar", "valor", "conteúdo"),
        "Entregue algo útil antes de pedir algo: uma dica aplicável, um checklist ou "
        "uma análise curta. Não use conteúdo genérico só para parecer útil.",
    ),
    PlaybookEntry(
        "trigger-authority",
        "Autoridade verificável",
        "gatilho ético",
        ("autoridade", "especialista", "referência", "experiência"),
        "Mostre experiência com fatos e exemplos verificáveis. Nunca invente "
        "credenciais, prêmios, clientes ou resultados.",
    ),
    PlaybookEntry(
        "trigger-scarcity",
        "Escassez real",
        "gatilho ético",
        ("escassez", "última vaga", "promoção", "urgente", "prazo"),
        "Use urgência apenas quando existir um limite real e verificável. Explique o "
        "motivo do prazo. Nunca fabrique escassez ou pressão artificial.",
    ),
    PlaybookEntry(
        "trigger-social-proof",
        "Prova social com consentimento",
        "gatilho ético",
        ("prova social", "depoimento", "case", "cliente", "resultado"),
        "Só mencione cases com autorização e dados verdadeiros. Prefira resultados "
        "contextualizados, sem prometer que o mesmo resultado se repetirá.",
    ),
    PlaybookEntry(
        "human-pacing",
        "Ritmo humano",
        "comportamento",
        ("demora", "digitação", "ritmo", "responder", "mensagem"),
        "Não envie várias mensagens seguidas. Espere a resposta, escreva de forma "
        "natural e limite o rascunho ao necessário. O tempo de digitação é uma "
        "estimativa exibida ao operador; nada é enviado automaticamente.",
    ),
    PlaybookEntry(
        "instagram-safe",
        "Instagram com consentimento",
        "canal",
        ("instagram", "feed", "seguir", "comentar", "compartilhar", "repostar", "dm"),
        "Leia apenas conteúdo público e autorizado. Seguir, comentar, repostar e "
        "enviar DM são ações externas: prepare o rascunho e peça confirmação "
        "imediata para cada uma. Não faça follow em massa, comentários repetidos ou "
        "DMs não solicitadas.",
    ),
    PlaybookEntry(
        "comparison",
        "Comparativo honesto",
        "conteúdo",
        ("comparativo", "print", "printar", "concorrente", "outro app", "tabela"),
        "Um comparativo deve usar dados públicos, atuais e verificáveis. Diga a data "
        "da fonte, diferencie fato de opinião e nunca altere prints. Envie imagens "
        "somente após revisão e confirmação humana.",
    ),
    PlaybookEntry(
        "followup",
        "Follow-up com contexto",
        "processo",
        ("follow-up", "followup", "retornar", "acompanhar", "sumiu"),
        "Retome a conversa citando o último assunto real, traga uma informação nova "
        "e faça uma única pergunta. Evite cobranças automáticas ou mensagens em série.",
    ),
)

_COMPARISON_CHECKLIST = (
    "Use apenas dados públicos e atuais; registre a fonte e a data.",
    "Diferencie recursos reais de opinião ou estimativa.",
    "Não altere capturas de tela nem invente números.",
    "Peça autorização antes de mencionar clientes ou resultados.",
    "Envie o comparativo como rascunho para revisão humana.",
)


def _normalize(text: str) -> str:
    lowered = (text or "").lower()
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFD", lowered)
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize(text))
        if len(token) > 2
    }


def _keyword_score(keywords: tuple[str, ...], normalized_query: str, tokens: set[str]) -> int:
    score = 0
    for keyword in keywords:
        normalized_keyword = _normalize(keyword)
        if not normalized_keyword:
            continue
        if " " in normalized_keyword:
            if normalized_keyword in normalized_query:
                score += 2
        elif normalized_keyword in tokens:
            score += 1
    return score


def search_playbook(
    query: str,
    custom_entries: list[dict] | None = None,
    limit: int = 4,
) -> list[PlaybookEntry]:
    normalized_query = _normalize(query)
    tokens = _tokens(query)
    scored: list[tuple[int, PlaybookEntry]] = []
    for entry in BUILTIN_ENTRIES:
        score = _keyword_score(entry.keywords, normalized_query, tokens)
        if _normalize(entry.category) in normalized_query:
            score += 1
        if score:
            scored.append((score, entry))
    for item in custom_entries or []:
        title = str(item.get("title") or "")
        content = str(item.get("content") or "")
        tags = str(item.get("tags") or "")
        score = len(tokens & _tokens(f"{title} {content} {tags}"))
        if score:
            scored.append(
                (
                    score,
                    PlaybookEntry(
                        key=f"custom:{item.get('id', '')}",
                        title=title or "Conhecimento local",
                        category="personalizado",
                        keywords=tuple(_tokens(f"{title} {tags}")),
                        guidance=content,
                    ),
                )
            )
    scored.sort(key=lambda item: (-item[0], item[1].title))
    return [entry for _score, entry in scored[: max(1, min(8, limit))]]


def build_playbook_context(entries: list[PlaybookEntry]) -> str:
    if not entries:
        return ""
    return (
        "Conhecimentos comerciais relevantes para esta conversa "
        "(use como orientação, não como script rígido):\n"
        + "\n".join(entry.prompt_line() for entry in entries)
    )


def comparison_checklist() -> tuple[str, ...]:
    return _COMPARISON_CHECKLIST


def draft_initial_message(
    name: str,
    product: str,
    *,
    hour: int | None = None,
    profile: StyleProfile | None = None,
    context: str = "",
    channel: str = "dm",
) -> str:
    greeting = greeting_for_hour(hour)
    first_name = (name or "").strip().split()[0] if (name or "").strip() else ""
    who = f", {first_name}" if first_name else ""
    if channel == "comment":
        body = (
            "Vi seu post e o ponto sobre "
            f"{(context or 'o tema').strip()} faz sentido. Como você está lidando com isso hoje?"
        )
    else:
        body = (
            f"tudo bem? Vi seu interesse em {(context or product).strip()} e queria "
            "entender qual resultado você busca. Posso te fazer uma pergunta rápida?"
        )
    if profile:
        return draft_with_style(body, profile, greeting=f"{greeting}{who}".strip())
    return f"{greeting}{who}, {body}"


def draft_objection_reply(objection: str, product: str) -> str:
    text = (objection or "").lower()
    if any(word in text for word in ("já uso", "outro app", "outro aplicativo", "concorrente")):
        return (
            f"Faz sentido continuar com o que já funciona. Para eu comparar de forma honesta "
            f"com {product}: o que você mais valoriza hoje e o que sentiria falta se mudasse?"
        )
    if any(word in text for word in ("caro", "preço", "valor", "orçamento")):
        return (
            f"Entendo a preocupação com o investimento. Para não te passar uma informação "
            f"genérica sobre {product}, qual resultado você espera e qual faixa de orçamento "
            "faz sentido para o seu momento?"
        )
    if any(word in text for word in ("pensar", "depois", "mais tarde", "sem tempo")):
        return (
            "Claro, sem pressa. Qual informação ainda falta para você decidir? "
            "Posso te enviar só o que for útil e retomamos quando fizer sentido."
        )
    if any(word in text for word in ("confio", "golpe", "seguro", "garantia")):
        return (
            "É justo querer segurança antes de avançar. Posso te mostrar a garantia, "
            "a política de suporte e uma demonstração objetiva. O que precisa ficar "
            "claro para você se sentir seguro?"
        )
    return (
        f"Entendi. Para eu te ajudar sem enrolação sobre {product}: o que está "
        "pesando mais na sua decisão neste momento?"
    )
