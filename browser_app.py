"""Aplicativo instalável do Agente de Vendas Local.

Empacotado com PyInstaller: inicia um servidor HTTP local e abre a interface
como uma janela de aplicativo do Edge/Chrome, sem depender de uma aba aberta.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import subprocess
import sys
import threading
import time
import traceback
import shutil
from pathlib import Path


PORT = 4173
LOG_FILE = Path(os.getenv("LOCALAPPDATA", Path.home())) / "SalesAgentLocal" / "browser_app.log"


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as stream:
        stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def show_error(message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "Agente de Vendas Local", 0x10)
    except Exception:
        pass


def frontend_dir() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / "frontend"


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def open_app_window(url: str) -> None:
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    browser = next((path for path in candidates if Path(path).exists()), None)
    if browser:
        subprocess.Popen([browser, f"--app={url}", "--start-maximized"], close_fds=True)
    else:
        os.startfile(url)  # type: ignore[attr-defined]


def main() -> None:
    try:
        bundled = frontend_dir()
        install_frontend = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "SalesAgentLocal" / "frontend"
        install_frontend.parent.mkdir(parents=True, exist_ok=True)
        if bundled.exists():
            shutil.copytree(bundled, install_frontend, dirs_exist_ok=True)
        index = install_frontend / "index.html"
        log(f"iniciando interface instalada: {index}; existe={index.exists()}")
        if not index.exists():
            raise FileNotFoundError(f"Interface não encontrada: {index}")
        open_app_window(index.as_uri())
        log("interface CRM aberta em modo aplicativo")
    except Exception:
        details = traceback.format_exc()
        log(details)
        show_error(f"Não foi possível abrir o Agente de Vendas Local.\n\nConsulte o log em:\n{LOG_FILE}")
        raise


if __name__ == "__main__":
    main()
