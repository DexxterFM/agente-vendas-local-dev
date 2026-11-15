"""Ponto de entrada e exports de compatibilidade do Agente de Vendas Local."""
from __future__ import annotations

import sys

from core.config import APP_NAME, APP_VERSION, AppConfig, load_config
from core.memory import Memory
from core.tools import explicit_navigation, parse_decision

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "AppConfig",
    "Memory",
    "explicit_navigation",
    "load_config",
    "main",
    "parse_decision",
]


def main() -> None:
    # Diagnóstico sem interface: útil no executável empacotado e em suporte.
    if "--rea" in sys.argv[1:]:
        from core.rea import analyze_project

        result = analyze_project()
        if sys.stdout:
            print(result["path"])
        return
    # A interface é importada somente ao iniciar, mantendo os testes de núcleo leves.
    from ui.desktop import run

    run()


if __name__ == "__main__":
    main()
