"""Ciclo comercial autônomo sobre a sessão interna persistente da VPS.

O módulo reutiliza o mesmo núcleo de memória/roteiro do desktop. Ele lê a
interface exibida, importa somente metadados da conversa necessários ao CRM,
digita por eventos do teclado virtual e só confirma uma resposta quando ela
aparece na área da conversa.
"""
from __future__ import annotations

import hashlib
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from core.config import load_config
from core.desktop_rpc import execute
from core.memory import Memory
from scripts.vps import internal_browser as browser


INBOX_URL = "https://www.instagram.com/direct/inbox/"
HOME_URL = "https://www.instagram.com/"
WEEKLY_SWEEP = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _wait(seconds: float) -> None:
    time.sleep(max(0.0, seconds))


def _page(expression: str) -> Any:
    return browser.evaluate(expression)


def _login_or_identity_step(url: str) -> bool:
    """Impede qualquer navegação enquanto a sessão ainda é autenticada.

    A tela pode passar por páginas intermediárias que não exibem um campo de
    senha por alguns segundos. A ausência de um input nunca é evidência
    suficiente para o agente assumir o controle da navegação.
    """
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or parsed.hostname not in {"instagram.com", "www.instagram.com"}:
        return True
    path = parsed.path.casefold()
    return any(marker in path for marker in (
        "/accounts/login", "/accounts/signup", "/accounts/password",
        "/challenge", "/checkpoint", "/two_factor", "/login", "/oidc",
    ))


def _thread_snapshot() -> dict[str, Any]:
    """Lê a conversa visível sem retornar texto para o painel remoto."""
    value = _page(r'''(()=>{
      const path=location.pathname.split('/').filter(Boolean);
      const threadId=path.length===3&&path[0]==='direct'&&path[1]==='t'?path[2]:'';
      const normalize=v=>String(v||'').replace(/\s+/g,' ').trim();
      const profile=[...document.querySelectorAll('a[aria-label],a[href]')].map(a=>{
        const label=a.getAttribute('aria-label')||'';
        const parts=new URL(a.href,location.href).pathname.split('/').filter(Boolean);
        const match=label.match(/(?:abrir a página de perfil de |open the profile page of )([^,]+)$/i);
        return match?match[1]:(parts.length===1&&/^[a-z0-9._]{1,30}$/i.test(parts[0])?parts[0]:'');
      }).find(Boolean)||'';
      const width=innerWidth||1280, seen=new Map();
      const nodes=[...document.querySelectorAll('[role="message"],[role="article"],[role="row"],[role="listitem"]')];
      const messages=[];
      for(const node of nodes){
        const text=normalize(node.innerText);
        if(!text||text.length>3500)continue;
        const rect=node.getBoundingClientRect();
        if(!rect.width||!rect.height)continue;
        const direction=rect.left+rect.width/2>width*.52?'outgoing':'incoming';
        const signature=direction+'\0'+text, ordinal=(seen.get(signature)||0)+1;
        seen.set(signature,ordinal);
        messages.push({text,direction,ordinal});
      }
      return {url:location.href,thread_id:threadId,username:String(profile).replace(/^@/,'').toLowerCase(),messages:messages.slice(-40)};
    })()''')
    if not isinstance(value, dict):
        return {"url": "", "thread_id": "", "username": "", "messages": []}
    thread = str(value.get("thread_id") or "")
    messages: list[dict[str, str]] = []
    for item in value.get("messages") or []:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split())[:3500]
        direction = str(item.get("direction") or "")
        if not thread or not text or direction not in {"incoming", "outgoing"}:
            continue
        ordinal = int(item.get("ordinal") or 1)
        external_id = hashlib.sha256(f"{thread}\0{direction}\0{text}\0{ordinal}".encode()).hexdigest()
        messages.append({"id": external_id, "text": text, "direction": direction})
    return {"url": str(value.get("url") or ""), "thread_id": thread, "username": str(value.get("username") or ""), "messages": messages[-40:]}


