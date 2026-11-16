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


def import_session_cookies(raw_cookies: Any) -> dict[str, int]:
    """Importa uma sessão do navegador do operador sem registrar valores."""
    if not isinstance(raw_cookies, list) or not raw_cookies:
        raise ValueError("Pacote de sessão inválido")
    allowed_domains = ("instagram.com", "facebook.com")
    same_site = {"no_restriction": "None", "unspecified": None, "lax": "Lax", "strict": "Strict", "none": "None"}
    imported: list[dict[str, Any]] = []
    now = time.time()
    for raw in raw_cookies:
        if not isinstance(raw, dict):
            continue
        name, value = str(raw.get("name") or ""), str(raw.get("value") or "")
        domain = str(raw.get("domain") or "").strip().lower()
        clean_domain = domain.lstrip(".")
        if not name or not value or len(name) > 180 or len(value) > 8192:
            continue
        if not any(clean_domain == item or clean_domain.endswith("." + item) for item in allowed_domains):
            continue
        cookie: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": str(raw.get("path") or "/")[:512],
            "secure": bool(raw.get("secure", True)),
            "httpOnly": bool(raw.get("httpOnly", False)),
        }
        mode = same_site.get(str(raw.get("sameSite") or "").lower())
        if mode:
            cookie["sameSite"] = mode
        expires = raw.get("expirationDate")
        if isinstance(expires, (int, float)) and expires > now:
            cookie["expires"] = float(expires)
        imported.append(cookie)
    if not imported:
        raise ValueError("Nenhum dado de sessão autorizado para importar")

    def run(page: DevTools):
        page.call("Network.enable")
        page.call("Network.setCookies", {"cookies": imported})
        return {"imported": len(imported)}

    return _with_page(run)


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
    return any(marker in path for marker in (
        "/login", "/recover", "/identify", "/checkpoint",
        "/two_step_verification", "/two_factor/", "/confirmemail",
    ))


def _is_instagram_login_window(item: dict[str, Any]) -> bool:
    parsed = urllib.parse.urlparse(str(item.get("url") or ""))
    if parsed.hostname not in _PRIMARY_HOSTS:
        return False
    path = parsed.path.casefold()
    return path.startswith((
        "/accounts/login", "/accounts/signup", "/accounts/emailsignup",
        "/accounts/password", "/auth_platform/", "/challenge",
        "/checkpoint", "/two_factor", "/login",
    ))


def _target() -> dict[str, Any]:
    pages = _http("/json/list")
    if not isinstance(pages, list):
        raise InternalBrowserError("Lista de páginas inválida")
    windows = [item for item in pages if isinstance(item, dict) and item.get("type") == "page" and _is_access_window(item)]
    # Prioriza a janela de recuperação aberta pelo operador. A página
    # principal permanece disponível e volta a ser selecionada quando a
    # recuperação termina ou é fechada.
    # Fluxos de confirmação podem abrir várias janelas auxiliares. A mais
    # recente é a etapa que o operador acabou de acionar e deve ser exibida
    # pelo painel, em vez da página inicial que ficou atrás dela.
    page = next((item for item in reversed(windows) if _is_recovery_window(item)), None)
    if page is None:
        primary = [item for item in windows if urllib.parse.urlparse(str(item.get("url") or "")).hostname in _PRIMARY_HOSTS]
        # Nunca deixa uma aba antiga de login encobrir a aba principal que já
        # foi aberta pelo operador. A página normal tem prioridade e a aba de
        # login só é usada quando ela é a única janela disponível.
        page = next((item for item in reversed(primary) if not _is_instagram_login_window(item)), None)
        if page is None:
            page = next((item for item in reversed(primary)), None)
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


