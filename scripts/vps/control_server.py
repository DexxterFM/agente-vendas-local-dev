"""Painel HTTP local para operar o agente que roda na VPS via túnel SSH."""
from __future__ import annotations

import json
import mimetypes
import os
import base64
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))
from core.desktop_rpc import _response
from core.memory import Memory
from scripts.vps.meta_webhook import ingest, verify_signature, verify_subscription
from scripts.vps.internal_browser import screenshot as browser_screenshot


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
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "service": "agente-vendas"})
            return
        if path == "/api/browser/screenshot":
            try:
                result = browser_screenshot()
                image = base64.b64decode(str(result.get("png") or ""), validate=True)
                if image[:8] != b"\x89PNG\r\n\x1a\n":
                    raise ValueError("PNG inválido")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(image)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(image)
            except Exception:
                self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if path == "/api/meta/webhook":
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
            challenge = verify_subscription(query)
            if challenge is None:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            body = challenge.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
        if urlsplit(self.path).path == "/api/meta/webhook":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 1_000_000:
                    raise ValueError("Corpo inválido")
                body = self.rfile.read(size)
                if not verify_signature(body, self.headers.get("X-Hub-Signature-256")):
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                memory = Memory()
                try:
                    result = ingest(memory, json.loads(body.decode("utf-8")))
                finally:
                    memory.close()
                self._json(HTTPStatus.OK, {"ok": True, **result})
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self.send_error(HTTPStatus.BAD_REQUEST)
            return
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
