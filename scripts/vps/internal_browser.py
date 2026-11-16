"""Cliente mínimo do navegador interno persistente da VPS via DevTools.

Não depende de extensões, sessão local ou serviços externos. O processo do
navegador pertence ao systemd e guarda a sessão em um diretório do agente.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.parse
import urllib.request
from itertools import count
from typing import Any

try:
    import websocket
except ImportError:  # a unidade da VPS instala python3-websocket-client
    websocket = None


DEBUG_URL = "http://127.0.0.1:9222"
_PRIMARY_HOSTS = {"instagram.com", "www.instagram.com"}
_ACCESS_HOSTS = _PRIMARY_HOSTS | {"facebook.com", "www.facebook.com"}


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
        if websocket is None:
            raise InternalBrowserError("Canal do navegador interno não está instalado")
        try:
            self.socket = websocket.create_connection(websocket_url, timeout=12, origin="http://127.0.0.1:9222")
        except Exception as exc:
            raise InternalBrowserError("Falha ao conectar ao navegador interno") from exc
        self.ids = count(1)

    def close(self) -> None:
        try:
            self.socket.close()
        except OSError:
            pass

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        call_id = next(self.ids)
        self.socket.send(json.dumps({"id": call_id, "method": method, "params": params or {}}, separators=(",", ":")))
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                payload = json.loads(self.socket.recv())
            except (json.JSONDecodeError, TypeError):
                continue
            if payload.get("id") != call_id:
                continue
            if "error" in payload:
                raise InternalBrowserError(str(payload["error"].get("message") or "Falha no navegador interno"))
            return payload.get("result") or {}
        raise InternalBrowserError("Navegador interno não respondeu")


def _is_access_window(item: dict[str, Any]) -> bool:
    """Retorna somente janelas abertas pelo fluxo de entrada da própria conta."""
    try:
        parsed = urllib.parse.urlparse(str(item.get("url") or ""))
    except (TypeError, ValueError):
        return False
    return parsed.scheme == "https" and parsed.hostname in _ACCESS_HOSTS


def _is_recovery_window(item: dict[str, Any]) -> bool:
    """Janelas de recuperação podem abrir fora da página principal.

    A tela remota precisa acompanhá-las, caso contrário o operador enxerga a
    página inicial carregando enquanto o campo de SMS foi aberto em outra
    janela pelo próprio fluxo de acesso.
    """
    parsed = urllib.parse.urlparse(str(item.get("url") or ""))
    if parsed.hostname not in {"facebook.com", "www.facebook.com"}:
        return False
    path = parsed.path.casefold()
    return any(marker in path for marker in ("/login", "/recover", "/identify", "/checkpoint"))


def _target() -> dict[str, Any]:
    pages = _http("/json/list")
    if not isinstance(pages, list):
        raise InternalBrowserError("Lista de páginas inválida")
    windows = [item for item in pages if isinstance(item, dict) and item.get("type") == "page" and _is_access_window(item)]
    # Prioriza a janela de recuperação aberta pelo operador. A página
    # principal permanece disponível e volta a ser selecionada quando a
    # recuperação termina ou é fechada.
    page = next((item for item in windows if _is_recovery_window(item)), None)
    if page is None:
        page = next((item for item in windows if urllib.parse.urlparse(str(item.get("url") or "")).hostname in _PRIMARY_HOSTS), None)
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
        active = next((item for item in pages if isinstance(item, dict) and item.get("type") == "page" and _is_access_window(item)), None)
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
    expression = """(()=>{const url=location.href;const text=(document.body?.innerText||'').slice(0,12000);const path=location.pathname.toLowerCase();const fields=[...document.querySelectorAll('input,textarea,[contenteditable=true]')].map(e=>[e.name,e.type,e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ').toLowerCase());const controls=[...document.querySelectorAll('a,button,[role=button],[role=link]')];const label=e=>[e.innerText,e.getAttribute('aria-label'),e.getAttribute('title'),e.getAttribute('href')].filter(Boolean).join(' ');const href=e=>{try{return new URL(e.getAttribute('href')||'',location.href).pathname.toLowerCase()}catch{return ''}};const credentialSurface=fields.some(v=>/password|senha|username|login|c[oó]digo/.test(v));const accessRoute=/^\\/(?:accounts\\/(?:login|signup|password)|challenge|checkpoint|two_factor|login|oidc)/.test(path);const signedInShell=controls.some(e=>/^\\/direct(?:\\/inbox)?\\/?$/.test(href(e))||/^\\/accounts\\/edit\\/?$/.test(href(e))||/mensagens|messages|direct/.test(label(e)));const authenticated=!credentialSurface&&!accessRoute&&signedInShell;return {url,authenticated,hasMessages:controls.some(e=>/mensagens|messages|direct/i.test(label(e))),hasNotifications:controls.some(e=>/notifica|notifications|activity/i.test(label(e))),text};})()"""
    value = evaluate(expression)
    if not isinstance(value, dict):
        raise InternalBrowserError("Leitura do navegador interno inválida")
    # O texto nunca é retornado pelo endpoint de estado; o ciclo do agente usa
    # este dado internamente. O painel vê somente metadados agregados.
    return {key: value.get(key) for key in ("url", "authenticated", "hasMessages", "hasNotifications")}


def screenshot() -> dict[str, Any]:
    def run(page: DevTools):
        page.call("Page.enable")
        data = str(page.call("Page.captureScreenshot", {"format": "png"}).get("data") or "")
        try:
            image = base64.b64decode(data)
            if image[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError("PNG inválido")
            width, height = struct.unpack(">II", image[16:24])
        except (ValueError, struct.error):
            width, height = 1280, 900
        return {"png": data, "width": int(width), "height": int(height)}
    return _with_page(run)


def action(payload: dict[str, Any]) -> dict[str, Any]:
    """Executa uma interação explícita na sessão interna persistente.

    O painel remoto só envia coordenadas, texto digitado ou uma tecla. Não há
    execução arbitrária de JavaScript vinda do operador.
    """
    if not isinstance(payload, dict):
        raise ValueError("Interação inválida")
    kind = str(payload.get("kind") or "").strip().lower()
    if kind == "navigate":
        target = urllib.parse.urlparse(str(payload.get("url") or ""))
        if target.scheme != "https" or target.hostname not in _PRIMARY_HOSTS:
            raise ValueError("Destino interno não autorizado")

    def run(page: DevTools):
        if kind == "click":
            x, y = float(payload.get("x", -1)), float(payload.get("y", -1))
            if not (0 <= x <= 1280 and 0 <= y <= 900):
                raise ValueError("Coordenada fora da janela interna")
            page.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            page.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        elif kind == "type":
            text = str(payload.get("text") or "")
            if not text or len(text) > 512:
                raise ValueError("Texto de entrada inválido")
            # A digitação do agente passa pelo teclado virtual do navegador.
            # Não usa área de transferência nem injeta o texto no DOM: cada
            # caractere é entregue ao campo que o operador/agente selecionou.
            # A pequena variação reproduz o ritmo já validado no desktop.
            import random
            for character in text:
                page.call("Input.dispatchKeyEvent", {"type": "char", "text": character})
                time.sleep((18 + random.randint(0, 42)) / 1000)
        elif kind == "key":
            key = str(payload.get("key") or "")
            key_codes = {
                "Enter": 13,
                "Tab": 9,
                "Escape": 27,
                "Backspace": 8,
                "Delete": 46,
                "ArrowLeft": 37,
                "ArrowUp": 38,
                "ArrowRight": 39,
                "ArrowDown": 40,
            }
            if key not in key_codes:
                raise ValueError("Tecla interna inválida")
            code = key_codes[key]
            page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": key, "windowsVirtualKeyCode": code})
            page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": key, "windowsVirtualKeyCode": code})
        elif kind == "reload":
            page.call("Page.reload", {"ignoreCache": False})
        elif kind == "navigate":
            page.call("Page.navigate", {"url": target.geturl()})
        else:
            raise ValueError("Ação interna inválida")
        return {"ok": True}

    return _with_page(run)