def metadata() -> dict[str, Any]:
    """Retorna somente indicadores agregados da interface autenticada."""
    expression = r'''(()=>{
      const norm=value=>String(value||'').replace(/\s+/g,' ').trim();
      const isRed=element=>{
        const style=getComputedStyle(element);
        const colors=[style.backgroundColor,style.color,style.borderColor,style.fill,style.stroke].join(' ');
        return /rgb\((?:2[0-5]\d|1[89]\d),\s*(?:[0-9]|[1-9]\d|1[0-5]\d),\s*(?:[0-9]|[1-9]\d|1[0-5]\d)\)/.test(colors);
      };
      const controls=[...document.querySelectorAll('[aria-label]')].filter(element=>/^(notifications|notificações|messages|mensagens)$/i.test(norm(element.getAttribute('aria-label'))));
      const inspect=(pattern)=>{
        const matches=controls.filter(element=>pattern.test(norm(element.getAttribute('aria-label'))));
        let pending=false;
        for(const element of matches){
          let scope=element;
          for(let depth=0;depth<6&&scope;depth++,scope=scope.parentElement){
            const nodes=[scope,...scope.querySelectorAll('*')];
            if(nodes.some(node=>{const rect=node.getBoundingClientRect();return rect.width>0&&rect.height>0&&rect.width<=80&&rect.height<=80&&isRed(node)}))pending=true;
            if(nodes.some(node=>/^\d{1,3}$/.test(norm(node.textContent))))pending=true;
            if(scope.matches('a,button,[role="link"],[role="button"]'))break;
          }
        }
        return {controls:matches.length,pending};
      };
      const messages=inspect(/^(messages|mensagens)$/i);
      const notifications=inspect(/^(notifications|notificações)$/i);
      return {path:location.pathname,message_controls:messages.controls,notification_controls:notifications.controls,message_pending:messages.pending,notification_pending:notifications.pending};
    })()'''
    value = evaluate(expression)
    if not isinstance(value, dict):
        raise InternalBrowserError("Metadados do navegador interno inválidos")
    return {
        "path": str(value.get("path") or "")[:240],
        "message_controls": max(0, min(20, int(value.get("message_controls") or 0))),
        "notification_controls": max(0, min(20, int(value.get("notification_controls") or 0))),
        "message_pending": bool(value.get("message_pending")),
        "notification_pending": bool(value.get("notification_pending")),
    }


