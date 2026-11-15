"""Painel HTTP local para operar o agente que roda na VPS via túnel SSH."""
from __future__ import annotations

import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))
from core.desktop_rpc import _response


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "AgenteVendasControl/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        return  # Nunca registrar conversas ou corpos de RPC no journal.

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlsplit(self.path).path)
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "service": "agente-vendas"})
            return
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        candidate = (FRONTEND / relative).resolve()
        if FRONTEND not in candidate.parents or not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(str(candidate))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/api/rpc":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 1_000_000:
                raise ValueError("Corpo inválido")
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("command"), str):
                raise ValueError("Comando inválido")
        except Exception as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self._json(HTTPStatus.OK, _response(payload))


def main() -> None:
    ThreadingHTTPServer(("127.0.0.1", 8787), ControlHandler).serve_forever()


if __name__ == "__main__":
    main()
