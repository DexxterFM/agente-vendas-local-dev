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
from scripts.vps.internal_browser import COMMENT_TEXTS


INBOX_URL = "https://www.instagram.com/direct/inbox/"
HOME_URL = "https://www.instagram.com/"
WEEKLY_SWEEP = timedelta(days=7)
COMMENT_LAST_KEY = 'sales.agent.campaign.comment.last'
COMMENT_POST_KEY_PREFIX = 'sales.agent.campaign.comment.post.'
ENGAGEMENT_ATTEMPTS = 3
BUBBLE_SPLIT = re.compile(r'\s*\[\[AGENT_BUBBLE\]\]\s*')
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
    if _click_surface(
        "/notifications/",
        ("notificações", "notifications", "atividade", "activity"),
        require_path=False,
    ):
        return True
    # O menu lateral expõe o coração como SVG com aria-label, sem href nem
    # texto. Nesse layout só o clique nativo no ponto do controle abre a
    # central; o ciclo não pode considerar a bolinha lida sem visitar essa
    # superfície.
    point = _page(r'''(()=>{
      const node=[...document.querySelectorAll('[aria-label]')].find(e=>/^(?:notifications|notificações)$/i.test(String(e.getAttribute('aria-label')||'')));
      if(!node)return null;
      const hit=node.closest('a,button,[role="link"],[role="button"]')||node, r=hit.getBoundingClientRect();
      return r.width>0&&r.height>0?{x:r.left+r.width/2,y:r.top+r.height/2}:null;
    })()''')
    if not isinstance(point, dict):
        return False
    try:
        browser.action({"kind": "click", "x": float(point["x"]), "y": float(point["y"])})
    except (KeyError, TypeError, ValueError, browser.InternalBrowserError):
        return False
    _wait(.9)
    return True


def _open_home() -> bool:
    current = urlparse(str(_page("location.href") or "")).path.rstrip("/") or "/"
    if current == "/":
        return True
    if _click_surface("/", ("página inicial", "home")):
        return True
    # Uma conversa aberta ou a central de notificações podem esconder o link
    # da home. A navegação interna preserva a sessão e devolve a tela de
    # referência, onde o agente lê os indicadores globais no próximo ciclo.
    browser.action({"kind": "navigate", "url": HOME_URL})
    for _ in range(12):
        _wait(.35)
        path = urlparse(str(_page("location.href") or "")).path.rstrip("/") or "/"
        if path == "/":
            return True
    return False


def _scroll_feed() -> None:
    """Rola a tela interna para revelar novos perfis no feed autenticado."""
    _page("window.scrollBy({top:Math.max(560,innerHeight*.82),behavior:'smooth'});true")
    _wait(.9)


def _prospecting_point(expression: str) -> dict[str, float] | None:
    value = _page(expression)
    if not isinstance(value, dict):
        return None
    try:
        return {"x": float(value["x"]), "y": float(value["y"])}
    except (KeyError, TypeError, ValueError):
        return None


def _engagement_metadata() -> dict[str, Any]:
    """Metadados de localização dos controles de engajamento da sessão interna."""
    try:
        value = browser.engagement_metadata()
    except browser.InternalBrowserError:
        return {}
    return value if isinstance(value, dict) else {}