def frontend_events(clear: bool = True) -> dict[str, Any]:
    """Instala e consome sinais estruturais emitidos pelo front autenticado.

    O observador vive no contexto da página e não copia textos, nomes ou
    conteúdo de conversas. Ele registra apenas transições de estado visual.
    """
    clear_js = "state.events.splice(0,state.events.length)" if clear else "state.events.slice()"
    expression = rf'''(()=>{{
      const KEY='__salesAgentFrontEventsV1';
      const norm=value=>String(value||'').replace(/\s+/g,' ').trim();
      const visible=e=>{{const r=e.getBoundingClientRect();return r.width>0&&r.height>0}};
      const rgb=value=>{{const m=String(value||'').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);return m?[+m[1],+m[2],+m[3]]:null}};
      const isRed=e=>{{
        const s=getComputedStyle(e), values=[s.backgroundColor,s.color,s.borderColor,s.fill,s.stroke];
        return values.some(value=>{{const c=rgb(value);return c&&c[0]>=180&&c[0]>c[1]*1.35&&c[0]>c[2]*1.2}});
      }};
      const isBlue=e=>{{
        const s=getComputedStyle(e), values=[s.backgroundColor,s.color,s.borderColor,s.fill,s.stroke];
        return values.some(value=>{{const c=rgb(value);return c&&c[2]>=140&&c[2]-c[0]>=35&&c[2]-c[1]>=10}});
      }};
      const inspectControl=pattern=>{{
        const controls=[...document.querySelectorAll('[aria-label]')].filter(e=>pattern.test(norm(e.getAttribute('aria-label'))));
        let pending=false;
        for(const control of controls){{
          let scope=control;
          for(let depth=0;depth<6&&scope;depth++,scope=scope.parentElement){{
            const nodes=[scope,...scope.querySelectorAll('*')].filter(visible);
            if(nodes.some(node=>{{const r=node.getBoundingClientRect();return r.width<=80&&r.height<=80&&isRed(node)}}))pending=true;
            if(nodes.some(node=>/^\d{{1,3}}$/.test(norm(node.textContent))))pending=true;
            if(scope.matches('a,button,[role="link"],[role="button"]'))break;
          }}
        }}
        return {{controls:controls.length,pending}};
      }};
      const unreadRows=()=>{{
        const candidates=[...document.querySelectorAll('a[href*="/direct/t/"],button,[role="button"]')].filter(visible);
        const seen=new Set(); let count=0, confirmed=0;
        for(const node of candidates){{
          let scope=node,parent=node.parentElement;
          for(let depth=0;depth<7&&parent;depth++,parent=parent.parentElement){{
            const r=parent.getBoundingClientRect();
            if(r.height>170)break;
            if(r.height>=42&&r.width>=scope.getBoundingClientRect().width)scope=parent;
          }}
          const link=node.matches('a[href*="/direct/t/"]')?node:scope.querySelector('a[href*="/direct/t/"]');
          const key=link?link.href:norm(scope.getAttribute('aria-label'));
          if(!key||seen.has(key))continue;
          seen.add(key);
          const elements=[scope,...scope.querySelectorAll('*')].filter(visible);
          const bold=elements.some(e=>parseInt(getComputedStyle(e).fontWeight||'0',10)>=600&&norm(e.textContent).length>1);
          const scopeRect=scope.getBoundingClientRect();
          const blue=elements.some(e=>{{
            const r=e.getBoundingClientRect(),label=norm([e.getAttribute('aria-label'),e.getAttribute('title')].join(' '));
            const rightDot=r.width>=3&&r.height>=3&&r.width<=14&&r.height<=14&&Math.abs(r.width-r.height)<=3&&r.left>=scopeRect.right-48;
            const tag=e.tagName.toLowerCase(),background=rgb(getComputedStyle(e).backgroundColor);
            const emptyBlueDot=(tag==='div'||tag==='span')&&!norm(e.textContent)&&background&&background[2]>=140&&background[2]-background[0]>=35&&background[2]-background[1]>=10;
            return /^(?:unread|não lida|nova mensagem)$/i.test(label)||(rightDot&&emptyBlueDot);
          }});
          if(blue){{count++;if(bold)confirmed++;}}
        }}
        return {{count,confirmed}};
      }};
      const read=()=>{{
        const messages=inspectControl(/^(messages|mensagens)$/i);
        const notifications=inspectControl(/^(notifications|notificações)$/i);
        const unread=location.pathname.startsWith('/direct')?unreadRows():{{count:0,confirmed:0}};
        return {{path:location.pathname,message_pending:messages.pending,notification_pending:notifications.pending,unread_rows:unread.count,unread_confirmed:unread.confirmed}};
      }};
      let state=window[KEY];
      if(!state||!state.observer){{
        state={{sequence:0,events:[],signature:'',timer:0,observer:null}};
        const sample=()=>{{
          state.timer=0;
          const next=read(),signature=JSON.stringify(next);
          if(signature===state.signature)return;
          state.signature=signature;state.sequence++;
          state.events.push({{sequence:state.sequence,at:Date.now(),...next}});
          if(state.events.length>40)state.events.splice(0,state.events.length-40);
        }};
        const schedule=()=>{{if(state.timer)return;state.timer=setTimeout(sample,350)}};
        state.observer=new MutationObserver(schedule);
        state.observer.observe(document.documentElement,{{subtree:true,childList:true,attributes:true,attributeFilter:['class','style','aria-label','title']}});
        addEventListener('popstate',schedule,{{passive:true}});
        addEventListener('hashchange',schedule,{{passive:true}});
        document.addEventListener('visibilitychange',schedule,{{passive:true}});
        window[KEY]=state;sample();
      }}
      const events={clear_js};
      const last=events.length?events[events.length-1]:null;
      return {{installed:true,sequence:state.sequence,event_count:events.length,last,events}};
    }})()'''
    value = evaluate(expression)
    if not isinstance(value, dict):
        raise InternalBrowserError("Fila de eventos do navegador interno inválida")
    events = []
    for item in value.get("events") or []:
        if not isinstance(item, dict):
            continue
        events.append({
            "sequence": max(0, int(item.get("sequence") or 0)),
            "message_pending": bool(item.get("message_pending")),
            "notification_pending": bool(item.get("notification_pending")),
            "unread_rows": max(0, min(100, int(item.get("unread_rows") or 0))),
            "unread_confirmed": max(0, min(100, int(item.get("unread_confirmed") or 0))),
            "path": str(item.get("path") or "")[:240],
        })
    return {
        "installed": bool(value.get("installed")),
        "sequence": max(0, int(value.get("sequence") or 0)),
        "event_count": len(events),
        "events": events,
        "last": events[-1] if events else None,
    }


def frontend_event_pending() -> bool:
    """Consulta barata usada para acordar o worker antes do próximo ciclo."""
    value = evaluate("(()=>{const s=window.__salesAgentFrontEventsV1;return !s||!s.observer||s.events.length>0})()")
    return bool(value)


