"""Cliente mínimo do navegador interno persistente da VPS via DevTools.

Não depende de extensões, sessão local ou serviços externos. O processo do
navegador pertence ao systemd e guarda a sessão em um diretório do agente.
"""
from __future__ import annotations

import base64
import json
import socket
import struct
import time
import urllib.parse
import urllib.request
from itertools import count
from typing import Any


DEBUG_URL = "http://127.0.0.1:9222"


class InternalBrowserError(RuntimeError):
    pass


def _http(path: str, method: str = "GET") -> Any:
    request = urllib.request.Request(DEBUG_URL + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise InternalBrowserError("Navegador interno indisponível") from exc


def _masked_frame(payload: bytes) -> bytes:
    mask = b"agent"
    size = len(payload)
    if size < 126:
        header = bytes([0x81, 0x80 | size])
    elif size <= 0xFFFF:
        header = bytes([0x81, 0x80 | 126]) + struct.pack("!H", size)
    else:
        header = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", size)
    return header + mask + bytes(value ^ mask[index % 4] for index, value in enumerate(payload))


def _receive(sock: socket.socket) -> bytes:
    first = sock.recv(2)
    if len(first) != 2:
        raise InternalBrowserError("Conexão interna encerrada")
    opcode = first[0] & 0x0F
    length = first[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", sock.recv(8))[0]
    masked = bool(first[1] & 0x80)
    mask = sock.recv(4) if masked else b""
    payload = b""
    while len(payload) < length:
        packet = sock.recv(min(65536, length - len(payload)))
        if not packet:
            raise InternalBrowserError("Conexão interna encerrada")
        payload += packet
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    if opcode == 8:
        raise InternalBrowserError("Navegador interno encerrou a sessão")
    return payload


class DevTools:
    def __init__(self, websocket_url: str) -> None:
        parsed = urllib.parse.urlparse(websocket_url)
        self.socket = socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=8)
        self.socket.settimeout(12)
        key = base64.b64encode(b"agente-vendas-interno").decode("ascii")
        request = (
            f"GET {parsed.path}{'?' + parsed.query if parsed.query else ''} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port or 80}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.socket.recv(2048)
            if not chunk:
                raise InternalBrowserError("Falha ao conectar ao navegador interno")
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise InternalBrowserError("DevTools recusou a conexão interna")
        self.ids = count(1)

    def close(self) -> None:
        try:
            self.socket.close()
        except OSError:
            pass

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        call_id = next(self.ids)
        self.socket.sendall(_masked_frame(json.dumps({"id": call_id, "method": method, "params": params or {}}, separators=(",", ":")).encode("utf-8")))
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                payload = json.loads(_receive(self.socket).decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if payload.get("id") != call_id:
                continue
            if "error" in payload:
                raise InternalBrowserError(str(payload["error"].get("message") or "Falha no navegador interno"))
            return payload.get("result") or {}
        raise InternalBrowserError("Navegador interno não respondeu")


def _target() -> dict[str, Any]:
    pages = _http("/json/list")
    if not isinstance(pages, list):
        raise InternalBrowserError("Lista de páginas inválida")
    page = next((item for item in pages if item.get("type") == "page" and "instagram.com" in str(item.get("url", ""))), None)
    if page:
        return page
    created = _http("/json/new?" + urllib.parse.quote("https://www.instagram.com/", safe="/:?=&"), method="PUT")
    if not isinstance(created, dict):
        raise InternalBrowserError("Não foi possível abrir a página interna")
    return created


def _with_page(callback):
    page = _target()
    ws = DevTools(str(page.get("webSocketDebuggerUrl") or ""))
    try:
        return callback(ws)
    finally:
        ws.close()


def status() -> dict[str, Any]:
    try:
        version = _http("/json/version")
        pages = _http("/json/list")
        active = next((item for item in pages if item.get("type") == "page" and "instagram.com" in str(item.get("url", ""))), None)
        return {"running": True, "ready": bool(active), "product": str(version.get("Browser", "navegador interno"))[:80]}
    except InternalBrowserError:
        return {"running": False, "ready": False, "product": ""}


def evaluate(expression: str) -> Any:
    def run(page: DevTools):
        result = page.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        details = result.get("exceptionDetails")
        if details:
            raise InternalBrowserError("Leitura interna recusada pela página")
        return (result.get("result") or {}).get("value")
    return _with_page(run)


def snapshot() -> dict[str, Any]:
    expression = """(()=>{const url=location.href;const text=(document.body?.innerText||'').slice(0,12000);const fields=[...document.querySelectorAll('input,textarea,[contenteditable=true]')].map(e=>[e.name,e.type,e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ').toLowerCase());const authenticated=!fields.some(v=>/password|senha|username|login|c[oó]digo/.test(v));const controls=[...document.querySelectorAll('a,button,[role=button],[role=link]')];const label=e=>[e.innerText,e.getAttribute('aria-label'),e.getAttribute('title'),e.getAttribute('href')].filter(Boolean).join(' ');return {url,authenticated,hasMessages:controls.some(e=>/mensagens|messages|direct/i.test(label(e))),hasNotifications:controls.some(e=>/notifica|notifications|activity/i.test(label(e))),text};})()"""
    value = evaluate(expression)
    if not isinstance(value, dict):
        raise InternalBrowserError("Leitura do navegador interno inválida")
    # O texto nunca é retornado pelo endpoint de estado; o ciclo do agente usa
    # este dado internamente. O painel vê somente metadados agregados.
    return {key: value.get(key) for key in ("url", "authenticated", "hasMessages", "hasNotifications")}


def screenshot() -> str:
    def run(page: DevTools):
        page.call("Page.enable")
        return str(page.call("Page.captureScreenshot", {"format": "png"}).get("data") or "")
    return _with_page(run)