def _inbox_targets() -> list[dict[str, str]]:
    value = _page(r'''(()=>{
      const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
      const norm=v=>String(v||'').replace(/\s+/g,' ').trim();
      const time=/(?:agora|now|ontem|yesterday|há\s+(?:\d+|um|uma)\s+(?:minuto|minutos|hora|horas|dia|dias)|\b\d+\s*(?:s|min|m|h|d|w))\s*$/i;
      const ignored=/^(?:avançar|voltar|nova mensagem|more options|pesquisar|primary|general|pedidos)$/i;
      const output=[], seen=new Set();
      for(const node of [...document.querySelectorAll('a[href*="/direct/t/"],button,[role="button"]')]){
        if(!visible(node))continue;
        const label=norm([node.getAttribute('aria-label'),node.innerText].filter(Boolean).join(' '));
        const link=node.matches('a[href]')?node:(node.querySelector('a[href*="/direct/t/"]')||null);
        const href=link?link.href:'';
        if(!href&&!ignored.test(label)&&!(label.length>8&&time.test(label)))continue;
        if(!href&&ignored.test(label))continue;
        const key=href||label;
        if(key&& !seen.has(key)){seen.add(key);output.push({href,label:label.slice(0,360)});}
      }
      return output.slice(0,70);
    })()''')
    return [
        {"href": str(item.get("href") or ""), "label": str(item.get("label") or "")}
        for item in (value if isinstance(value, list) else []) if isinstance(item, dict)
    ]


def _open_target(target: dict[str, str]) -> bool:
    href = target.get("href") or ""
    if href:
        browser.action({"kind": "navigate", "url": href})
    else:
        label = repr(str(target.get("label") or ""))
        clicked = _page(f'''(()=>{{
          const expected={label}; const norm=v=>String(v||'').replace(/\\s+/g,' ').trim();
          const node=[...document.querySelectorAll('button,[role="button"]')].find(e=>norm([e.getAttribute('aria-label'),e.innerText].filter(Boolean).join(' '))===expected);
          if(!node)return false;node.click();return true;
        }})()''')
        if not clicked:
            return False
    for _ in range(16):
        _wait(.45)
        path = urlparse(str(browser.status().get("url") or "")).path.strip("/").split("/")
        # status intentionally does not include url; evaluate below remains
        # local to the service and cannot leak to the panel.
        current = _page("location.href")
        path = urlparse(str(current or "")).path.strip("/").split("/")
        if len(path) == 3 and path[:2] == ["direct", "t"]:
            return True
    return False


def _composer_center() -> dict[str, float] | None:
    value = _page(r'''(()=>{
      const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
      const nodes=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
      const el=nodes.find(e=>/mensagem|message|responder|reply/i.test((e.getAttribute('placeholder')||'')+' '+(e.getAttribute('aria-label')||'')))
        ||nodes.find(e=>e.matches('[contenteditable="true"],[role="textbox"]'))
        ||nodes.find(e=>e.tagName==='TEXTAREA'&&!/pesquis|search/i.test(e.getAttribute('placeholder')||''));
      if(!el)return null;const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};
    })()''')
    if not isinstance(value, dict):
        return None
    try:
        return {"x": float(value["x"]), "y": float(value["y"])}
    except (KeyError, TypeError, ValueError):
        return None


def _message_count(text: str) -> int:
    value = _page(f'''(()=>{{const target={text!r};return [...document.querySelectorAll('[role="row"],[role="listitem"],[role="article"],[role="message"]')].filter(e=>(e.innerText||'').replace(/\\s+/g,' ').trim()===target).length}})()''')
    return int(value or 0) if isinstance(value, (int, float)) else 0