def stalled_page_watchdog() -> dict[str, Any]:
    """Arma recuperação suave quando o front fica preso no splash.

    O temporizador roda dentro da própria página. Rotas de login, desafios e
    qualquer tela com campos de credencial nunca são recarregadas por ele.
    """
    value = evaluate(r'''(()=>{
      const KEY='__salesAgentStallWatchdogV1',STORE='salesAgentStallRecoveriesV1';
      const label=e=>[e.innerText,e.getAttribute('aria-label'),e.getAttribute('title'),e.getAttribute('href')].filter(Boolean).join(' ');
      const health=()=>{
        const path=location.pathname.toLowerCase();
        const fields=[...document.querySelectorAll('input,textarea,[contenteditable="true"]')];
        const fieldText=fields.map(e=>[e.name,e.type,e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ').toLowerCase());
        const credential=fieldText.some(v=>/password|senha|username|login|c[oó]digo|security|seguran[cç]a/.test(v));
        const identity=/^\/(?:accounts\/|auth_platform\/|challenge|checkpoint|two_factor|login|oidc)/.test(path);
        const controls=[...document.querySelectorAll('a,button,[role="button"],[role="link"]')];
        const shell=controls.some(e=>/mensagens|messages|direct|notifica|notifications|página inicial|home/i.test(label(e)));
        const direct=path.startsWith('/direct');
        const bodyText=String(document.body?.innerText||'').replace(/\s+/g,' ').trim();
        const threadLinks=document.querySelectorAll('a[href*="/direct/t/"]').length;
        const conversationNodes=document.querySelectorAll('[role="message"],[role="article"],[role="listitem"],[role="row"]').length;
        const composer=fields.some(e=>/mensagem|message|responder|reply/i.test([e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ')));
        const inboxControls=fields.some(e=>/pesquis|search/i.test([e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ')))
          ||controls.some(e=>/^(primary|general|requests|principal|geral|solicita[cç][oõ]es)$/i.test(String(e.innerText||'').trim()));
        const emptyState=/no messages|nenhuma mensagem|send a message|enviar (?:uma )?mensagem/i.test(bodyText);
        const usable=threadLinks>0||conversationNodes>0||composer||inboxControls||emptyState;
        return {stalled:direct&&document.readyState==='complete'&&!credential&&!identity&&(!shell||!usable)};
      };
      const stalled=health().stalled;
      let state=window[KEY];
      if(!state)state=window[KEY]={timer:0,armedAt:0};
      if(!stalled){
        if(state.timer)clearTimeout(state.timer);
        state.timer=0;state.armedAt=0;
        return {stalled:false,armed:false,throttled:false};
      }
      let history=[];
      try{history=JSON.parse(sessionStorage.getItem(STORE)||'[]').filter(v=>Number(v)>Date.now()-300000)}catch{history=[]}
      const throttled=history.length>=2;
      if(!state.timer&&!throttled){
        state.armedAt=Date.now();
        state.timer=setTimeout(()=>{
          state.timer=0;
          if(health().stalled){
            history.push(Date.now());
            try{sessionStorage.setItem(STORE,JSON.stringify(history.slice(-2)))}catch{}
            location.reload();
          }
        },12000);
      }
      return {stalled:true,armed:Boolean(state.timer),throttled,armed_seconds:state.armedAt?Math.max(0,Math.floor((Date.now()-state.armedAt)/1000)):0};
    })()''')
    if not isinstance(value, dict):
        raise InternalBrowserError("Watchdog do navegador interno inválido")
    return {
        "stalled": bool(value.get("stalled")),
        "armed": bool(value.get("armed")),
        "throttled": bool(value.get("throttled")),
        "armed_seconds": max(0, min(300, int(value.get("armed_seconds") or 0))),
    }


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
                # O editor contenteditable da DM ignora eventos char e pares
                # keyDown/keyUp sintetizados. Input.insertText é a primitiva
                # nativa de edição do motor: dispara beforeinput/input no
                # campo focado, sem clipboard e sem modificar o DOM por script.
                page.call("Input.insertText", {"text": character})
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
        elif kind in {"back", "forward"}:
            history = page.call("Page.getNavigationHistory")
            entries = history.get("entries") if isinstance(history, dict) else []
            current = int(history.get("currentIndex", -1)) if isinstance(history, dict) else -1
            destination = current - 1 if kind == "back" else current + 1
            if not isinstance(entries, list) or not (0 <= destination < len(entries)):
                return {"ok": True, "moved": False}
            entry = entries[destination] if isinstance(entries[destination], dict) else {}
            entry_id = entry.get("id")
            if not isinstance(entry_id, int):
                return {"ok": True, "moved": False}
            page.call("Page.navigateToHistoryEntry", {"entryId": entry_id})
            return {"ok": True, "moved": True}
        elif kind == "reload":
            page.call("Page.reload", {"ignoreCache": False})
        elif kind == "navigate":
            page.call("Page.navigate", {"url": target.geturl()})
        else:
            raise ValueError("Ação interna inválida")
        return {"ok": True}

    return _with_page(run)
