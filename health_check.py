from __future__ import annotations

import argparse
import json

from core.config import load_config
from core.supervisor import Supervisor, port_open


def ollama_ready() -> bool:
    config = load_config()
    return port_open(config.ollama_port)


def collect(deep: bool = False) -> dict:
    supervisor = Supervisor()
    return supervisor.health(deep=True) if deep else supervisor.quick_status()


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico local do Agente de Vendas Local")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Testa também o handshake MCP do BrowserOS e os detalhes de cada serviço.",
    )
    args = parser.parse_args()
    print(json.dumps(collect(deep=args.deep), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
