"""Ciclo comercial autônomo sobre a sessão interna persistente da VPS.

O módulo reutiliza o mesmo núcleo de memória/roteiro do desktop. Ele lê a
interface exibida, importa somente metadados da conversa necessários ao CRM,
digita por eventos do teclado virtual e só confirma uma resposta quando ela
aparece na área da conversa.
"""
from __future__ import annotations

import hashlib
import random
import re
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
_RECENT_UNREAD_TARGETS: dict[str, float] = {}
_LAST_NOTIFICATION_SCAN = 0.0
NOTIFICATION_SCAN_COOLDOWN_SECONDS = 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _wait(seconds: float) -> None:
    time.sleep(max(0.0, seconds))


def _unread_target_key(target: dict[str, Any]) -> str:
    return str(target.get("key") or target.get("href") or target.get("label") or "")[:500]


def _actionable_unread(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = time.monotonic()
    expired = [key for key, until in _RECENT_UNREAD_TARGETS.items() if until <= now]
    for key in expired:
        _RECENT_UNREAD_TARGETS.pop(key, None)
    return [
        target for target in targets
        if target.get("unread") and _RECENT_UNREAD_TARGETS.get(_unread_target_key(target), 0) <= now
    ]


def _pending_message_fallback_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recupera DMs recentes quando o celular já removeu o marcador azul.

    O evento estrutural de mensagem nova continua sendo a condição de entrada.
    Abrimos no máximo seis linhas recentes, e o histórico da própria conversa
    decide se a última fala é nova antes de qualquer resposta.
    """
    now = time.monotonic()
    return [
        target for target in targets
        if (target.get("href") or (target.get("x") is not None and target.get("y") is not None))
        and _RECENT_UNREAD_TARGETS.get(_unread_target_key(target), 0) <= now
    ][:6]


def _notification_scan_due() -> bool:
    return time.monotonic() - _LAST_NOTIFICATION_SCAN >= NOTIFICATION_SCAN_COOLDOWN_SECONDS


def _mark_notification_scan() -> None:
    global _LAST_NOTIFICATION_SCAN
    _LAST_NOTIFICATION_SCAN = time.monotonic()


def _page(expression: str) -> Any:
    return browser.evaluate(expression)


def _click_surface(pathname: str, labels: tuple[str, ...], *, require_path: bool = True) -> bool:
    """Abre uma área pelo próprio DOM, preservando o documento SPA ativo."""
    clicked = _page(fr'''(()=>{{
      const expectedPath={pathname!r}.replace(/\/$/,'')||'/';
      const labels={list(labels)!r}.map(value=>String(value).toLowerCase());
      const visible=node=>{{const r=node.getBoundingClientRect();const s=getComputedStyle(node);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'}};
      const norm=value=>String(value||'').replace(/\s+/g,' ').trim().toLowerCase();
      const nodes=[...document.querySelectorAll('a[href],button,[role="button"],[role="link"]')].filter(visible);
      let node=nodes.find(item=>{{
        if(!item.href)return false;
        try{{const path=new URL(item.href,location.href).pathname.replace(/\/$/,'')||'/';return path===expectedPath}}catch{{return false}}
      }});
      if(!node)node=nodes.find(item=>{{
        const text=norm([item.getAttribute('aria-label'),item.getAttribute('title'),item.innerText].filter(Boolean).join(' '));
        return labels.some(label=>text===label||text.startsWith(label+' '));
      }});
      if(!node)return false;
      (node.closest('a[href],button,[role="button"],[role="link"]')||node).click();
      return true;
    }})()''')
    if not clicked:
        return False
    if not require_path:
        _wait(.8)
        return True
    expected = pathname.rstrip("/") or "/"
    for _ in range(24):
        _wait(.25)
        current = urlparse(str(_page("location.href") or "")).path.rstrip("/") or "/"
        if current == expected:
            return True
    return False


def _open_inbox() -> bool:
    current = urlparse(str(_page("location.href") or "")).path.rstrip("/") or "/"
    if current == "/direct/inbox":
        return True
    if _click_surface("/direct/inbox/", ("mensagens", "messages", "direct")):
        return True
    # Em alguns layouts a superfície de mensagens fica recolhida e não expõe
    # um alvo clicável. A navegação interna mantém a mesma sessão e evita que
    # um evento novo do celular fique sem leitura.
    browser.action({"kind": "navigate", "url": INBOX_URL})
    for _ in range(12):
        _wait(.35)
        path = urlparse(str(_page("location.href") or "")).path.rstrip("/")
        if path == "/direct/inbox":
            return True
    return False


def _open_notifications() -> bool:
    return _click_surface(
        "/notifications/",
        ("notificações", "notifications", "atividade", "activity"),
        require_path=False,
    )


def _open_home() -> bool:
    current = urlparse(str(_page("location.href") or "")).path.rstrip("/") or "/"
    if current == "/":
        return True
    return _click_surface("/", ("página inicial", "home"))


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
        "/auth_platform/", "/challenge", "/checkpoint", "/two_factor",
        "/login", "/oidc",
    ))


def _thread_snapshot() -> dict[str, Any]:
    """Lê a conversa visível sem retornar texto para o painel remoto."""
    value = _page(r'''(()=>{
      const path=location.pathname.split('/').filter(Boolean);
      const threadId=path.length===3&&path[0]==='direct'&&path[1]==='t'?path[2]:'';
      const normalize=v=>String(v||'').replace(/\s+/g,' ').trim();
      const anchors=[...document.querySelectorAll('a[aria-label],a[href]')];
      const labeledProfile=anchors.map(a=>{
        const label=a.getAttribute('aria-label')||'';
        const match=label.match(/(?:abrir a página de perfil de |open the profile page of )([^,]+)$/i);
        return match?match[1]:'';
      }).find(Boolean)||'';
      const reserved=new Set(['accounts','direct','explore','reels','stories','about','developer','legal','privacy','web']);
      const fallbackProfile=anchors.filter(a=>a.getBoundingClientRect().left>(innerWidth||1280)*.3).map(a=>{
        const parts=new URL(a.href,location.href).pathname.split('/').filter(Boolean);
        return parts.length===1&&/^[a-z0-9._]{1,30}$/i.test(parts[0])&&!reserved.has(parts[0].toLowerCase())?parts[0]:'';
      }).find(Boolean)||'';
      const profile=labeledProfile||fallbackProfile;
      const width=innerWidth||1280, seen=new Map();
      const nodes=[...document.querySelectorAll('[role="message"],[role="article"],[role="row"],[role="listitem"]')];
      const messages=[];
      for(const node of nodes){
        const text=normalize(node.innerText);
        if(!text||text.length>3500)continue;
        const rect=node.getBoundingClientRect();
        if(!rect.width||!rect.height)continue;
        const painted=[node,...node.querySelectorAll('div,span')].map(element=>getComputedStyle(element).backgroundColor)
          .map(color=>String(color||'').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i)).filter(Boolean)
          .map(match=>[Number(match[1]),Number(match[2]),Number(match[3])]);
        const coloredBubble=painted.some(rgb=>Math.max(...rgb)-Math.min(...rgb)>55&&Math.max(...rgb)>125);
        const direction=coloredBubble||(rect.left>width*.5&&rect.right>width*.84)?'outgoing':'incoming';
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


def _inbox_targets() -> list[dict[str, Any]]:
    value = _page(r'''(()=>{
      const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
      const norm=v=>String(v||'').replace(/\s+/g,' ').trim();
      const rgb=value=>{const m=String(value||'').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);return m?[+m[1],+m[2],+m[3]]:null};
      const isBlue=e=>{
        const s=getComputedStyle(e), colors=[s.backgroundColor,s.color,s.borderColor,s.fill,s.stroke];
        return colors.some(value=>{const c=rgb(value);return c&&c[2]>=140&&c[2]-c[0]>=35&&c[2]-c[1]>=10});
      };
      const time=/(?:agora|now|ontem|yesterday|há\s+(?:\d+|um|uma)\s+(?:minuto|minutos|hora|horas|dia|dias)|\b\d+\s*(?:s|min|m|h|d|w))\s*$/i;
      const ignored=/^(?:avançar|voltar|nova mensagem|more options|pesquisar|primary|general|pedidos)$/i;
      const output=[], seen=new Set();
      for(const node of [...document.querySelectorAll('a[href*="/direct/t/"],button,[role="button"]')]){
        if(!visible(node))continue;
        let scope=node, parent=node.parentElement;
        for(let depth=0;depth<7&&parent;depth++,parent=parent.parentElement){
          const r=parent.getBoundingClientRect();
          if(r.height>170)break;
          if(r.height>=42&&r.width>=scope.getBoundingClientRect().width)scope=parent;
        }
        const label=norm([scope.getAttribute('aria-label'),scope.innerText].filter(Boolean).join(' '));
        const link=node.matches('a[href*="/direct/t/"]')?node:(scope.querySelector('a[href*="/direct/t/"]')||null);
        const href=link?link.href:'';
        if(!href&&!ignored.test(label)&&!(label.length>8&&time.test(label)))continue;
        if(!href&&ignored.test(label))continue;
        const key=href||label;
        if(key&& !seen.has(key)){
          seen.add(key);
          const elements=[scope,...scope.querySelectorAll('*')].filter(visible);
          const bold=elements.some(e=>Number.parseInt(getComputedStyle(e).fontWeight,10)>=600&&norm(e.textContent).length>1);
          const scopeRect=scope.getBoundingClientRect();
           const blue=elements.some(e=>{
            const r=e.getBoundingClientRect(), accessibility=norm([e.getAttribute('aria-label'),e.getAttribute('title')].join(' '));
            const rightDot=r.width>=3&&r.height>=3&&r.width<=14&&r.height<=14&&Math.abs(r.width-r.height)<=3&&r.left>=scopeRect.right-48;
             const tag=e.tagName.toLowerCase(), background=rgb(getComputedStyle(e).backgroundColor);
             const emptyBlueDot=(tag==='div'||tag==='span')&&!norm(e.textContent)&&background&&background[2]>=140&&background[2]-background[0]>=35&&background[2]-background[1]>=10;
             return /^(?:unread|não lida|nova mensagem)$/i.test(accessibility)||(rightDot&&emptyBlueDot);
          });
          const reserved=new Set(['accounts','direct','explore','reels','stories','about','developer','legal','privacy','web']);
          const profile=[...scope.querySelectorAll('a[href]')].map(anchor=>new URL(anchor.href,location.href).pathname.split('/').filter(Boolean))
            .find(parts=>parts.length===1&&/^[a-z0-9._]{1,30}$/i.test(parts[0])&&!reserved.has(parts[0].toLowerCase()));
          const stableKey=href||(profile?profile[0].toLowerCase():label.replace(time,'').slice(0,160));
          const clickNode=node.closest('a[href*="/direct/t/"],button,[role="button"]')||node;
          const clickRect=clickNode.getBoundingClientRect();
          output.push({key:stableKey,href,label:label.slice(0,360),unread:Boolean(blue),bold:Boolean(bold),blue:Boolean(blue),x:clickRect.left+clickRect.width/2,y:clickRect.top+clickRect.height/2});
        }
      }
      return output.slice(0,70);
    })()''')
    targets = [
        {
            "href": str(item.get("href") or ""),
            "key": str(item.get("key") or "")[:500],
            "label": str(item.get("label") or ""),
            "unread": bool(item.get("unread")),
            "bold": bool(item.get("bold")),
            "blue": bool(item.get("blue")),
            "x": float(item.get("x")) if isinstance(item.get("x"), (int, float)) else None,
            "y": float(item.get("y")) if isinstance(item.get("y"), (int, float)) else None,
        }
        for item in (value if isinstance(value, list) else []) if isinstance(item, dict)
    ]
    # A bolinha azul é o marcador autoritativo de DM não lida. O peso da
    # tipografia fica registrado como confirmação visual, sem usar OCR.
    return sorted(targets, key=lambda item: (not item["unread"], not item["bold"]))


def _open_target(target: dict[str, Any]) -> bool:
    href = target.get("href") or ""
    target_path = urlparse(href).path if href else ""
    label = str(target.get("label") or "")
    clicked = _page(fr'''(()=>{{
      const expectedPath={target_path!r}; const expectedLabel={label!r};
      const visible=e=>{{const r=e.getBoundingClientRect();return r.width>0&&r.height>0}};
      const norm=v=>String(v||'').replace(/\s+/g,' ').trim();
      const nodes=[...document.querySelectorAll('a[href*="/direct/t/"],button,[role="button"],[role="link"]')].filter(visible);
      let node=expectedPath?nodes.find(e=>{{try{{return new URL(e.href||'',location.href).pathname===expectedPath}}catch{{return false}}}}):null;
      if(!node&&expectedLabel)node=nodes.find(e=>norm([e.getAttribute('aria-label'),e.innerText].filter(Boolean).join(' '))===expectedLabel);
      if(!node)return false;
      (node.closest('a[href],button,[role="button"],[role="link"]')||node).click();return true;
    }})()''')
    if clicked:
        for _ in range(16):
            _wait(.45)
            current = _page("location.href")
            path = urlparse(str(current or "")).path.strip("/").split("/")
            if len(path) == 3 and path[:2] == ["direct", "t"]:
                return True
    x, y = target.get("x"), target.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        browser.action({"kind": "click", "x": float(x), "y": float(y)})
        for _ in range(16):
            _wait(.45)
            current = _page("location.href")
            path = urlparse(str(current or "")).path.strip("/").split("/")
            if len(path) == 3 and path[:2] == ["direct", "t"]:
                return True
    # Linhas virtualizadas podem manter um nó visível, mas descartar o clique
    # sintético. A URL veio da própria linha; navegar internamente para ela
    # conserva a sessão e abre exatamente a conversa selecionada.
    if not href:
        return False
    browser.action({"kind": "navigate", "url": href})
    for _ in range(16):
        _wait(.45)
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
    value = _page(fr'''(()=>{{
      const canonical=v=>String(v||'').replace(/[\u{{1F000}}-\u{{1FAFF}}\u2600-\u27BF]/gu,'').replace(/\\s+/g,' ').trim();
      const target=canonical({text!r});
      const visible=e=>{{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'}};
      const nodes=[...document.querySelectorAll('[role="row"],[role="listitem"],[role="article"],[role="message"],[dir="auto"]')].filter(visible);
      return nodes.filter(e=>{{
        const own=canonical(e.innerText||e.textContent||'');
        if(own!==target)return false;
        const r=e.getBoundingClientRect();
        return r.left>450&&r.bottom<(innerHeight||900)-40;
      }}).length;
    }})()''')
    return int(value or 0) if isinstance(value, (int, float)) else 0


def _send_button_center() -> dict[str, float] | None:
    """Localiza o controle de envio ao lado do compositor da DM.

    O botão atual é exposto apenas como um ícone em algumas versões da tela.
    Por isso, além do rótulo acessível, usamos a relação geométrica com o
    compositor. O clique propriamente dito continua sendo um evento nativo de
    mouse, e não ``element.click()``, que a interface pode ignorar.
    """
    value = _page(r'''(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
      const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
      const fields=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
      const composer=fields.find(e=>/mensagem|message|responder|reply/i.test([e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ')))
        ||fields.find(e=>e.matches('[contenteditable="true"],[role="textbox"]')&&!/pesquis|search/i.test([e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ')));
      if(!composer)return null;
      const c=composer.getBoundingClientRect();
      const candidates=[...document.querySelectorAll('button,[role="button"]')].filter(visible).map(e=>{
        const r=e.getBoundingClientRect();
        const label=norm([e.getAttribute('aria-label'),e.getAttribute('title'),e.innerText].filter(Boolean).join(' '));
        const sameBand=r.bottom>=c.top-8&&r.top<=c.bottom+8;
        const onRight=r.left>=c.left+c.width*.68&&r.right<=Math.max(innerWidth,c.right+96);
        const named=/^(?:send|enviar)(?: message| mensagem)?$/.test(label);
        return {r,label,named,sameBand,onRight};
      }).filter(v=>v.sameBand&&(v.named||v.onRight));
      candidates.sort((a,b)=>Number(b.named)-Number(a.named)||b.r.right-a.r.right);
      const hit=candidates[0];
      return hit?{x:hit.r.left+hit.r.width/2,y:hit.r.top+hit.r.height/2,label:hit.label}:null;
    })()''')
    if not isinstance(value, dict):
        return None
    try:
        return {"x": float(value["x"]), "y": float(value["y"])}
    except (KeyError, TypeError, ValueError):
        return None


def _clear_composer() -> None:
    """Remove de forma nativa qualquer rascunho deixado por uma tentativa."""
    # Uma tentativa anterior pode deixar o compositor com o foco visual, mas
    # sem foco de teclado depois de uma transição da interface. Reconfirme o
    # foco pelo mouse antes de cada tentativa; nunca acrescente uma resposta
    # ao texto que ficou no campo.
    for attempt in range(3):
        point = _composer_center()
        if point:
            browser.action({"kind": "click", **point})
        browser.action({"kind": "key", "key": "SelectAll"})
        browser.action({"kind": "key", "key": "Backspace"})
        _wait(.18 + attempt * .12)
        remaining = _page("(()=>{const e=document.activeElement;return String(e?.value||e?.innerText||e?.textContent||'').trim()})()")
        if not str(remaining or "").strip():
            return
        # Em certas versões da caixa de DM, Ctrl+A é recebido mas a seleção
        # visual não é aplicada. Nesse caso, apague a extensão restante por
        # eventos Backspace individuais — ainda é somente teclado virtual e
        # garante que nenhuma resposta seja anexada ao rascunho anterior.
        for _ in range(min(len(str(remaining)), 512)):
            browser.action({"kind": "key", "key": "Backspace"})
        _wait(.20 + attempt * .1)
        remaining = _page("(()=>{const e=document.activeElement;return String(e?.value||e?.innerText||e?.textContent||'').trim()})()")
        if not str(remaining or "").strip():
            return
    raise browser.InternalBrowserError("Rascunho anterior não pôde ser limpo")


def _composer_safe_text(text: str) -> str:
    """Evita que `_` de URLs seja interpretado como itálico pelo editor.

    O editor Lexical transforma sublinhados de uma URL em elementos ``em`` e
    remove os caracteres do texto visível. ``%5F`` é equivalente em URLs,
    continua clicável e mantém os nomes dos parâmetros depois da decodificação.
    """
    return re.sub(
        r"https://[^\s]+",
        lambda match: match.group(0).replace("_", "%5F"),
        str(text or ""),
    )


def _send_bubble(text: str, expected_url: str) -> dict[str, Any]:
    composer_text = _composer_safe_text(text)
    point = _composer_center()
    if not point:
        raise browser.InternalBrowserError("Campo de mensagem não encontrado na conversa aberta")
    before = _message_count(composer_text)
    browser.action({"kind": "click", **point})
    _wait(.15 + random.random() * .25)
    existing = _page("(()=>{const e=document.activeElement;return String(e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if existing:
        _clear_composer()
    browser.action({"kind": "type", "text": composer_text})
    entered = _page("(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if str(entered or "").strip() != composer_text:
        raise browser.InternalBrowserError("Texto não foi inserido no campo da conversa")
    if str(_page("location.href") or "") != expected_url:
        raise browser.InternalBrowserError("Conversa mudou antes do envio")
    send_point = _send_button_center()
    if send_point:
        browser.action({"kind": "click", **send_point})
        # A interface pode aceitar o clique visual mas perder o primeiro
        # evento durante a reidratação. Se o próprio compositor ainda contém
        # exatamente o texto digitado, Enter é a segunda rota nativa de envio.
        _wait(.28)
        still_draft = _page("(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()})()")
        if str(still_draft or "").strip() == composer_text:
            browser.action({"kind": "key", "key": "Enter"})
    else:
        browser.action({"kind": "key", "key": "Enter"})
    for _ in range(12):
        _wait(.5)
        if str(_page("location.href") or "") != expected_url:
            raise browser.InternalBrowserError("Conversa mudou antes da confirmação")
        if _message_count(composer_text) > before:
            return {"sent": True, "method": "mouse-virtual-keyboard-send"}
    after = _thread_snapshot().get("messages") or []
    if after and after[-1].get("direction") == "outgoing" and after[-1].get("text") == composer_text:
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
        return {
            "processed": True,
            "replied": False,
            "reason": str(cycle.get("reason") or "already-handled-or-no-draft")[:80],
            "reaction": str(cycle.get("reaction") or "")[:20],
            "reaction_pending": bool(cycle.get("reaction_pending")),
        }
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
    if not _open_notifications():
        return []
    _wait(1.4)
    value = _page(r'''(()=>{
      const reserved=new Set(['accounts','direct','explore','reels','stories','about','developer','legal','privacy','web']);
      const follower=/(?:começou|passou|acabou)(?:\s+de)? a seguir(?: você|te)?|(?:segue|seguiu|está seguindo)(?: você|te)?|started following you|follows you/i;
      const followBack=/(?:seguir(?:\s+de)?\s+volta|follow\s+back|seguir você|follow you)/i;
      const output=[];
      for(const marker of [...document.querySelectorAll('span,div,p')]){
        const text=String(marker.innerText||'').replace(/\s+/g,' ').trim();
        const rowButtons=[...marker.querySelectorAll('button,[role="button"]')].map(button=>String(button.getAttribute('aria-label')||button.innerText||'')).join(' ');
        if(!text||text.length>360||(!follower.test(text)&&!followBack.test(rowButtons)))continue;
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
    _open_home()
    return {"notification_candidates": len(candidates), "notification_queued": queued}


def sweep(source: str = "scheduled") -> dict[str, Any]:
    if not _open_inbox():
        return {"source": source, "threads": 0, "opened": 0, "imported": 0, "replied": 0, "skipped": 1, "reason": "inbox-control-unavailable"}
    _wait(.8)
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
            _open_inbox()
            _wait(.4)
    execute("classifyImportedHistory", {})
    _mark_sweep()
    _open_home()
    return result


def cycle() -> dict[str, Any]:
    state = execute("agentStatus", {})
    if not state.get("active"):
        return {"active": False, "browser": "paused"}
    status = browser.status()
    if not status.get("running") or not status.get("ready"):
        return {"active": True, "browser": "offline"}
    snap = browser.snapshot()
    try:
        page_watchdog = browser.stalled_page_watchdog()
    except browser.InternalBrowserError:
        page_watchdog = {"stalled": False, "armed": False, "throttled": False}
    # A URL é verificada antes da heurística de DOM. Durante login, páginas
    # de identidade podem não ter campos de credencial durante uma transição;
    # nessa situação o agente deve ficar rigorosamente passivo.
    if page_watchdog.get("stalled"):
        return {"active": True, "browser": "recovering-page", "page_watchdog": page_watchdog}
    if _login_or_identity_step(str(snap.get("url") or "")) or not snap.get("authenticated"):
        return {"active": True, "browser": "waiting-login"}
    try:
        frontend = browser.frontend_events(clear=True)
    except browser.InternalBrowserError:
        frontend = {"event_count": 0, "events": [], "last": None}
    url = str(snap.get("url") or "")
    open_thread_result: dict[str, Any] | None = None
    if "/direct/t/" in url:
        open_thread_result = _process_thread("open-thread")
        # Uma conversa aberta não pode impedir a descoberta das demais DMs.
        # Só permanecemos nela quando houve uma ação real neste ciclo.
        if open_thread_result.get("replied") or open_thread_result.get("reaction_pending"):
            return {"active": True, "browser": "thread", **open_thread_result}
    indicators = browser.metadata()
    event_rows = [item for item in frontend.get("events") or [] if isinstance(item, dict)]
    last_event = frontend.get("last") if isinstance(frontend.get("last"), dict) else {}
    aggregate = {
        "message_pending": bool(indicators.get("message_pending") or last_event.get("message_pending") or last_event.get("unread_rows")),
        "notification_pending": bool(indicators.get("notification_pending") or last_event.get("notification_pending")),
        "message_controls": int(indicators.get("message_controls") or 0),
        "notification_controls": int(indicators.get("notification_controls") or 0),
        "frontend_events": len(event_rows),
        "frontend_unread_rows": int(last_event.get("unread_rows") or 0),
    }
    # A central de notificações tem prioridade quando os dois indicadores
    # vermelhos aparecem juntos. Antes, o retorno antecipado do ramo de DMs
    # impedia esta rotina de ser alcançada indefinidamente.
    if aggregate["notification_pending"] and _notification_scan_due():
        notification_result = _capture_notification_actions()
        _mark_notification_scan()
        return {"active": True, "browser": "notification", **aggregate, **notification_result}
    if aggregate["message_pending"]:
        if urlparse(url).path.rstrip("/") != "/direct/inbox":
            if not _open_inbox():
                return {"active": True, "browser": "inbox-control-unavailable", **aggregate}
            _wait(.7)
        targets = _inbox_targets()
        unread = [target for target in targets if target.get("unread")]
        actionable = _actionable_unread(targets)
        aggregate["inbox_unread"] = len(unread)
        aggregate["inbox_actionable_unread"] = len(actionable)
        # Nunca escolhe a primeira conversa por posição. A linha precisa ter
        # o estado visual de não lida exposto pelo próprio navegador interno.
        if actionable and _open_target(actionable[0]):
            processed = _process_thread("unread-row-metadata")
            cooldown = 300 if processed.get("reason") == "no-pending-incoming" else 60
            _RECENT_UNREAD_TARGETS[_unread_target_key(actionable[0])] = time.monotonic() + cooldown
            return {"active": True, "browser": "message", **aggregate, **processed}
        # Uma resposta feita pelo celular pode marcar a conversa como lida
        # antes do próximo ciclo. Se o próprio navegador sinalizou uma nova
        # mensagem, percorremos poucas conversas recentes e só respondemos se
        # o snapshot confirmar uma fala nova recebida.
        for target in _pending_message_fallback_targets(targets):
            if not _open_target(target):
                continue
            processed = _process_thread("message-event-fallback")
            cooldown = 300 if processed.get("reason") == "no-pending-incoming" else 60
            _RECENT_UNREAD_TARGETS[_unread_target_key(target)] = time.monotonic() + cooldown
            if processed.get("replied") or processed.get("reason") != "no-pending-incoming":
                return {"active": True, "browser": "message", **aggregate, **processed}
            _open_inbox()
            _wait(.35)
        return {"active": True, "browser": "inbox-no-new-unread", **aggregate}
    notification_result = {}
    if _sweep_due():
        return {"active": True, "browser": "sweep", **aggregate, **notification_result, **sweep("weekly")}
    if open_thread_result is not None:
        return {"active": True, "browser": "thread", **aggregate, **notification_result, **open_thread_result}
    return {"active": True, "browser": "ready", **aggregate, **notification_result}