def _send_bubble(text: str, expected_url: str) -> dict[str, Any]:
    point = _composer_center()
    if not point:
        raise browser.InternalBrowserError("Campo de mensagem não encontrado na conversa aberta")
    before = _message_count(text)
    browser.action({"kind": "click", **point})
    _wait(.15 + random.random() * .25)
    browser.action({"kind": "type", "text": text})
    entered = _page("(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if str(entered or "").strip() != text:
        raise browser.InternalBrowserError("Texto não foi inserido no campo da conversa")
    if str(_page("location.href") or "") != expected_url:
        raise browser.InternalBrowserError("Conversa mudou antes do envio")
    browser.action({"kind": "key", "key": "Enter"})
    for _ in range(12):
        _wait(.5)
        if str(_page("location.href") or "") != expected_url:
            raise browser.InternalBrowserError("Conversa mudou antes da confirmação")
        if _message_count(text) > before:
            return {"sent": True, "method": "mouse-virtual-keyboard-enter"}
    after = _thread_snapshot().get("messages") or []
    if after and after[-1].get("direction") == "outgoing" and after[-1].get("text") == text:
        return {"sent": True, "method": "virtual-keyboard-visible-bubble"}
    raise browser.InternalBrowserError("Mensagem não apareceu na conversa para confirmação")


def _process_thread(source: str) -> dict[str, Any]:
    snap = _thread_snapshot()
    if not snap["thread_id"] or not snap["username"] or not snap["messages"]:
        return {"processed": False, "reason": "thread-metadata-unavailable"}
    execute("browserImportThread", snap)
    last = snap["messages"][-1]
    if last["direction"] != "incoming":
        return {"processed": True, "replied": False, "reason": "no-pending-incoming"}
    cycle = execute("browserScreenCycle", {
        "url": snap["url"], "thread_id": snap["thread_id"], "username": snap["username"],
        "message_id": last["id"], "message": last["text"], "direction": "incoming", "messages": snap["messages"],
    })
    if not cycle.get("new_message") or not cycle.get("text"):
        return {"processed": True, "replied": False, "reason": "already-handled-or-no-draft"}
    _wait(2.4 + random.random() * 8.6)
    if not execute("agentStatus", {}).get("active"):
        return {"processed": True, "replied": False, "reason": "agent-paused"}
    if str(_page("location.href") or "") != snap["url"]:
        return {"processed": True, "replied": False, "reason": "conversation-changed"}
    sent = []
    for index, bubble in enumerate(str(cycle["text"]).split("\n[[AGENT_BUBBLE]]\n")):
        bubble = bubble.strip()
        if not bubble:
            continue
        sent.append(_send_bubble(bubble, snap["url"]))
        if index + 1 < len(str(cycle["text"]).split("\n[[AGENT_BUBBLE]]\n")):
            _wait(.7 + random.random() * 1.9)
    execute("browserScreenConfirm", {"message_key": cycle["message_key"], "lead_id": cycle["lead_id"], "text": cycle["text"], "thread_id": snap["thread_id"]})
    return {"processed": True, "replied": True, "source": source, "thread_id": snap["thread_id"], "sent": len(sent)}


def _sweep_due() -> bool:
    config = load_config()
    with Memory(config.db_path) as memory:
        raw = memory.get_setting("sales.agent.vps_browser.last_sweep", "")
    try:
        return _now() - datetime.fromisoformat(raw.replace("Z", "+00:00")) >= WEEKLY_SWEEP
    except ValueError:
        return True


def _mark_sweep() -> None:
    config = load_config()
    with Memory(config.db_path) as memory:
        memory.set_setting("sales.agent.vps_browser.last_sweep", _now().isoformat())


def _notification_candidates() -> list[str]:
    """Lê somente perfis associados explicitamente a novo seguidor."""
    browser.action({"kind": "navigate", "url": "https://www.instagram.com/notifications/"})
    _wait(2.2)
    value = _page(r'''(()=>{
      const reserved=new Set(['accounts','direct','explore','reels','stories','about','developer','legal','privacy','web']);
      const follower=/(?:começou|passou|acabou)(?:\s+de)? a seguir(?: você)?|(?:segue|seguiu|está seguindo)(?: você)?|started following you|follows you/i;
      const output=[];
      for(const marker of [...document.querySelectorAll('span,div,p')]){
        const text=String(marker.innerText||'').replace(/\s+/g,' ').trim();
        if(!text||text.length>360||!follower.test(text))continue;
        let row=marker;
        for(let depth=0;row&&depth<9;depth++,row=row.parentElement){
          const match=[...row.querySelectorAll('a[href]')].map(anchor=>new URL(anchor.href,location.href).pathname.split('/').filter(Boolean))
            .find(parts=>parts.length===1&&/^[a-z0-9._]{1,30}$/i.test(parts[0])&&!reserved.has(parts[0].toLowerCase()));
          if(match){output.push(match[0].toLowerCase());break;}
        }
      }
      return [...new Set(output)].slice(0,20);
    })()''')
    usernames = [str(item).lower() for item in (value if isinstance(value, list) else [])]
    return list(dict.fromkeys(item for item in usernames if item and len(item) <= 30))


def _capture_notification_actions() -> dict[str, int]:
    candidates = _notification_candidates()
    queued = 0
    for username in candidates:
        result = execute("browserNotificationCandidate", {"username": username, "kind": "new_follower"})
        if result.get("queued"):
            queued += 1
    browser.action({"kind": "navigate", "url": HOME_URL})
    _wait(1.0)
    return {"notification_candidates": len(candidates), "notification_queued": queued}


def sweep(source: str = "scheduled") -> dict[str, Any]:
    browser.action({"kind": "navigate", "url": INBOX_URL})
    _wait(1.5)
    targets = _inbox_targets()
    result = {"source": source, "threads": len(targets), "opened": 0, "imported": 0, "replied": 0, "skipped": 0}
    for target in targets:
        try:
            if not _open_target(target):
                result["skipped"] += 1
                continue
            result["opened"] += 1
            _wait(.7)
            processed = _process_thread(source)
            if processed.get("processed"):
                result["imported"] += 1
            if processed.get("replied"):
                result["replied"] += 1
        except Exception:
            result["skipped"] += 1
        finally:
            browser.action({"kind": "navigate", "url": INBOX_URL})
            _wait(.65)
    execute("classifyImportedHistory", {})
    _mark_sweep()
    browser.action({"kind": "navigate", "url": HOME_URL})
    return result


def cycle() -> dict[str, Any]:
    state = execute("agentStatus", {})
    if not state.get("active"):
        return {"active": False, "browser": "paused"}
    status = browser.status()
    if not status.get("running") or not status.get("ready"):
        return {"active": True, "browser": "offline"}
    snap = browser.snapshot()
    # A URL é verificada antes da heurística de DOM. Durante login, páginas
    # de identidade podem não ter campos de credencial durante uma transição;
    # nessa situação o agente deve ficar rigorosamente passivo.
    if _login_or_identity_step(str(snap.get("url") or "")) or not snap.get("authenticated"):
        return {"active": True, "browser": "waiting-login"}
    url = str(snap.get("url") or "")
    if "/direct/t/" in url:
        return {"active": True, "browser": "thread", **_process_thread("open-thread")}
    indicators = browser.metadata()
    aggregate = {
        "message_pending": bool(indicators.get("message_pending")),
        "notification_pending": bool(indicators.get("notification_pending")),
        "message_controls": int(indicators.get("message_controls") or 0),
        "notification_controls": int(indicators.get("notification_controls") or 0),
    }
    if aggregate["message_pending"]:
        browser.action({"kind": "navigate", "url": INBOX_URL})
        _wait(1.4)
        targets = _inbox_targets()
        if targets and _open_target(targets[0]):
            return {"active": True, "browser": "message", **aggregate, **_process_thread("message-indicator")}
    notification_result = {}
    if aggregate["notification_pending"]:
        notification_result = _capture_notification_actions()
    if _sweep_due():
        return {"active": True, "browser": "sweep", **aggregate, **notification_result, **sweep("weekly")}
    return {"active": True, "browser": "ready", **aggregate, **notification_result}
