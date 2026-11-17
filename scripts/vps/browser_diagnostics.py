"""Continuous aggregate browser telemetry; no cookies or conversation text."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.vps import internal_browser as browser

ROOT = Path(os.environ.get('SALES_AGENT_DATA_DIR', '/var/lib/agente-vendas-local')) / 'diagnostics'
RECOVERY_REQUEST = ROOT / 'browser-recovery.request'


def resource_sample():
    """Read process counters even when the renderer cannot answer."""
    processes = []
    for entry in Path('/proc').glob('[0-9]*'):
        try:
            values = dict(line.split(':', 1) for line in (entry / 'status').read_text().splitlines() if ':' in line)
            if 'chromium' not in values.get('Name', ''):
                continue
            # Scope counters to the agent service, not other applications.
            if 'agente-vendas-internal-browser.service' not in (entry / 'cgroup').read_text():
                continue
            processes.append({'pid': int(entry.name),
                              'rss_kib': int(values.get('VmRSS', '0').split()[0]),
                              'swap_kib': int(values.get('VmSwap', '0').split()[0])})
        except (OSError, ValueError, IndexError):
            continue
    return {'processes': processes, 'rss_kib': sum(p['rss_kib'] for p in processes),
            'swap_kib': sum(p['swap_kib'] for p in processes)}


def sample():
    """Obtém uma fotografia agregada em uma única conexão DevTools.

    O monitor não pode repetir ``visual_state`` + ``metadata`` + ``evaluate``:
    cada uma abria uma conexão e, junto com o worker, podia exceder a fila do
    renderizador. Nenhum texto, cookie ou nome de conversa é coletado.
    """
    target = browser._target()
    expression = r'''(()=>{
      const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
      const norm=v=>String(v||'').replace(/\s+/g,' ').trim();
      const label=e=>norm([e.innerText,e.getAttribute('aria-label'),e.getAttribute('title'),e.getAttribute('href')].filter(Boolean).join(' '));
      const path=location.pathname.toLowerCase();
      const controls=[...document.querySelectorAll('a,button,[role="button"],[role="link"]')].filter(visible);
      const fields=[...document.querySelectorAll('input,textarea,[contenteditable="true"],[role="textbox"]')].filter(visible);
      const shell=controls.some(e=>/mensagens|messages|direct|notifica|notifications|página inicial|home/i.test(label(e)));
      const composer=fields.some(e=>/mensagem|message|responder|reply/i.test([e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' '))) ||
        (path.startsWith('/direct/t/')&&fields.some(e=>e.matches('[contenteditable="true"],[role="textbox"]')&&!/pesquis|search/i.test(e.placeholder||'')));
      const search=fields.some(e=>/pesquis|search/i.test([e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ')));
      const direct=path.startsWith('/direct');
      const ready=document.readyState==='complete'&&shell&&(path.startsWith('/direct/t/')?composer:(direct?search:true));
      const active=document.activeElement;
      const eventState=window.__salesAgentFrontEventsV3;
      return {viewport:{width:innerWidth,height:innerHeight,scale:devicePixelRatio},document_state:document.readyState,
        visibility:document.visibilityState,composer_visible:composer,focus_editable:Boolean(active&&(active.isContentEditable||active.tagName==='TEXTAREA')),
        visual:{ready,path,authenticated_surface:shell,direct,document_ready:document.readyState==='complete'},
        observer:{installed:Boolean(eventState&&eventState.observer),queued:Number(eventState?.events?.length||0),sequence:Number(eventState?.sequence||0)}};
    })()'''
    def run(page):
        result = page.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if result.get("exceptionDetails"):
            raise browser.InternalBrowserError("Leitura diagnóstica recusada pela página")
        return (result.get("result") or {}).get("value")
    data = browser._with_page(run)
    if not isinstance(data, dict):
        raise browser.InternalBrowserError("Leitura diagnóstica inválida")
    return {'target_id': target.get('id'), **data}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    previous = None
    failures = 0
    while True:
        record = {'at': datetime.now(timezone.utc).isoformat(), 'resources': resource_sample()}
        try:
            state = sample()
            reasons = []
            if previous:
                if previous.get('target_id') != state.get('target_id'): reasons.append('target_changed')
                if previous.get('viewport') != state.get('viewport'): reasons.append('viewport_changed')
            visual = state.get('visual', {})
            if not visual.get('ready'): reasons.append('page_not_ready')
            if visual.get('direct') and '/direct/t/' in visual.get('path', '') and not state.get('composer_visible'):
                reasons.append('thread_without_composer')
            record.update(state=state, anomalies=reasons)
            previous = state
            failures = 0
            RECOVERY_REQUEST.unlink(missing_ok=True)
        except Exception as exc:
            failures += 1
            record.update(error=type(exc).__name__, anomalies=['diagnostic_read_failed'], failure_streak=failures)
            # O monitor não reinicia processos: solicita ao vigia de sistema
            # uma única recuperação após três leituras seguidas sem resposta.
            # Assim uma troca de página transitória não destrói a sessão.
            if failures >= 3:
                RECOVERY_REQUEST.write_text(json.dumps({
                    'at': record['at'], 'reason': 'three_consecutive_read_failures', 'failure_streak': failures,
                }), encoding='utf-8')
        latest = ROOT / 'latest.json'
        temporary = ROOT / 'latest.tmp'
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        temporary.replace(latest)
        log = ROOT / 'browser-events.jsonl'
        if log.exists() and log.stat().st_size > 5_000_000:
            log.replace(ROOT / 'browser-events.previous.jsonl')
        with log.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        if record.get('anomalies'):
            print(json.dumps(record, ensure_ascii=False), flush=True)
        # Mantém visibilidade de transições sem competir com o ciclo comercial.
        time.sleep(10)


if __name__ == '__main__':
    main()
