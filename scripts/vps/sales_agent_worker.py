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
from scripts.vps.internal_browser_agent import cycle as internal_browser_cycle

RUNNING = True


def stop(*_args):
    global RUNNING
    RUNNING = False


def main() -> None:
    interval = max(10, min(300, int(os.getenv("SALES_AGENT_CYCLE_SECONDS", "30"))))
    auto_dispatch = os.getenv("SALES_AGENT_AUTO_DISPATCH", "false").strip().lower() == "true"
    postflow_sync = os.getenv("POSTFLOW_SYNC_ENABLED", "false").strip().lower() == "true"
    postflow_interval = max(30, min(900, int(os.getenv("POSTFLOW_SYNC_INTERVAL_SECONDS", "90"))))
    next_postflow_sync = 0.0
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # BrowserOS pertence ao app Windows e não deve ser inicializado no Linux.
    # O Ollama já é gerenciado pelo serviço existente da VPS; aqui apenas
    # confirmamos que a memória e o ciclo comercial podem abrir normalmente.
    print(
        datetime.now(timezone.utc).isoformat(),
        "worker_started",
        {"interval": interval, "auto_dispatch": auto_dispatch, "postflow_sync": postflow_sync},
        flush=True,
    )
    # O painel remoto precisa conseguir comprovar que o worker está vivo sem
    # ler o journal (que pode conter referências a conversas). Registra-se
    # somente uma telemetria agregada na memória comercial.
    execute("workerHeartbeat", {
        "active": False,
        "queued": 0,
        "synced": 0,
        "meta_sync_enabled": os.getenv("SALES_AGENT_META_SYNC_ENABLED", "false").strip().lower() in ("1", "true", "yes"),
        "postflow_sync_enabled": postflow_sync,
    })
    while RUNNING:
        try:
            if postflow_sync and time.monotonic() >= next_postflow_sync:
                result = execute("syncPostflow", {})
                next_postflow_sync = time.monotonic() + postflow_interval
                print(datetime.now(timezone.utc).isoformat(), "postflow_sync", result, flush=True)
            result = execute("agentCycle", {})
            # O navegador interno persistente é a rota principal do agente na
            # VPS. O ciclo não toca a autenticação: só começa depois que a
            # página autenticada foi detectada e mantém a confirmação visual
            # de cada mensagem antes de gravá-la na memória.
            browser_result = internal_browser_cycle()
            if auto_dispatch and result.get("active"):
                execute("dispatchDue", {})
            execute("workerHeartbeat", {
                "active": result.get("active", False),
                "queued": result.get("queued", 0),
                "synced": result.get("synced", 0),
                "meta_sync_enabled": result.get("meta_sync_enabled", False),
                "postflow_sync_enabled": postflow_sync,
                "browser": browser_result,
            })
            print(datetime.now(timezone.utc).isoformat(), {**result, "browser": browser_result}, flush=True)
        except Exception as exc:  # systemd reinicia somente se o processo cair
            print(datetime.now(timezone.utc).isoformat(), "cycle_error", str(exc), flush=True)
            if postflow_sync:
                next_postflow_sync = time.monotonic() + postflow_interval
        for _ in range(interval):
            if not RUNNING:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
