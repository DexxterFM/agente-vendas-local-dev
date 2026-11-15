"""Configuração local da aplicação, sem dependências externas e sem segredos."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

APP_NAME = "Agente de Vendas Local"
APP_VERSION = "0.3.0"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def install_root() -> Path:
    """Diretório do executável ou raiz do projeto em desenvolvimento."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return source_root()


def resource_root() -> Path:
    """Raiz de recursos embarcados pelo PyInstaller."""
    return Path(getattr(sys, "_MEIPASS", install_root()))


def data_root() -> Path:
    override = os.getenv("SALES_AGENT_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return (Path(base) / "SalesAgentLocal").resolve()
    return source_root()


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def _read_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _read_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _default_browser_server() -> str:
    return str(
        Path(os.getenv("LOCALAPPDATA", ""))
        / "BrowserClaw"
        / "Application"
        / "155.0.8318.26"
        / "BrowserClawServer"
        / "default"
        / "resources"
        / "bin"
        / "browseros-claw-server.exe"
    )


def _default_browser_config() -> str:
    return str(
        Path(os.getenv("LOCALAPPDATA", ""))
        / "BrowserClaw"
        / "User Data"
        / ".browseros"
        / "config.json"
    )


@dataclass(frozen=True)
class AppConfig:
    ollama_url: str
    ollama_model: str
    local_llm_url: str
    local_llm_model: str
    browseros_mcp_url: str
    rea_mcp_url: str
    db_path: Path
    data_dir: Path
    audit_dir: Path
    persona_key: str
    product_name: str
    browseros_server: str
    browseros_config: str
    ollama_exe: str
    max_page_chars: int
    http_timeout: float
    version: str = APP_VERSION

    @property
    def ollama_chat_url(self) -> str:
        base = self.ollama_url.rstrip("/")
        return base if base.endswith("/api/chat") else f"{base}/api/chat"

    @property
    def ollama_tags_url(self) -> str:
        base = self.ollama_url.rstrip("/")
        if base.endswith("/api/chat"):
            base = base[: -len("/api/chat")]
        return base if base.endswith("/api/tags") else f"{base}/api/tags"

    @property
    def ollama_port(self) -> int:
        parsed = urlparse(self.ollama_tags_url)
        return parsed.port or (443 if parsed.scheme == "https" else 80)

    @property
    def browseros_port(self) -> int:
        parsed = urlparse(self.browseros_mcp_url)
        return parsed.port or (443 if parsed.scheme == "https" else 80)

    @property
    def rea_dir(self) -> Path:
        return self.audit_dir / "rea"


def load_config() -> AppConfig:
    # O .env fica ao lado do executável/projeto e nunca é versionado.
    _load_dotenv(install_root() / ".env")
    data_dir = data_root()
    db_override = os.getenv("SALES_AGENT_DB", "").strip()
    db_path = Path(db_override).expanduser().resolve() if db_override else data_dir / "sales_agent.sqlite3"
    audit_dir = data_dir / "audit"
    return AppConfig(
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip(),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:0.6b").strip(),
        local_llm_url=os.getenv("LOCAL_LLM_URL", "").strip(),
        local_llm_model=os.getenv("LOCAL_LLM_MODEL", "qwen3-sales").strip(),
        browseros_mcp_url=os.getenv("BROWSEROS_MCP_URL", "http://127.0.0.1:9200/mcp").strip(),
        rea_mcp_url=os.getenv("REA_MCP_URL", "").strip(),
        db_path=db_path,
        data_dir=data_dir,
        audit_dir=audit_dir,
        persona_key=os.getenv("SALES_PERSONA", "consultivo").strip() or "consultivo",
        product_name=os.getenv("SALES_PRODUCT_NAME", "nossa solução").strip() or "nossa solução",
        browseros_server=os.getenv("BROWSEROS_SERVER", _default_browser_server()).strip(),
        browseros_config=os.getenv("BROWSEROS_CONFIG", _default_browser_config()).strip(),
        ollama_exe=os.getenv("OLLAMA_EXE", "").strip(),
        max_page_chars=_read_int("SALES_MAX_PAGE_CHARS", 12000, 1000, 100000),
        http_timeout=_read_float("SALES_HTTP_TIMEOUT", 60.0, 5.0, 300.0),
    )
