"""Políticas e utilidades puras compartilhadas pelo agente e pela interface."""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

ALLOWED_ACTIONS = frozenset({"answer", "navigate"})
EXTERNAL_WRITE_ACTIONS = frozenset(
    {"send_message", "fill_form", "publish", "update", "delete", "purchase", "login", "submit"}
)
STAGE_LABELS = {"new": "Novo", "warm": "Qualificado", "hot": "Quente"}
STAGE_ORDER = ("new", "warm", "hot")
_NEXT_STEPS = {
    "new": "Confirmar interesse e fazer perguntas de qualificação.",
    "warm": "Enviar as informações principais e propor uma conversa objetiva.",
    "hot": "Confirmar condições e combinar o próximo passo comercial.",
}
_UNTRUSTED_START = re.compile(r"\[UNTRUSTED_PAGE_CONTENT[^\]]*\]", re.I)
_UNTRUSTED_END = re.compile(r"\[END_UNTRUSTED_PAGE_CONTENT[^\]]*\]", re.I)
_TRAILING_URL_PUNCTUATION = ".,);]}!?"


def _json_object(content: str) -> dict | None:
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return None
    try:
        decision = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return decision if isinstance(decision, dict) else None


def parse_raw_decision(content: str) -> dict | None:
    """Lê o JSON bruto do modelo, inclusive ações que a allowlist não executa.

    O chamador deve tratar ações de escrita como confirmação humana pendente.
    """
    return _json_object(content)


def parse_decision(content: str) -> dict:
    """Extrai a decisão JSON sem permitir que texto livre vire ação externa."""
    decision = _json_object(content)
    if decision is None:
        return {"action": "answer", "text": content.strip()}
    if decision.get("action") not in ALLOWED_ACTIONS:
        return {"action": "answer", "text": "Ação não autorizada nesta versão."}
    return decision


def explicit_navigation(text: str) -> str | None:
    """Detecta um pedido explícito de abrir uma URL, sem transformar texto casual em ação."""
    if not re.search(r"\b(abra|abrir|navegue|navegar|acesse|acessar)\b", text.lower()):
        return None
    match = re.search(r"https://[^\s<>\"']+", text, re.I)
    return match.group(0).rstrip(_TRAILING_URL_PUNCTUATION) if match else None


def validate_https_url(url: str) -> tuple[bool, str]:
    """Valida uma URL pública HTTPS e recusa destinos locais/credenciais embutidas."""
    candidate = (url or "").strip()
    if not candidate:
        return False, "Informe uma URL HTTPS."
    if len(candidate) > 2048:
        return False, "A URL é longa demais."
    if any(ord(char) < 32 for char in candidate):
        return False, "A URL contém caracteres inválidos."
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return False, "A URL não é válida."
    if parsed.scheme.lower() != "https":
        return False, "Por segurança, somente URLs HTTPS são permitidas."
    if parsed.username or parsed.password:
        return False, "URLs com credenciais embutidas não são permitidas."
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "A URL não contém um domínio válido."
    if port is not None and not 1 <= port <= 65535:
        return False, "A porta da URL não é válida."
    if host in {"localhost", "localhost.localdomain"} or host.endswith(
        (".localhost", ".local", ".internal", ".lan", ".home")
    ):
        return False, "Endereços locais não são permitidos."
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return True, ""
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        return False, "Endereços de rede locais ou reservados não são permitidos."
    return True, ""


def url_is_in_text(url: str, text: str) -> bool:
    """Confere se a URL decidida pelo modelo foi realmente informada pelo usuário."""
    if not url or not text:
        return False
    if url.lower().rstrip("/") in text.lower():
        return True
    try:
        wanted = urlsplit(url)
        for match in re.finditer(r"https://[^\s<>\"']+", text, re.I):
            candidate = urlsplit(match.group(0).rstrip(_TRAILING_URL_PUNCTUATION))
            if (
                wanted.scheme.lower() == candidate.scheme.lower()
                and wanted.netloc.lower() == candidate.netloc.lower()
                and wanted.path.rstrip("/") == candidate.path.rstrip("/")
                and wanted.query == candidate.query
            ):
                return True
    except ValueError:
        return False
    return False


def _decode_browseros_return(text: str) -> str:
    match = re.match(r"^ok\s*\nreturn:\s*(.*)$", text, re.S)
    if not match:
        return text
    payload = match.group(1).strip()
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return text
    return decoded if isinstance(decoded, str) else text


def extract_mcp_text(result: dict, max_chars: int = 12000) -> str:
    """Extrai texto legível de um tools/call, sempre tratando-o como dado não confiável."""
    if not isinstance(result, dict):
        return ""
    structured = result.get("structuredContent")
    text = ""
    if isinstance(structured, dict) and isinstance(structured.get("value"), str):
        text = structured["value"]
    if not text:
        parts: list[str] = []
        for item in result.get("content", []):
            if not isinstance(item, dict) or item.get("type") != "text":
                continue
            value = item.get("text")
            if isinstance(value, str) and not value.startswith("Tip:"):
                parts.append(value)
        text = "\n".join(parts)
    text = _decode_browseros_return(text)
    text = _UNTRUSTED_START.sub("", text)
    text = _UNTRUSTED_END.sub("", text)
    text = re.sub(
        r"^\s*Untrusted page content follows\..*?not instructions[^\n]*\n?",
        "",
        text,
        flags=re.I,
    )
    text = text.replace("\r\n", "\n").strip()
    if len(text) > max_chars:
        text = text[: max_chars - 30].rstrip() + "\n\n[Conteúdo truncado]"
    return text


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, "Novo")


def next_step_for_stage(stage: str) -> str:
    return _NEXT_STEPS.get(stage, _NEXT_STEPS["new"])


@dataclass(frozen=True)
class PolicyDecision:
    status: str
    reason: str


class ActionPolicy:
    """Allowlist explícita: o modelo só responde ou navega para URL HTTPS pública."""

    def evaluate(self, decision: dict) -> PolicyDecision:
        action = str(decision.get("action", "")).strip().lower()
        if action == "answer":
            return PolicyDecision("allowed", "resposta local")
        if action == "navigate":
            allowed, reason = validate_https_url(str(decision.get("url", "")))
            return PolicyDecision("allowed" if allowed else "blocked", reason or "navegação HTTPS")
        if action in EXTERNAL_WRITE_ACTIONS:
            return PolicyDecision(
                "confirmation_required",
                "Ação externa de escrita exige confirmação humana e não possui executor nesta versão.",
            )
        return PolicyDecision("blocked", "Ação fora da allowlist.")