def _wait_page_ready(timeout: float = 15.0) -> bool:
    """Só devolve quando a página carregou e tem conteúdo verificável."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if _page("document.readyState==='complete' && !!document.body && (document.body.innerText||'').length>40"):
                return True
        except browser.InternalBrowserError:
            pass
        _wait(0.35)
    return False


def _wait_post_controls(timeout: float = 15.0) -> tuple[bool, dict[str, Any]]:
    """Espera o modal do post terminar de montar curtida/comentário/repost."""
    deadline = time.monotonic() + timeout
    metadata: dict[str, Any] = {}
    while time.monotonic() < deadline:
        metadata = _engagement_metadata()
        if metadata.get("like_state") != "unknown" and metadata.get("comment"):
            return True, metadata
        _wait(0.35)
    return False, metadata


def _wait_for_state(key: str, expected: Any, timeout: float = 9.0) -> tuple[bool, dict[str, Any]]:
    """Faz polling dos metadados até o estado esperado ser observado."""
    deadline = time.monotonic() + timeout
    observed: dict[str, Any] = {}
    while time.monotonic() < deadline:
        observed = _engagement_metadata()
        if observed.get(key) == expected:
            return True, observed
        _wait(0.35)
    return False, observed


def _open_post() -> tuple[bool, dict[str, Any]]:
    """Abre a publicação do perfil e confirma que os controles apareceram.

    O clique no primeiro post pode ser perdido durante a animação da página;
    nesse caso like, comentário e repost ficam como ``unknown``. Retentar a
    abertura evita registrar três falhas que na verdade foram um clique perdido.
    """
    for attempt in range(1, ENGAGEMENT_ATTEMPTS + 1):
        metadata = _engagement_metadata()
        post = metadata.get("post")
        if post:
            browser.action({"kind": "click", **post})
            ready, observed = _wait_post_controls()
            if ready:
                return True, observed
        _wait(0.5)
    return False, _engagement_metadata()


def _audit_action(action_id: int, step: str, result: str, detail: str) -> None:
    """Grava o resultado medido de uma interação individual."""
    try:
        execute("campaignActionAudit", {
            "id": action_id, "step": step, "result": result, "detail": detail[:400],
        })
    except Exception:
        pass


def _engage_step(
    action_id: int,
    step: str,
    point_key: str,
    state_key: str,
    expected: Any,
) -> tuple[bool, dict[str, Any]]:
    """Localiza o alvo, clica e confirma pelo estado devolvido nos metadados."""
    metadata = _engagement_metadata()
    # Se o estado já é o desejado, clicar inverteria a ação (deixaria de seguir
    # ou descurtiria). Uma retentativa deve ser idempotente: medir e seguir.
    if metadata.get(state_key) == expected:
        _audit_action(action_id, step, "confirmed", f"already={state_key}={expected}")
        return True, metadata
    for attempt in range(1, ENGAGEMENT_ATTEMPTS + 1):
        point = metadata.get(point_key)
        if point:
            browser.action({"kind": "click", **point})
            confirmed, observed = _wait_for_state(state_key, expected)
            if confirmed:
                _audit_action(action_id, step, "confirmed", f"attempt={attempt}; {state_key}={expected}")
                return True, observed
        metadata = _engagement_metadata()
        if metadata.get(state_key) == expected:
            _audit_action(action_id, step, "confirmed", f"already={state_key}={expected}; after-attempt={attempt}")
            return True, metadata
        _wait(0.5)
    _audit_action(action_id, step, "unconfirmed", f"attempts={ENGAGEMENT_ATTEMPTS}; {state_key}={metadata.get(state_key)}")
    return False, metadata


def _comment_post_key(post_url: str, text: str) -> str:
    """Identifica um texto já usado em um post específico."""
    digest = hashlib.sha256(f"{post_url}\0{text}".encode("utf-8")).hexdigest()[:24]
    return f"{COMMENT_POST_KEY_PREFIX}{digest}"


def _comment_texts_used_in_post(post_url: str) -> tuple[str, ...]:
    """Textos aprovados que já foram publicados neste post."""
    if not post_url:
        return ()
    with Memory(load_config().db_path) as memory:
        return tuple(
            text for text in COMMENT_TEXTS
            if str(memory.get_setting(_comment_post_key(post_url, text), '') or '') == '1'
        )


def _record_comment_text_in_post(post_url: str, text: str) -> None:
    if not post_url or not text:
        return
    with Memory(load_config().db_path) as memory:
        memory.set_setting(_comment_post_key(post_url, text), '1')


def next_comment_text(exclude: tuple[str, ...] = ()) -> str:
    """Próxima variante em rotação, sem repetir a última nem textos do post."""
    try:
        with Memory(load_config().db_path) as memory:
            last = str(memory.get_setting(COMMENT_LAST_KEY, '') or '')
            try:
                start = COMMENT_TEXTS.index(last) + 1
            except ValueError:
                start = 0
            blocked = set(exclude or ())
            for offset in range(len(COMMENT_TEXTS)):
                chosen = COMMENT_TEXTS[(start + offset) % len(COMMENT_TEXTS)]
                if chosen not in blocked:
                    memory.set_setting(COMMENT_LAST_KEY, chosen)
                    return chosen
            return ''
    except Exception:
        return next((text for text in COMMENT_TEXTS if text not in (exclude or ())), '')


def _engage_comment(action_id: int) -> tuple[bool, dict[str, Any]]:
    """Abre o balão, digita pelo teclado e envia com Enter, sem clique em Post."""
    try:
        post_url = str(_page("location.href") or "")
    except Exception:
        post_url = ""
    used = _comment_texts_used_in_post(post_url)
    comment_text = next_comment_text(exclude=used)
    metadata = _engagement_metadata()
    # Não comentar duas vezes no mesmo post quando a ação já foi confirmada.
    if metadata.get("comment_present"):
        _audit_action(action_id, "comment", "confirmed", "already-commented")
        return True, metadata
    if not comment_text:
        _audit_action(action_id, "comment", "confirmed", "all-approved-variants-already-used")
        return True, metadata
    for attempt in range(1, ENGAGEMENT_ATTEMPTS + 1):
        point = metadata.get("comment")
        if point:
            browser.action({"kind": "click", **point})
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                metadata = _engagement_metadata()
                field = metadata.get("comment_field")
                if field:
                    break
                _wait(0.35)
            else:
                field = None
            if field:
                browser.action({"kind": "click", **field})
                browser.action({"kind": "key", "key": "SelectAll"})
                # Digitação exclusivamente pelo teclado de acessibilidade.
                browser.action({"kind": "type", "text": comment_text})
                # Envio pela tecla Enter: nenhum clique no botão de publicar.
                browser.action({"kind": "key", "key": "Enter"})
                _wait(0.3)
                confirmed, observed = _wait_for_state("comment_present", True, timeout=10.0)
                if confirmed:
                    _record_comment_text_in_post(post_url, comment_text)
                    _audit_action(action_id, "comment", "confirmed", f"attempt={attempt}; comment_present=True; text={comment_text[:60]}; submit=Enter")
                    return True, observed
                # Enter não confirmou: repete a tecla antes de desistir, sem
                # recorrer ao clique no botão da interface.
                browser.action({"kind": "key", "key": "Enter"})
                confirmed, observed = _wait_for_state("comment_present", True, timeout=6.0)
                if confirmed:
                    _record_comment_text_in_post(post_url, comment_text)
                    _audit_action(action_id, "comment", "confirmed", f"attempt={attempt}; comment_present=True; text={comment_text[:60]}; submit=Enter-retry")
                    return True, observed
        metadata = _engagement_metadata()
        _wait(0.5)
    _audit_action(action_id, "comment", "unconfirmed", f"attempts={ENGAGEMENT_ATTEMPTS}; comment_present={metadata.get('comment_present')}; text={comment_text[:60]}")
    return False, metadata


def _stable_point(key: str, *, tolerance: float = 4.0) -> dict[str, Any] | None:
    """Espera o botão do sheet parar de se mover antes de clicar.

    O sheet do repost entra com animação: o centro do botão roxo muda alguns
    pixels a cada quadro e um clique na primeira leitura cai no vazio. Só
    devolver o ponto depois de duas letras consecutivas estáveis.
    """
    previous: dict[str, Any] | None = None
    stable = 0
    last: dict[str, Any] | None = None
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        current = (_engagement_metadata() or {}).get(key)
        if not current:
            return None
        if previous and (abs(float(current["x"]) - float(previous["x"])) <= tolerance
                         and abs(float(current["y"]) - float(previous["y"])) <= tolerance):
            stable += 1
            if stable >= 2:
                return current
        else:
            stable = 0
        previous = current
        last = current
        _wait(0.25)
    return last


def _engage_repost(action_id: int) -> tuple[bool, dict[str, Any]]:
    """Executa o repost e confirma pelo estado final da página.

    O Instagram atual exige duas etapas: o ícone da barra de ações abre um
    sheet e o botão roxo "Repost" dentro dele confirma. O primeiro clique
    sozinho não muda o estado; por isso o segundo ponto é obrigatório antes
    de medir ``repost_state``.
    """
    def confirm_sheet(attempt: int) -> tuple[bool, dict[str, Any]] | None:
        """Clica no botão roxo do sheet e confirma o estado final."""
        confirm = _stable_point("repost_confirm")
        if not confirm:
            return None
        browser.action({"kind": "click", **confirm})
        done, final = _wait_for_state("repost_state", "reposted", timeout=10.0)
        if done:
            _audit_action(action_id, "repost", "confirmed", f"attempt={attempt}; repost_state=reposted")
            try:
                browser.action({"kind": "key", "key": "Escape"})
            except browser.InternalBrowserError:
                pass
            return True, final
        return None

    metadata = _engagement_metadata()
    if metadata.get("repost_state") == "reposted":
        _audit_action(action_id, "repost", "confirmed", "already-reposted")
        return True, metadata
    for attempt in range(1, ENGAGEMENT_ATTEMPTS + 1):
        # Uma tentativa anterior pode ter aberto o sheet sem clicar no botão
        # roxo: nesse estado o ícone da barra some (repost=None) e o estado
        # vira "unknown". Clicar direto no confirm evita o clique no ícone.
        result = confirm_sheet(attempt)
        if result:
            return result
        point = metadata.get("repost") or metadata.get("share")
        if point:
            browser.action({"kind": "click", **point})
            # O sheet com o botão roxo aparece em menos de 1s e pode sumir
            # rápido; fazer polling até o ponto existir ou o estado mudar.
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                observed = _engagement_metadata()
                if observed.get("repost_state") == "reposted":
                    _audit_action(action_id, "repost", "confirmed", f"attempt={attempt}; repost_state=reposted")
                    return True, observed
                if observed.get("repost_confirm"):
                    break
                _wait(0.2)
            result = confirm_sheet(attempt)
            if result:
                return result
        metadata = _engagement_metadata()
        _wait(0.5)
    _audit_action(action_id, "repost", "unconfirmed", f"attempts={ENGAGEMENT_ATTEMPTS}; repost_state={metadata.get('repost_state')}")
    return False, metadata


class _ProspectSkip(RuntimeError):
    """Perfil sem superfície de DM; retentar não muda o resultado."""


def _own_username() -> str:
    """Lê o identificador da conta logada no menu lateral."""
    value = _page(r'''(()=>{
      for(const img of document.querySelectorAll("img[alt$='s profile picture']")){
        const link=img.closest('a[href]');
        if(!link)continue;
        const rect=img.getBoundingClientRect();
        if(!rect.width||rect.width>48||rect.left>140)continue;
        let parts=[];try{parts=new URL(link.href,location.href).pathname.split('/').filter(Boolean)}catch{continue}
        if(parts.length===1)return parts[0].toLowerCase();
      }
      return '';
    })()''')
    return str(value or "").strip().lower()


def _profile_message_button() -> dict[str, float] | None:
    """Localiza o controle de mensagem no cabeçalho do perfil."""
    return _prospecting_point(r'''(()=>{
      const norm=v=>String(v||'').replace(/\s+/g,' ').trim();
      const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
      const e=[...document.querySelectorAll('button,[role="button"],a')].filter(visible).find(x=>{
        const label=norm(x.getAttribute('aria-label')||x.getAttribute('title')||x.innerText);
        return /^(mensagem|message|enviar mensagem|send message)$/i.test(label);
      });
      if(!e)return null;const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};
    })()''')


def _open_profile_dm(username: str) -> dict[str, Any]:
    """Abre a DM do perfil aceitando a página de thread ou o overlay da interface.

    A versão web do Instagram pode abrir o chat como um painel sobre o próprio
    perfil, sem mudar a URL para ``/direct/t/<id>``. O fluxo antigo exigia a
    URL de thread e descartava justamente esse formato.
    """
    expected = f"/{username}".rstrip("/")
    current = urlparse(str(_page("location.href") or "")).path.rstrip("/")
    if current != expected:
        browser.action({"kind": "navigate", "url": f"https://www.instagram.com/{username}/"})
        _wait(1.4)
    _page("window.scrollTo(0,0);true")
    point = None
    for _ in range(24):
        point = _profile_message_button()
        if point:
            break
        _wait(.5)
    if not point:
        raise _ProspectSkip("Botão de mensagem não encontrado")
    browser.action({"kind": "click", **point})
    for _ in range(24):
        _wait(.5)
        url = str(_page("location.href") or "")
        path = urlparse(url).path.rstrip("/")
        if not _composer_center():
            continue
        if path.startswith("/direct/t/"):
            parts = path.strip("/").split("/")
            return {"mode": "thread", "url": url, "thread_id": parts[2] if len(parts) > 2 else ""}
        if path == expected:
            return {"mode": "overlay", "url": url, "thread_id": ""}
    raise RuntimeError("Conversa ainda carregando; envio não executado")


def _overlay_panel_expression(text: str) -> str:
    """Expressão que localiza o painel do overlay e mede a bolha enviada."""
    return fr'''(()=>{{
      const canonical=v=>String(v||'').replace(/[\u{{1F000}}-\u{{1FAFF}}\u2600-\u27BF\uFE00-\uFE0F\u200D\u20E3]/gu,'').replace(/\s+/g,' ').trim();
      const target=canonical({text!r});
      const visible=e=>{{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'}};
      const fields=[...document.querySelectorAll('textarea,[contenteditable="true"],[role="textbox"]')].filter(visible);
      const composer=fields.find(e=>/mensagem|message|responder|reply/i.test([e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ')))
        ||fields.find(e=>e.matches('[contenteditable="true"],[role="textbox"]')&&!/pesquis|search/i.test(e.placeholder||''));
      if(!composer)return {{found:false,count:0,panel_text:false}};
      let panel=composer;
      for(let d=0;d<12&&panel;d++,panel=panel.parentElement){{
        const r=panel.getBoundingClientRect();
        if(r.width>=340&&r.width<=440&&r.height>=300)break;
      }}
      if(!panel)return {{found:false,count:0,panel_text:false}};
      const nodes=[...panel.querySelectorAll('[role="row"],[role="listitem"],[role="article"],[role="message"],[dir="auto"]')].filter(visible);
      const count=nodes.filter(e=>e!==composer&&!composer.contains(e)&&!e.contains(composer)&&canonical(e.innerText||e.textContent||'')===target).length;
      const panel_text=canonical(panel.innerText).includes(target);
      return {{found:true,count,panel_text}};
    }})()'''


def _overlay_state(text: str) -> dict[str, Any]:
    value = _page(_overlay_panel_expression(text))
    if not isinstance(value, dict):
        return {"found": False, "count": 0, "panel_text": False}
    return {
        "found": bool(value.get("found")),
        "count": int(value.get("count") or 0),
        "panel_text": bool(value.get("panel_text")),
    }


def _send_overlay_bubble(text: str) -> dict[str, Any]:
    """Envia uma bolha no painel de DM aberto sobre o perfil."""
    composer_text = _composer_safe_text(text)
    url = str(_page("location.href") or "")
    if not _composer_center():
        raise browser.InternalBrowserError("Campo de mensagem não encontrado")
    _focus_composer()
    before_state = _overlay_state(composer_text)
    before = before_state["count"]
    if before:
        # A bolha já está na conversa: a retentativa apenas confirma o envio
        # anterior em vez de duplicar a mensagem.
        _clear_composer()
        return {"sent": True, "method": "overlay-already-present"}
    _wait(.15 + random.random() * .25)
    existing = _page("(()=>{const e=document.activeElement;return String(e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if existing:
        _clear_composer()
    _focus_composer()
    browser.action({"kind": "type", "text": composer_text})
    entered = _page("(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if str(entered or "").strip() != composer_text:
        raise browser.InternalBrowserError("Texto não foi inserido no campo da conversa")
    if str(_page("location.href") or "") != url:
        raise browser.InternalBrowserError("Conversa mudou antes do envio")
    # Envio apenas pela tecla Enter do teclado de acessibilidade: nenhum
    # clique no botão visual de enviar.
    browser.action({"kind": "key", "key": "Enter"})
    _wait(.28)
    still_draft = _page("(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if str(still_draft or "").strip() == composer_text:
        browser.action({"kind": "key", "key": "Enter"})
    for _ in range(12):
        _wait(.5)
        if str(_page("location.href") or "") != url:
            raise browser.InternalBrowserError("Conversa mudou antes da confirmação")
        state = _overlay_state(composer_text)
        if state["count"] > before:
            return {"sent": True, "method": "overlay-keyboard-enter"}
        draft = _page("(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()})()")
        if not str(draft or "").strip() and state["panel_text"]:
            return {"sent": True, "method": "overlay-keyboard-enter-cleared"}
    raise browser.InternalBrowserError("Mensagem não apareceu na conversa para confirmação")


def _prospecting_cycle() -> dict[str, Any]:
    """Executa uma rodada espaçada de prospecção pela sessão persistente."""
    status = execute("agentStatus", {})
    if not status.get("active") or not status.get("prospecting_active"):
        return {"prospecting": False}
    current = urlparse(str(_page("location.href") or ""))
    if current.path.rstrip("/") not in {"", "/"}:
        return {"prospecting": True, "browser": "prospecting-waiting-home"}
    pacing = execute("prospectingPacing", {"mode": "status"})
    if not pacing.get("ready"):
        return {"prospecting": True, "browser": "prospecting-paced", "wait_seconds": pacing.get("wait_seconds", 0)}
    profiles = _page(r'''(()=>{
      const reserved=new Set(['accounts','direct','explore','reels','stories','about','developer','legal','privacy','web','p','reel','tv']);
      const own=__OWN__;
      const out=[],seen=new Set();
      for(const link of document.querySelectorAll('a[href]')){
        let parts=[];try{parts=new URL(link.href,location.href).pathname.split('/').filter(Boolean)}catch{continue}
        // Somente perfis: /p/<code>/ e /reel/<code>/ também têm um primeiro
        // segmento válido e antes entravam na fila como se fossem usuários.
        if(parts.length!==1)continue;
        const path=parts[0];
        if(!/^[a-z0-9._]{2,30}$/i.test(path)||reserved.has(path.toLowerCase())||path.toLowerCase()===own||seen.has(path.toLowerCase()))continue;
        const rect=link.getBoundingClientRect();if(!rect.width||!rect.height||rect.top>innerHeight*1.4)continue;
        let scope=link;for(let i=0;i<5&&scope.parentElement;i++,scope=scope.parentElement){if((scope.innerText||'').length>1800)break}
        const text=(scope.innerText||'').replace(/\s+/g,' ').trim().slice(0,4000);
        const following=/\b(?:seguindo|following)\b/i.test(text);
        seen.add(path.toLowerCase());out.push({username:path.toLowerCase(),text,following});
      }
      return out.slice(0,30);
    })()'''.replace("__OWN__", repr(_own_username())))
    if not isinstance(profiles, list) or not profiles:
        _scroll_feed()
        return {"prospecting": True, "browser": "prospecting-scrolled", "discovered": 0}
    discovered = execute("campaignDiscover", {"profiles": profiles})
    created = discovered.get("created", [])
    created = created if isinstance(created, list) else []
    if not created:
        # Perfis já seguidos ou descartados pelo segmento não geram lead. Rolar
        # o feed é a única forma de revelar novos candidatos; sem isto o worker
        # fica preso em "no-candidate" forever enquanto há feed não explorado.
        _scroll_feed()
    claim = execute("campaignClaim", {})
    if not claim.get("claimed"):
        if not created:
            return {"prospecting": True, "browser": "prospecting-scrolled", "discovered": 0}
        return {"prospecting": True, "browser": "prospecting-no-candidate", "discovered": len(created)}
    payload = claim.get("payload") or {}
    username = str(payload.get("username") or "").strip().lower()
    action_id = int(claim.get("id") or 0)
    stage = str(claim.get("stage") or "")
    if not re.fullmatch(r"[a-z0-9._]{2,30}", username) or username == _own_username():
        execute("campaignConfirm", {"id": action_id, "state": "skipped", "note": "Perfil inválido para prospecção"})
        return {"prospecting": True, "browser": "prospecting-skipped", "username": username}
    reserved = execute("prospectingPacing", {"mode": "reserve", "kind": "instagram_campaign", "target": username})
    if not reserved.get("reserved"):
        execute("campaignConfirm", {"id": action_id, "state": "pending", "note": "Aguardando a próxima janela"})
        return {"prospecting": True, "browser": "prospecting-paced", "wait_seconds": reserved.get("wait_seconds", 0)}
    try:
        intro = str(payload.get('intro') or 'Olá! Muito legal o trabalho de vocês ❤️')
        profile_text = str(payload.get('profile_text') or '')
        actions: dict[str, bool] = {}
        if stage != "dm":
            browser.action({"kind": "navigate", "url": f"https://www.instagram.com/{username}/"})
            _wait_page_ready()
            engagement = _engagement_metadata()
            actions["follow"], engagement = _engage_step(
                action_id, "follow", "follow", "follow_state", "following"
            )
            controls_ready, engagement = _open_post()
            if not controls_ready:
                _audit_action(action_id, "post", "unconfirmed", "controles de post ausentes apos abrir publicacao")
            actions["like"], engagement = _engage_step(
                action_id, "like", "like", "like_state", "liked"
            )
            actions["comment"], engagement = _engage_comment(action_id)
            actions["repost"], engagement = _engage_repost(action_id)
            # Entra no perfil que recebeu as ações, lê nome+bio e escolhe a
            # saudação já aprovada nos fluxos para clínica ou profissional.
            browser.action({"kind": "navigate", "url": f"https://www.instagram.com/{username}/"})
            _wait_page_ready(timeout=10.0)
            profile_text = str(_page(r'''(()=>{
              const scope=document.querySelector('header section')||document.querySelector('header')||document.body;
              return (scope.innerText||'').replace(/\s+/g,' ').trim().slice(0,4000);
            })()''') or '')
            intro_info = execute("campaignProfileIntro", {"username": username, "text": profile_text})
            intro = str(intro_info.get("intro") or intro)
            # A partir daqui a retentativa não repete follow/curtida/comentário/
            # repost: apenas reabre a DM do mesmo perfil.
            execute("campaignStage", {"id": action_id, "stage": "dm"})
        # O cadastro persistente decide se esta mensagem já foi aplicada a este
        # perfil. Sem esta barreira a retentativa reenvia a mesma saudação.
        guard = execute("campaignMessageGuard", {"username": username, "text": intro})
        if not guard.get("allowed", True):
            reason = str(guard.get("reason") or "duplicate-message")
            execute("campaignConfirm", {
                "id": action_id, "state": "skipped",
                "note": "Mensagem repetida bloqueada pelo cadastro: " + reason,
            })
            _audit_action(action_id, "dm", "skipped", reason)
            execute("campaignProfileObserve", {
                "username": username, "text": profile_text, "actions": actions, "stage": "dm",
            })
            try:
                _open_home()
            except browser.InternalBrowserError:
                pass
            return {
                "prospecting": True, "browser": "prospecting-duplicate",
                "username": username, "reason": reason,
            }
        surface = _open_profile_dm(username)
        if surface.get("mode") == "thread" and surface.get("url"):
            send_result = _send_bubble(intro, str(surface["url"]))
        else:
            send_result = _send_overlay_bubble(intro)
        actions["dm"] = bool(send_result.get("sent")) if isinstance(send_result, dict) else True
        measured = ", ".join(f"{name}={'ok' if value else 'falha'}" for name, value in actions.items())
        note = "Interações medidas: " + measured
        execute("campaignConfirm", {"id": action_id, "state": "sent", "note": note[:1000]})
        _audit_action(action_id, "dm", "confirmed" if actions["dm"] else "unconfirmed", note[:400])
        execute("campaignProfileObserve", {
            "username": username,
            "text": profile_text,
            "actions": actions,
            "message": intro,
            "sent": bool(actions["dm"]),
            "stage": "dm",
        })
        try:
            _open_home()
        except browser.InternalBrowserError:
            pass
        return {
            "prospecting": True,
            "browser": "prospecting-sent",
            "username": username,
            "action_id": action_id,
            "mode": surface.get("mode"),
            "actions": actions,
        }
    except _ProspectSkip as exc:
        execute("campaignConfirm", {"id": action_id, "state": "skipped", "note": str(exc)[:500]})
        try:
            _open_home()
        except browser.InternalBrowserError:
            pass
        return {
            "prospecting": True,
            "browser": "prospecting-skipped",
            "username": username,
            "reason": str(exc)[:160],
        }
    except Exception as exc:
        try:
            outcome = execute("campaignFail", {"id": action_id, "note": str(exc)[:500]})
        except Exception:
            outcome = {}
        try:
            _open_home()
        except browser.InternalBrowserError:
            pass
        return {
            "prospecting": True,
            "browser": "prospecting-error",
            "error": str(exc)[:160],
            "retry_state": outcome.get("state"),
            "attempts": outcome.get("attempts"),
        }


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
        const textualUnread=/\b(?:unread|não lida|nova mensagem)\b/i.test(label);
        // O rótulo de uma linha não lida termina com "Unread", depois do
        // horário. A regra anterior aceitava apenas horário no fim e
        // descartava exatamente as conversas que precisavam de resposta.
        if(!href&&!ignored.test(label)&&!textualUnread&&!(label.length>8&&time.test(label)))continue;
        if(!href&&ignored.test(label))continue;
        const key=href||label;
        if(key&& !seen.has(key)){
          seen.add(key);
          const elements=[scope,...scope.querySelectorAll('*')].filter(visible);
          const bold=elements.some(e=>Number.parseInt(getComputedStyle(e).fontWeight,10)>=600&&norm(e.textContent).length>1);
          const scopeRect=scope.getBoundingClientRect();
           const blue=elements.some(e=>{
            const r=e.getBoundingClientRect(), accessibility=norm([e.getAttribute('aria-label'),e.getAttribute('title')].join(' '));
            const rightDot=r.width>=3&&r.height>=3&&r.width<=16&&r.height<=16&&Math.abs(r.width-r.height)<=4&&r.left>=scopeRect.left;
             const tag=e.tagName.toLowerCase(), background=rgb(getComputedStyle(e).backgroundColor);
             const rounded=getComputedStyle(e).borderRadius;
             const emptyBlueDot=(tag==='div'||tag==='span')&&!norm(e.textContent)&&rounded&&background&&background[2]>=140&&background[2]-background[0]>=25&&background[2]-background[1]>=5;
             return /^(?:unread|não lida|nova mensagem)$/i.test(accessibility)||textualUnread||(rightDot&&emptyBlueDot);
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


def _focus_composer() -> None:
    """Só permite edição após o DOM confirmar o foco em campo editável da DM."""
    for _ in range(24):
        point = _composer_center()
        if point:
            browser.action({"kind": "click", **point})
            focused = _page(r'''(()=>{const e=document.activeElement;if(!e||e===document.body)return false;
              const label=[e.getAttribute('placeholder'),e.getAttribute('aria-label'),e.type].join(' ');
              return !/search|pesquis|password|senha/i.test(label)&&
                (e.isContentEditable||e.tagName==='TEXTAREA')&&e.getBoundingClientRect().width>0;
            })()''')
            if focused:
                return
        _wait(.35)
    raise browser.InternalBrowserError("Campo de DM ainda indisponível; envio adiado sem editar a página")


def _clear_composer() -> None:
    """Remove de forma nativa qualquer rascunho deixado por uma tentativa."""
    # Uma tentativa anterior pode deixar o compositor com o foco visual, mas
    # sem foco de teclado depois de uma transição da interface. Reconfirme o
    # foco pelo mouse antes de cada tentativa; nunca acrescente uma resposta
    # ao texto que ficou no campo.
    for attempt in range(3):
        _focus_composer()
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
    if str(_page("location.href") or "") != expected_url:
        raise browser.InternalBrowserError("Conversa mudou antes da preparação do envio")
    _focus_composer()
    before = _message_count(composer_text)
    _wait(.15 + random.random() * .25)
    existing = _page("(()=>{const e=document.activeElement;return String(e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if existing:
        _clear_composer()
    _focus_composer()
    browser.action({"kind": "type", "text": composer_text})
    entered = _page("(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if str(entered or "").strip() != composer_text:
        raise browser.InternalBrowserError("Texto não foi inserido no campo da conversa")
    if str(_page("location.href") or "") != expected_url:
        raise browser.InternalBrowserError("Conversa mudou antes do envio")
    # Envio apenas pela tecla Enter do teclado de acessibilidade: nenhum
    # clique no botão visual de enviar.
    browser.action({"kind": "key", "key": "Enter"})
    _wait(.28)
    still_draft = _page("(()=>{const e=document.activeElement;return (e?.value||e?.innerText||e?.textContent||'').trim()})()")
    if str(still_draft or "").strip() == composer_text:
        # Reidratação da interface pode perder o primeiro Enter. Repete a
        # tecla antes de considerar o envio como falho.
        browser.action({"kind": "key", "key": "Enter"})
    for _ in range(12):
        _wait(.5)
        if str(_page("location.href") or "") != expected_url:
            raise browser.InternalBrowserError("Conversa mudou antes da confirmação")
        if _message_count(composer_text) > before:
            return {"sent": True, "method": "keyboard-enter-send"}
    after = _thread_snapshot().get("messages") or []
    if after and after[-1].get("direction") == "outgoing" and after[-1].get("text") == composer_text:
        return {"sent": True, "method": "keyboard-enter-visible-bubble"}
    raise browser.InternalBrowserError("Mensagem não apareceu na conversa para confirmação")


def _process_thread(source: str) -> dict[str, Any]:
    snap = _thread_snapshot()
    # A linha pode mudar para /direct/t/ antes do painel da conversa terminar
    # de montar. Aguarde o próprio DOM fornecer thread, perfil e mensagens;
    # sem isso uma DM recebida pelo celular era descartada como metadado vazio.
    if not snap["thread_id"] or not snap["username"] or not snap["messages"]:
        for _ in range(12):
            _wait(.35)
            snap = _thread_snapshot()
            if snap["thread_id"] and snap["username"] and snap["messages"]:
                break
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
    bubbles = [item.strip() for item in BUBBLE_SPLIT.split(str(cycle["text"])) if item.strip()]
    for index, bubble in enumerate(bubbles):
        sent.append(_send_bubble(bubble, snap["url"]))
        if index + 1 < len(bubbles):
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


def _notification_candidates() -> list[dict[str, Any]]:
    """Lê somente perfis associados explicitamente a novo seguidor."""
    opened = _open_notifications()
    if not opened:
        # Algumas versões deixam os eventos da central renderizados na página
        # inicial e o ícone não muda a rota. Se já há botões Follow Back
        # visíveis, a central está disponível para leitura mesmo sem navegação.
        available = _page(r'''(()=>[...document.querySelectorAll('button,[role="button"]')].some(e=>/seguir(?:\s+de)?\s+volta|follow\s+back/i.test(String(e.getAttribute('aria-label')||e.innerText||''))))()''')
        if not available:
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
          if(match){
            const controls=[...row.querySelectorAll('button,[role="button"]')].filter(e=>{const t=String(e.getAttribute('aria-label')||e.innerText||'');return /seguir(?:\s+de)?\s+volta|follow\s+back/i.test(t)});
            const control=controls[0]||null, rect=control?control.getBoundingClientRect():null;
            const profile=[...row.querySelectorAll('a[href]')].find(a=>{try{return new URL(a.href,location.href).pathname.split('/').filter(Boolean).length===1}catch{return false}});
            output.push({username:match[0].toLowerCase(),profile_href:profile?profile.href:'',profile_text:text.slice(0,1200),x:rect?rect.left+rect.width/2:null,y:rect?rect.top+rect.height/2:null});break;
          }
        }
      }
      // Quando a central já foi visualizada, o texto do evento pode sair do
      // DOM, mas o botão azul permanece. Nesse caso, use o próprio botão como
      // âncora e suba até a linha que contém o perfil.
      for(const button of [...document.querySelectorAll('button,[role="button"]')]){
        const label=String(button.getAttribute('aria-label')||button.innerText||'');
        if(!/seguir(?:\s+de)?\s+volta|follow\s+back/i.test(label))continue;
        let row=button, profile=null;
        for(let depth=0;row&&depth<9;depth++,row=row.parentElement){
          profile=[...row.querySelectorAll('a[href]')].map(a=>{try{return {a,parts:new URL(a.href,location.href).pathname.split('/').filter(Boolean)}}catch{return null}}).find(v=>v&&v.parts.length===1&&/^[a-z0-9._]{1,30}$/i.test(v.parts[0]));
          if(profile)break;
        }
        if(profile){const r=button.getBoundingClientRect();output.push({username:profile.parts[0].toLowerCase(),profile_href:profile.a.href,profile_text:String(row.innerText||'').replace(/\s+/g,' ').trim().slice(0,1200),x:r.left+r.width/2,y:r.top+r.height/2});}
      }
      return [...new Set(output)].slice(0,20);
    })()''')
    result=[]; seen=set()
    for item in (value if isinstance(value,list) else []):
        if isinstance(item,str): item={'username':item}
        if not isinstance(item,dict): continue
        username=str(item.get('username') or '').lower()
        if not username or len(username)>30 or username in seen: continue
        seen.add(username); result.append({'username':username,'profile_href':str(item.get('profile_href') or ''),'profile_text':str(item.get('profile_text') or '')[:1200],'x':item.get('x'),'y':item.get('y')})
    return result


def _click_live_follow_back(username: str, fallback: dict[str, Any]) -> bool:
    """Resolve novamente o botão no HTML imediatamente antes do clique.

    A central muda a posição das linhas após cada interação; coordenadas
    capturadas em uma leitura anterior nunca são a fonte primária do clique.
    """
    point = _page(fr'''(()=>{{
      const username={username!r}.toLowerCase();
      const isFollowBack=e=>/^(?:seguir(?:\s+de)?\s+volta|follow\s+back)$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').replace(/\s+/g,' ').trim());
      for(const anchor of document.querySelectorAll('a[href]')){{
        let path='';try{{path=new URL(anchor.href,location.href).pathname.split('/').filter(Boolean)[0]||''}}catch{{}}
        if(path.toLowerCase()!==username)continue;
        let row=anchor;
        for(let depth=0;row&&depth<10;depth++,row=row.parentElement){{
          const button=[...row.querySelectorAll('button,[role="button"]')].find(isFollowBack);
          if(!button)continue;
          const r=button.getBoundingClientRect();
          if(r.width>0&&r.height>0)return {{x:r.left+r.width/2,y:r.top+r.height/2}};
        }}
      }}
      return null;
    }})()''')
    if not isinstance(point, dict):
        point = {"x": fallback.get("x"), "y": fallback.get("y")}
    try:
        browser.action({'kind': 'click', 'x': float(point['x']), 'y': float(point['y'])})
        _wait(.7)
        # A confirmação também é estrutural: o botão da própria linha deixa
        # de ser "Seguir de volta" depois do clique aceito.
        state = _page(fr'''(()=>{{
          const username={username!r}.toLowerCase();
          for(const a of document.querySelectorAll('a[href]')){{
            let p='';try{{p=new URL(a.href,location.href).pathname.split('/').filter(Boolean)[0]||''}}catch{{}}
            if(p.toLowerCase()!==username)continue;
            let row=a;for(let d=0;row&&d<10;d++,row=row.parentElement){{
              const labels=[...row.querySelectorAll('button,[role="button"]')].map(e=>String(e.getAttribute('aria-label')||e.innerText||'').replace(/\s+/g,' ').trim());
              if(labels.some(v=>/^(?:seguindo|following)$/i.test(v)))return true;
            }}
          }}return false;
        }})()''')
        return bool(state)
    except (KeyError, TypeError, ValueError, browser.InternalBrowserError):
        return False


def _capture_notification_actions() -> dict[str, int]:
    candidates = _notification_candidates()
    queued = 0
    followed = 0
    welcomed = 0
    for candidate in candidates:
        username=str(candidate.get('username') or '')
        result = execute("browserNotificationCandidate", {"username": username, "kind": "new_follower"})
        if result.get("queued") or result.get("duplicate"):
            if result.get("queued"):
                queued += 1
            if _click_live_follow_back(username, candidate):
                followed += 1
            plan=execute('followerCycle', {'username':username,'profile':{'text':candidate.get('profile_text','')}})
            if plan.get('new_follower') and welcomed < 1:
                try:
                    surface = _open_profile_dm(username)
                    for bubble in BUBBLE_SPLIT.split(str(plan.get('text') or '')):
                        bubble = bubble.strip()
                        if not bubble:
                            continue
                        if surface.get("mode") == "thread" and surface.get("url"):
                            _send_bubble(bubble, str(surface["url"]))
                        else:
                            _send_overlay_bubble(bubble)
                    execute('followerConfirm', {'username': username, 'text': str(plan.get('text') or '')})
                    welcomed += 1
                except Exception:
                    continue
    try:
        _open_home()
    except browser.InternalBrowserError:
        pass
    return {"notification_candidates": len(candidates), "notification_queued": queued, "notification_followed": followed, "notification_welcomed": welcomed}


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


def cycle(mode: str | None = None) -> dict[str, Any]:
    """Executa somente o modo que está no turno da fila.

    `sales` atende DMs/notificações e `prospecting` varre o feed. Um job
    concluído (ou alguns ciclos sem job) devolve o turno ao outro modo.
    """
    state = execute("agentStatus", {})
    if not state.get("active"):
        return {"active": False, "browser": "paused"}
    mode_state = execute("browserModeStatus", {})
    current_mode = str(mode or mode_state.get("mode") or "sales").strip().lower()
    if current_mode not in ("sales", "prospecting"):
        current_mode = "sales"

    def done(payload: dict[str, Any], job: bool = False, detail: str = "") -> dict[str, Any]:
        result = {"active": True, "mode": current_mode, **payload}
        if job:
            nxt = execute("browserModeComplete", {"mode": current_mode, "detail": detail})
        else:
            nxt = execute("browserModeIdle", {"mode": current_mode})
        new_mode = str(nxt.get("mode") or current_mode)
        result["mode"] = new_mode
        result["next_mode"] = str(nxt.get("next_mode") or "")
        result["idle_cycles"] = int(nxt.get("idle_cycles") or 0)
        # A troca de turno marca o fim da tarefa (ou o timeout de ociosidade).
        # Voltar para a home devolve a tela de referência ao agente, que passa
        # a ler os indicadores globais sem ficar preso em DM, notificações ou
        # perfil de prospecção até o próximo ciclo do outro modo.
        if new_mode != current_mode:
            try:
                result["returned_home"] = bool(_open_home())
            except browser.InternalBrowserError:
                result["returned_home"] = False
        return result

    status = browser.status()
    if not status.get("running") or not status.get("ready"):
        return done({"browser": "offline"})
    snap = browser.snapshot()
    try:
        page_watchdog = browser.stalled_page_watchdog()
    except browser.InternalBrowserError:
        page_watchdog = {"stalled": False, "armed": False, "throttled": False}
    # A URL é verificada antes da heurística de DOM. Durante login, páginas
    # de identidade podem não ter campos de credencial durante uma transição;
    # nessa situação o agente deve ficar rigorosamente passivo.
    # A caixa de entrada pode exibir o skeleton por alguns instantes enquanto
    # a lista é atualizada. Não bloqueie o ciclo de DM nesse estado: a leitura
    # dos marcadores e das linhas continua sendo feita no mesmo documento.
    if page_watchdog.get("stalled") and not str(snap.get("url") or "").startswith("https://www.instagram.com/direct"):
        return done({"browser": "recovering-page", "page_watchdog": page_watchdog})
    if _login_or_identity_step(str(snap.get("url") or "")) or not snap.get("authenticated"):
        return done({"browser": "waiting-login"})
    try:
        frontend = browser.frontend_events(clear=True)
    except browser.InternalBrowserError:
        frontend = {"event_count": 0, "events": [], "last": None}
    url = str(snap.get("url") or "")
    open_thread_result: dict[str, Any] | None = None
    indicators = browser.metadata()
    event_rows = [item for item in frontend.get("events") or [] if isinstance(item, dict)]
    last_event = frontend.get("last") if isinstance(frontend.get("last"), dict) else {}
    aggregate = {
        "message_pending": bool(indicators.get("message_pending") or any(e.get("message_pending") or e.get("unread_rows") for e in event_rows) or last_event.get("message_pending") or last_event.get("unread_rows")),
        "notification_pending": bool(indicators.get("notification_pending") or any(e.get("notification_pending") for e in event_rows) or last_event.get("notification_pending")),
        "message_controls": int(indicators.get("message_controls") or 0),
        "notification_controls": int(indicators.get("notification_controls") or 0),
        "frontend_events": len(event_rows),
        "frontend_unread_rows": int(last_event.get("unread_rows") or 0),
    }

    if current_mode == "prospecting":
        # Nenhuma leitura de conversa neste turno: a prospecção usa sozinha o
        # documento autenticado e devolve a fila ao atendimento ao terminar.
        if (urlparse(url).path.rstrip("/") in {"", "/"}
                and bool(state.get("prospecting_active"))
                and not aggregate["message_pending"] and not aggregate["notification_pending"]):
            prospecting_result = _prospecting_cycle()
            browser_state = str(prospecting_result.get("browser") or "")
            job = browser_state in {"prospecting-sent", "prospecting-skipped"}
            detail = f"{browser_state}:{prospecting_result.get('username', '')}"
            return done({**aggregate, **prospecting_result}, job=job, detail=detail)
        return done({**aggregate, "browser": "prospecting-waiting"})

    if "/direct/t/" in url:
        open_thread_result = _process_thread("open-thread")
        # Uma conversa aberta não pode impedir a descoberta das demais DMs.
        # Só permanecemos nela quando houve uma ação real neste ciclo.
        if open_thread_result.get("replied") or open_thread_result.get("reaction_pending"):
            return done({"browser": "thread", **open_thread_result}, job=True, detail="open-thread")
    # A central de notificações tem prioridade quando os dois indicadores
    # vermelhos aparecem juntos. Antes, o retorno antecipado do ramo de DMs
    # impedia esta rotina de ser alcançada indefinidamente.
    # A bolinha pode desaparecer assim que o operador abre a central. Ainda
    # assim, perfis com o botão real "Seguir de volta" permanecem acionáveis;
    # faça uma varredura periódica fora de uma conversa aberta para não perder
    # o evento apenas porque ele já foi marcado como visualizado.
    if (_notification_scan_due()
            and (aggregate["notification_pending"] or not aggregate["message_pending"])):
        notification_result = _capture_notification_actions()
        _mark_notification_scan()
        job = any(int(notification_result.get(key) or 0) > 0
                  for key in ("queued", "followed", "welcomed"))
        return done({"browser": "notification", **aggregate, **notification_result},
                    job=job, detail="notification")
    if aggregate["message_pending"]:
        if urlparse(url).path.rstrip("/") != "/direct/inbox":
            if not _open_inbox():
                return done({"browser": "inbox-control-unavailable", **aggregate})
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
            return done({"browser": "message", **aggregate, **processed},
                        job=bool(processed.get("replied")), detail="message")
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
                return done({"browser": "message", **aggregate, **processed},
                            job=bool(processed.get("replied")), detail="message-fallback")
            _open_inbox()
            _wait(.35)
        return done({"browser": "inbox-no-new-unread", **aggregate})
    notification_result = {}
    if _sweep_due():
        sweep_result = sweep("weekly")
        job = any(int(sweep_result.get(key) or 0) > 0 for key in ("imported", "replied"))
        return done({"browser": "sweep", **aggregate, **notification_result, **sweep_result},
                    job=job, detail="sweep")
    if open_thread_result is not None:
        return done({"browser": "thread", **aggregate, **notification_result, **open_thread_result})
    return done({"browser": "ready", **aggregate, **notification_result})
