from __future__ import annotations

import json
import os
import socket
import urllib.request


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.8)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ollama_ready() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def collect() -> dict[str, bool | str]:
    return {
        "ollama_port": port_open(11434),
        "ollama_api": ollama_ready(),
        "browseros_mcp_port": port_open(9210),
        "model": os.getenv("OLLAMA_MODEL", "qwen3:0.6b"),
    }


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
