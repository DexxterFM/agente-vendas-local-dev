"""Worker contínuo para a integração oficial Meta no VPS.

O navegador interno pertence ao aplicativo Windows. No VPS este processo mantém
memória, sincronização Meta, qualificação, fila e (quando configurado) despacho
de respostas dentro das permissões disponíveis para a conta.
"""
from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Quando executado pelo systemd, o diretório do script (scripts/vps) é o
# primeiro item do sys.path. Inclua explicitamente a raiz da aplicação para
# importar o mesmo núcleo usado pelo desktop.
APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.desktop_rpc import execute

RUNNING = True


def stop(*_args):
    global RUNNING
    RUNNING = False


def main() -> None:
    interval = max(10, min(300, int(os.getenv("SALES_AGENT_CYCLE_SECONDS", "30"))))
    auto_dispatch = os.getenv("SALES_AGENT_AUTO_DISPATCH", "false").strip().lower() == "true"
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # BrowserOS pertence ao app Windows e não deve ser inicializado no Linux.
    # O Ollama já é gerenciado pelo serviço existente da VPS; aqui apenas
    # confirmamos que a memória e o ciclo comercial podem abrir normalmente.
    print(
        datetime.now(timezone.utc).isoformat(),
        "worker_started",
        {"interval": interval, "auto_dispatch": auto_dispatch},
        flush=True,
    )
    while RUNNING:
        try:
            result = execute("agentCycle", {})
            if auto_dispatch and result.get("active"):
                execute("dispatchDue", {})
            print(datetime.now(timezone.utc).isoformat(), result, flush=True)
        except Exception as exc:  # systemd reinicia somente se o processo cair
            print(datetime.now(timezone.utc).isoformat(), "cycle_error", str(exc), flush=True)
        for _ in range(interval):
            if not RUNNING:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
