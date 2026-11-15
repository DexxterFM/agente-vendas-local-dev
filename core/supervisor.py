"""Supervisor local: diagnostica e inicia serviços sem duplicar processos."""
from __future__ import annotations

import shutil
import socket
import sqlite3
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

from adapters.mcp import MCPClient
from adapters.ollama import OllamaClient
from adapters.instagram_meta import check_connection as instagram_check_connection
from core.config import AppConfig, load_config
from core.memory import Memory


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.8) -> bool:
    try:
        with socket.socket() as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def _status(status: str, detail: str, **meta: object) -> dict:
    return {"status": status, "detail": detail, "meta": meta}


class Supervisor:
    def __init__(
        self,
        config: AppConfig | None = None,
        memory: Memory | None = None,
        *,
        port_checker: Callable[[int], bool] | None = None,
        popen: Callable[..., object] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or load_config()
        self.memory = memory
        self._port_open = port_checker or port_open
        self._popen = popen or subprocess.Popen
        self._sleep = sleep or time.sleep

    # ---------------------------------------------------------------- saúde
    def _ollama_health(self) -> dict:
        client = OllamaClient(self.config.ollama_url, self.config.ollama_model)
        try:
            health = client.health()
        except Exception as exc:
            return _status("unavailable", f"API local indisponível: {str(exc)[:160]}")
        if not health.api:
            return _status("unavailable", "API local indisponível em 127.0.0.1.")
        if not health.model_available:
            return _status(
                "attention",
                f"API conectada, mas o modelo {self.config.ollama_model} não está instalado.",
                models=len(health.models),
            )
        return _status(
            "connected",
            f"API local ativa com o modelo {self.config.ollama_model}.",
            models=len(health.models),
        )

    def _browser_health(self, deep: bool) -> dict:
        # O aplicativo Electron já fornece o navegador que opera o Instagram.
        # BrowserOS só é uma integração complementar e, na VPS, não deve
        # aparecer como falha quando não foi explicitamente configurado.
        if not os.getenv("BROWSEROS_MCP_URL", "").strip():
            return _status(
                "not_configured",
                "Navegador interno do aplicativo é o canal ativo; BrowserOS MCP é opcional na VPS.",
            )
        if not self._port_open(self.config.browseros_port):
            return _status("unavailable", "BrowserOS MCP não está escutando na porta local.")
        if not deep:
            return _status("connected", "Porta MCP local aberta.")
        try:
            MCPClient(
                self.config.browseros_mcp_url,
                timeout=2.5,
                client_name="sales-agent-health",
                require_session=True,
            ).ping()
        except Exception as exc:
            return _status("attention", f"Porta aberta, mas o MCP não respondeu: {str(exc)[:140]}")
        return _status("connected", "BrowserOS MCP conectado.")

    def _memory_health(self) -> dict:
        try:
            if self.memory is not None:
                if not self.memory.health():
                    return _status("unavailable", "SQLite não respondeu.")
                counts = self.memory.counts()
            else:
                path = Path(self.config.db_path)
                if not path.is_file():
                    return _status("attention", "Banco será criado na primeira execução.")
                with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as db:
                    leads = db.execute("select count(*) from leads").fetchone()[0]
                counts = {"leads": int(leads)}
        except Exception as exc:
            return _status("unavailable", f"Falha ao ler o SQLite: {str(exc)[:140]}")
        return _status(
            "connected",
            f"Memória SQLite ativa • {counts.get('leads', 0)} leads, "
            f"{counts.get('messages', 0)} mensagens.",
            **counts,
        )

    def _rea_health(self) -> dict:
        reports = sorted(self.config.rea_dir.glob("rea_*.json")) if self.config.rea_dir.is_dir() else []
        if self.config.rea_mcp_url:
            try:
                MCPClient(self.config.rea_mcp_url, timeout=2.5, require_session=False).ping()
                return _status("connected", "REA MCP conectado.")
            except Exception as exc:
                return _status("attention", f"REA MCP configurado, mas indisponível: {str(exc)[:120]}")
        if reports:
            latest = reports[-1]
            try:
                stamp = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            except OSError:
                stamp = "data desconhecida"
            return _status("connected", f"Análise local disponível • último relatório {stamp}.")
        return _status("attention", "Análise local disponível; ainda não executada.")

    def _instagram_health(self) -> dict:
        result = instagram_check_connection(timeout=min(self.config.http_timeout, 15.0))
        return _status(result.get("status", "unavailable"), result.get("detail", "Instagram não configurado."), **result.get("meta", {}))

    def _postflow_health(self) -> dict:
        try:
            from adapters.postflow import status
            result = status()
            detail = result.get("detail", "PostFlow conectado." if result.get("status") == "connected" else "PostFlow indisponível.")
            return _status(
                result.get("status", "unavailable"), detail,
                threads=int(result.get("threads", 0) or 0),
            )
        except Exception as exc:
            return _status("unavailable", f"PostFlow indisponível: {exc}")

    def _erp_health(self) -> dict:
        base = os.getenv("ERP_CLINICATEA_API_BASE_URL", "").strip().rstrip("/")
        if not base:
            return _status("not_configured", "Endpoint do ERP não configurado.")
        headers = {"Accept": "application/json"}
        token = os.getenv("ERP_CLINICATEA_API_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            request = urllib.request.Request(f"{base}/health", headers=headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                return _status("connected" if 200 <= response.status < 300 else "unavailable", "ERP Clínica TEA disponível.")
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            return _status("unavailable", f"ERP Clínica TEA indisponível: {exc}")

    def health(self, deep: bool = True) -> dict[str, dict]:
        ollama = self._ollama_health()
        browser = self._browser_health(deep)
        memory = self._memory_health()
        rea = self._rea_health()
        instagram = self._instagram_health()
        postflow = self._postflow_health()
        erp = self._erp_health()
        model_status = ollama["status"]
        model_detail = self.config.ollama_model
        if model_status == "attention":
            model_detail = f"{self.config.ollama_model} (não instalado)"
        elif model_status == "unavailable":
            model_detail = f"{self.config.ollama_model} (Ollama offline)"
        result = {
            "ollama": {**ollama, "label": "Ollama"},
            "model": _status(
                "connected" if model_status == "connected" else model_status,
                model_detail,
            ),
            "browseros": {**browser, "label": "BrowserOS MCP (opcional)"},
            "memory": {**memory, "label": "Memória SQLite"},
            "rea": {**rea, "label": "REA"},
            "privacy": _status(
                "connected",
                "Dados comerciais processados localmente; operação segue os controles ativos do agente.",
            ),
            "instagram": {**instagram, "label": "Instagram/Meta"},
            "postflow": {**postflow, "label": "PostFlow"},
            "erp": {**erp, "label": "ERP Clínica TEA"},
        }
        result["model"]["label"] = "Modelo"
        result["privacy"]["label"] = "Privacidade"
        result["model"]["meta"] = {"model": self.config.ollama_model}
        result["privacy"]["meta"] = {}
        return result

    def quick_status(self) -> dict:
        """Compatibilidade com o health_check.py e consumidores antigos."""
        health = self.health(deep=False)
        return {
            "ollama_port": self._port_open(self.config.ollama_port),
            "ollama_api": health["ollama"]["status"] == "connected",
            "browseros_mcp_port": self._port_open(self.config.browseros_port),
            "model": self.config.ollama_model,
            "model_available": health["model"]["status"] == "connected",
            "sqlite": health["memory"]["status"] == "connected",
            "rea_report": health["rea"]["status"] == "connected",
        }

    # ------------------------------------------------------------ inicialização
    def start_services(self) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        # The desktop product owns its inference process.  When Electron has
        # supplied LOCAL_LLM_URL, do not start a second Ollama service or an
        # external browser: both would duplicate memory-heavy processes.
        if os.getenv("LOCAL_LLM_URL"):
            results.append({
                "name": "Motor de IA embutido",
                "running": True,
                "detail": "llama.cpp local iniciado pelo aplicativo",
            })
        else:
            results.append(self._start_ollama())
        if self.memory is not None:
            for item in results:
                self.memory.audit(
                    "service.start",
                    item["name"],
                    "ok" if item["ok"] else "attention",
                    item["detail"],
                )
        return results

    def _start_ollama(self) -> dict[str, str]:
        if self._port_open(self.config.ollama_port):
            return {"name": "Ollama", "ok": True, "detail": "já estava em execução"}
        executable = self.config.ollama_exe.strip()
        if not executable:
            executable = shutil.which("ollama") or ""
        if not executable:
            local = Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
            if local.is_file():
                executable = str(local)
        if not executable or not Path(executable).is_file():
            return {"name": "Ollama", "ok": False, "detail": "executável não encontrado"}
        try:
            self._popen(
                [executable, "serve"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            return {"name": "Ollama", "ok": False, "detail": f"falha ao iniciar: {exc}"}
        for _ in range(16):
            if self._port_open(self.config.ollama_port):
                return {"name": "Ollama", "ok": True, "detail": "iniciado"}
            self._sleep(0.5)
        return {"name": "Ollama", "ok": False, "detail": "iniciado, mas a porta ainda não respondeu"}

    def _start_browseros(self) -> dict[str, str]:
        if self._port_open(self.config.browseros_port):
            return {"name": "BrowserOS", "ok": True, "detail": "já estava em execução"}
        server = Path(self.config.browseros_server)
        config = Path(self.config.browseros_config)
        if not server.is_file() or not config.is_file():
            return {
                "name": "BrowserOS",
                "ok": False,
                "detail": "servidor ou configuração não encontrados",
            }
        try:
            self._popen(
                [str(server), "--config", str(config)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            return {"name": "BrowserOS", "ok": False, "detail": f"falha ao iniciar: {exc}"}
        for _ in range(20):
            if self._port_open(self.config.browseros_port):
                return {"name": "BrowserOS", "ok": True, "detail": "iniciado"}
            self._sleep(0.5)
        return {
            "name": "BrowserOS",
            "ok": False,
            "detail": "iniciado, mas o MCP ainda não respondeu",
        }


if __name__ == "__main__":
    print(Supervisor().quick_status())
