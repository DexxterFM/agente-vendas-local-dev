"""Aprendizado de estilo opt-in, sempre local e revisável pelo operador.

Nada é capturado em segundo plano: o perfil é construído apenas com textos que
o usuário salva explicitamente na aba Aprendizado ou com mensagens antigas que
ele decide importar. O objetivo é orientar rascunhos, nunca personificar o
usuário sem transparência.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
_STOPWORDS = frozenset(
    {
        "a", "à", "ao", "aos", "as", "às", "com", "como", "da", "das", "de",
        "do", "dos", "e", "é", "em", "esta", "está", "eu", "foi", "há", "isso",
        "isto", "já", "mais", "mas", "me", "mesmo", "meu", "minha", "muito",
        "na", "nas", "não", "no", "nos", "nós", "o", "os", "ou", "para", "pela",
        "pelo", "por", "qual", "que", "se", "sem", "ser", "seu", "sua", "tem",
        "um", "uma", "você", "vocês", "vou", "estou", "aqui", "então", "sobre",
        "também", "bem", "sim", "não", "tudo", "muito", "pode", "posso",
    }
)


@dataclass(frozen=True)
class StyleProfile:
    sample_count: int
    avg_chars: int
    avg_words: int
    emoji_rate: float
    exclamation_rate: float
    question_rate: float
    lowercase_start_rate: float
    common_phrases: tuple[str, ...]
    typical_greeting: str

    @property
    def ready(self) -> bool:
        return self.sample_count >= 2

    def summary(self) -> str:
        if not self.sample_count:
            return (
                "Nenhuma amostra de estilo salva. O agente usará a persona padrão "
                "até você autorizar o aprendizado."
            )
        greeting = self.typical_greeting or "sem saudação recorrente"
        phrases = ", ".join(self.common_phrases[:4]) or "sem expressões recorrentes"
        return (
            f"{self.sample_count} amostra(s) • média de {self.avg_chars} caracteres "
            f"e {self.avg_words} palavras • emoji {self.emoji_rate:.0%} • "
            f"exclamação {self.exclamation_rate:.0%} • pergunta {self.question_rate:.0%} • "
            f"saudação: {greeting} • expressões: {phrases}"
        )

    def prompt(self) -> str:
        if not self.ready:
            return ""
        emoji = "use emojis com moderação" if self.emoji_rate >= 0.2 else "evite emojis"
        exclamation = (
            "use exclamações ocasionalmente"
            if self.exclamation_rate >= 0.2
            else "prefira frases sem exclamação"
        )
        case = (
            "pode iniciar mensagens em minúsculas, como o operador"
            if self.lowercase_start_rate >= 0.5
            else "inicie frases com maiúscula"
        )
        greeting = self.typical_greeting or "cumprimente de forma natural"
        phrases = ", ".join(self.common_phrases[:5])
        return (
            "Estilo do operador (aprendido de amostras autorizadas): "
            f"mensagens de aproximadamente {self.avg_chars} caracteres e "
            f"{self.avg_words} palavras; {emoji}; {exclamation}; {case}; "
            f"saudação típica: {greeting}."
            + (f" Expressões recorrentes: {phrases}." if phrases else "")
            + " Preserve a clareza e nunca copie dados pessoais das amostras."
        )


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZÀ-ÿ0-9']+", text.lower())


def _common_phrases(samples: list[str], limit: int = 5) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    for sample in samples:
        words = [word for word in _words(sample) if word not in _STOPWORDS and len(word) > 2]
        for size in (2, 3):
            for index in range(0, max(0, len(words) - size + 1)):
                phrase = " ".join(words[index : index + size])
                if len(phrase) < 8:
                    continue
                counts[phrase] = counts.get(phrase, 0) + 1
    repeated = [(phrase, count) for phrase, count in counts.items() if count >= 2]
    repeated.sort(key=lambda item: (-item[1], -len(item[0])))
    seen: list[str] = []
    for phrase, _count in repeated:
        if any(phrase in existing or existing in phrase for existing in seen):
            continue
        seen.append(phrase)
        if len(seen) >= limit:
            break
    return tuple(seen)


def _typical_greeting(samples: list[str]) -> str:
    greetings = (
        "bom dia",
        "boa tarde",
        "boa noite",
        "olá",
        "oi",
        "e aí",
        "tudo bem",
    )
    counts: dict[str, int] = {}
    for sample in samples:
        lowered = sample.lower()
        for greeting in greetings:
            if lowered.startswith(greeting):
                counts[greeting] = counts.get(greeting, 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)


def analyze_style(samples: list[str]) -> StyleProfile:
    clean = [str(sample).strip() for sample in samples if str(sample).strip()]
    if not clean:
        return StyleProfile(0, 0, 0, 0.0, 0.0, 0.0, 0.0, (), "")
    lengths = [len(sample) for sample in clean]
    word_counts = [len(_words(sample)) for sample in clean]
    count = len(clean)
    emoji = sum(1 for sample in clean if _EMOJI.search(sample)) / count
    exclamation = sum(1 for sample in clean if "!" in sample) / count
    question = sum(1 for sample in clean if "?" in sample) / count
    lower_starts = 0
    for sample in clean:
        first = sample.lstrip()[:1]
        lower_starts += 1 if first and first.isalpha() and first.islower() else 0
    return StyleProfile(
        sample_count=count,
        avg_chars=round(sum(lengths) / count),
        avg_words=round(sum(word_counts) / count),
        emoji_rate=emoji,
        exclamation_rate=exclamation,
        question_rate=question,
        lowercase_start_rate=lower_starts / count,
        common_phrases=_common_phrases(clean),
        typical_greeting=_typical_greeting(clean),
    )


def greeting_for_hour(hour: int | None = None) -> str:
    current = datetime.now().hour if hour is None else int(hour) % 24
    if 5 <= current < 12:
        return "Bom dia"
    if 12 <= current < 18:
        return "Boa tarde"
    return "Boa noite"


def human_delay_seconds(text: str, words_per_minute: int = 42) -> int:
    """Estimativa transparente de ritmo de digitação; não envia nada."""
    words = max(1, len(_words(text)))
    per_minute = max(15, min(120, int(words_per_minute)))
    seconds = round(words / per_minute * 60)
    return max(3, min(20, seconds))


def draft_with_style(
    body: str,
    profile: StyleProfile,
    *,
    greeting: str | None = None,
) -> str:
    """Ajusta um rascunho ao perfil sem copiar conteúdo pessoal das amostras.

    A saudação explícita sempre vence: quem chama decide o período do dia
    (bom dia/boa tarde/boa noite). O perfil orienta tom e tamanho, não o horário.
    """
    text = body.strip()
    if greeting:
        normalized = greeting[:1].upper() + greeting[1:]
        text = f"{normalized}, {text}" if not text.lower().startswith(normalized.lower()) else text
    if not profile.ready:
        return text
    if profile.emoji_rate < 0.15:
        text = _EMOJI.sub("", text).strip()
    if profile.exclamation_rate < 0.15:
        text = re.sub(r"!+", ".", text)
    if profile.lowercase_start_rate < 0.4 and text:
        text = text[0].upper() + text[1:]
    return re.sub(r"\s{2,}", " ", text).strip()
