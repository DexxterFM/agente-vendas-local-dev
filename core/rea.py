"""Análise REA local baseada em evidências do código e do pacote gerado.

Não substitui o motor REA completo: produz um inventário verificável dos
componentes que a aplicação controla, com hashes e limitações explícitas.
"""
from __future__ import annotations

import ast
import hashlib
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.config import APP_VERSION, AppConfig, is_frozen, load_config, resource_root, source_root
from core.tools import ALLOWED_ACTIONS, EXTERNAL_WRITE_ACTIONS

_SOURCE_PATTERNS = (
    "app.py",
    "health_check.py",
    "sales_logic.py",
    "core/*.py",
    "adapters/*.py",
    "ui/*.py",
    "tests/*.py",
    "build.ps1",
    "run_local.ps1",
    ".env.example",
    "README.md",
    "HANDOFF_PARA_OUTRA_IA.md",
    "CONTEXTO_FRONTEND_PARA_IA.md",
)
_TABLE_PATTERN = re.compile(r"create table if not exists\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.I)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _role(relative: str) -> str:
    if relative.startswith("core/"):
        return "núcleo"
    if relative.startswith("adapters/"):
        return "adaptador"
    if relative.startswith("ui/"):
        return "interface"
    if relative.startswith("tests/"):
        return "teste"
    if relative.endswith(".ps1"):
        return "build/operação"
    return "documentação/configuração"


def _imports(path: Path) -> list[str]:
    if path.suffix != ".py":
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return sorted(names)


def _component(path: Path, root: Path) -> dict:
    relative = path.relative_to(root).as_posix()
    try:
        size = path.stat().st_size
        text = path.read_text(encoding="utf-8", errors="replace") if path.suffix in {".py", ".md", ".ps1", ".example"} or path.name == ".env.example" else ""
        lines = len(text.splitlines()) if text else None
    except OSError:
        size = 0
        lines = None
    return {
        "path": relative,
        "role": _role(relative),
        "sha256": _sha256(path),
        "bytes": size,
        "lines": lines,
        "imports": _imports(path),
    }


def _manifest_components(root: Path) -> list[dict] | None:
    manifest_path = root / "app_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    files = data.get("files")
    if not isinstance(files, list):
        return None
    components = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        components.append(
            {
                "path": item["path"],
                "role": _role(item["path"]),
                "sha256": str(item.get("sha256", "")),
                "bytes": int(item.get("bytes", 0)),
                "lines": item.get("lines"),
                "imports": item.get("imports", []),
                "source": "build-manifest",
            }
        )
    return components


def _tables_from_source(components: list[dict], root: Path) -> list[str]:
    memory = root / "core" / "memory.py"
    if not memory.is_file():
        return []
    try:
        text = memory.read_text(encoding="utf-8")
    except OSError:
        return []
    return sorted(set(match.group(1) for match in _TABLE_PATTERN.finditer(text)))


def analyze_project(
    root: Path | None = None,
    output_dir: Path | None = None,
    *,
    config: AppConfig | None = None,
) -> dict:
    root = (root or (resource_root() if is_frozen() else source_root())).resolve()
    cfg = config or load_config()
    output_dir = (output_dir or cfg.rea_dir).resolve()
    components: list[dict] = []
    for pattern in _SOURCE_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and "__pycache__" not in path.parts:
                components.append(_component(path, root))
    seen = {item["path"] for item in components}
    components = [item for item in components if item["path"] in seen]
    components.sort(key=lambda item: item["path"])

    manifest_components = _manifest_components(resource_root())
    if manifest_components:
        existing = {item["path"] for item in components}
        components.extend(item for item in manifest_components if item["path"] not in existing)
        components.sort(key=lambda item: item["path"])

    tables = _tables_from_source(components, root)
    total_bytes = sum(int(item.get("bytes") or 0) for item in components)
    total_lines = sum(int(item.get("lines") or 0) for item in components)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "version": APP_VERSION,
                "components": [(item["path"], item["sha256"]) for item in components],
                "allowlist": sorted(ALLOWED_ACTIONS),
                "write_actions": sorted(EXTERNAL_WRITE_ACTIONS),
                "tables": tables,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    findings = [
        {
            "id": "allowlist",
            "statement": "A allowlist de ferramentas permite somente resposta e navegação HTTPS.",
            "evidence": sorted(ALLOWED_ACTIONS),
        },
        {
            "id": "write-actions",
            "statement": "Ações externas de escrita estão declaradas como sujeitas a confirmação humana e não têm executor automático.",
            "evidence": sorted(EXTERNAL_WRITE_ACTIONS),
        },
        {
            "id": "sqlite-schema",
            "statement": "O schema SQLite é criado e migrado de forma idempotente.",
            "evidence": tables,
        },
        {
            "id": "local-only",
            "statement": "O modelo, o navegador e a memória são endpoints locais configuráveis.",
            "evidence": {
                "ollama": cfg.ollama_url,
                "browseros": cfg.browseros_mcp_url,
                "database": cfg.db_path.name,
            },
        },
    ]
    report = {
        "schema": "sales-agent-local/rea-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION,
        "evidence_id": fingerprint,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "frozen": bool(getattr(sys, "frozen", False)),
            "root": str(root),
        },
        "components": components,
        "metrics": {
            "component_count": len(components),
            "total_bytes": total_bytes,
            "total_lines": total_lines,
            "sqlite_tables": tables,
            "allowed_actions": sorted(ALLOWED_ACTIONS),
            "confirmable_write_actions": sorted(EXTERNAL_WRITE_ACTIONS),
        },
        "findings": findings,
        "limitations": [
            "Inspeção estática; não executa o aplicativo nem comprova comportamento em runtime.",
            "O conteúdo do PYZ de um executável PyInstaller pode permanecer opaco.",
            "Conclusões devem ser confrontadas com testes e com a execução local.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = output_dir / f"rea_{stamp}.json"
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)
    latest = output_dir / "latest.json"
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": report, "path": str(target), "summary": summary(report)}


def summary(report: dict) -> str:
    metrics = report.get("metrics", {})
    return (
        f"REA local: {metrics.get('component_count', 0)} componentes, "
        f"{metrics.get('total_lines', 0)} linhas analisadas. "
        f"Allowlist: {', '.join(metrics.get('allowed_actions', []))}. "
        f"Evidência: {report.get('evidence_id', '')[:16]}…"
    )


def latest_report(config: AppConfig | None = None) -> dict | None:
    cfg = config or load_config()
    latest = cfg.rea_dir / "latest.json"
    if not latest.is_file():
        return None
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
