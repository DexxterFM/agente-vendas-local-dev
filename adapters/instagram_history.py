"""Importa as mensagens que a Graph API disponibiliza para a conta autorizada."""
import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error
from core.sales_intelligence import SalesIntelligence

def sync_history(memory):
    from core.meta_credentials import values
    account,token,configured_version=values(memory)
    version=configured_version
    if not account or not token:raise ValueError('Configure o token Instagram e o ID da conta antes de importar.')
    if not account.isdigit() or not __import__('re').fullmatch(r'v\d+\.\d+',version): raise ValueError('Configuração Meta inválida')
    # Tokens issued by the Meta Business/Unified Login flow use the Facebook
    # Graph host; legacy Instagram Login tokens continue to use graph.instagram.com.
    host='https://graph.facebook.com' if token.startswith(('EA','IG')) else 'https://graph.instagram.com'
    def request(path,params):
        url=f'{host}/{version}/{urllib.parse.quote(path,safe="/")}?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req,timeout=25) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            detail=''
            try: detail=json.loads(exc.read().decode('utf-8')).get('error',{}).get('message','')
            except Exception: pass
            retry_after=str(exc.headers.get('Retry-After','')).strip() if exc.headers else ''
            app_usage=str(exc.headers.get('X-App-Usage','')).strip() if exc.headers else ''
            buc_usage=str(exc.headers.get('X-Business-Use-Case-Usage','')).strip() if exc.headers else ''
            hints=[]
            if retry_after: hints.append('retry_after='+retry_after[:30])
            if app_usage: hints.append('app_usage='+app_usage[:240])
            if buc_usage: hints.append('buc_usage='+buc_usage[:240])
            suffix=('; '+'; '.join(hints)) if hints else ''
            raise RuntimeError(f'Meta respondeu HTTP {exc.code}: {detail[:220]}{suffix}; importação pode ser retomada sem duplicar mensagens.') from None
        except urllib.error.URLError:
            raise RuntimeError('Sem conexão com a Meta; tente novamente.') from None
    def pages(path,params):
        seen=set()
        while True:
            payload=request(path,params)
            yield from payload.get('data',[])
            paging=payload.get('paging',{})
            cursor=paging.get('cursors',{}).get('after')
            if not paging.get('next'):break
            if cursor and cursor not in seen:
                seen.add(cursor);params={**params,'after':cursor};continue
            # Algumas respostas Meta trazem apenas o próximo URL. Aceite-o
            # somente no host Graph permitido, sem seguir redirecionamentos
            # arbitrários.
            next_url=paging.get('next','')
            parsed=urllib.parse.urlparse(next_url)
            if parsed.scheme!='https' or parsed.netloc not in {'graph.instagram.com','graph.facebook.com'}:
                raise RuntimeError('Paginação Meta recusada: próximo URL fora do Graph oficial')
            path=parsed.path.lstrip('/'); query=dict(urllib.parse.parse_qsl(parsed.query))
            if not path or not query: raise RuntimeError('Paginação incompleta: cursor ausente ou repetido')
            # O Graph pode devolver a próxima página com uma versão diferente
            # da configurada; remova sempre o prefixo de versão antes de
            # remontar a chamada, evitando /v23/v26/.../messages.
            path=re.sub(r'^v\d+\.\d+/', '', path)
            params=query; request_path=path
    intelligence=SalesIntelligence(memory)
    result={'threads':0,'messages':0,'coverage':'api_partial','account':account,'complete':True}
    max_threads=max(1,min(25,int(os.getenv('META_SYNC_THREAD_LIMIT','10'))))
    for thread in pages(f'{account}/conversations',{'platform':'instagram','fields':'id,participants','limit':50}):
        if result['threads'] >= max_threads: result['complete']=False; break
        # Existing threads must be fetched again: import_thread is idempotent
        # and deduplicates message IDs, while this refresh picks up new DMs.
        participants=thread.get('participants',{}).get('data',[])
        peer=next((p for p in participants if str(p.get('id'))!=account),{})
        messages=[]
        try:
            for item in pages(f"{thread['id']}/messages",{'fields':'id,message,from,created_time','limit':20}):
                messages.append({'id':item['id'],'role':'assistant' if str(item.get('from',{}).get('id'))==account else 'user','text':item.get('message',''),'created_at':item['created_time']})
        except RuntimeError as exc:
            result['complete']=False; result['error']=str(exc); break
        imported=intelligence.import_thread(account,thread['id'],peer.get('username') or peer.get('id') or thread['id'],messages)
        if peer.get('id'):memory.set_setting('instagram.recipient:'+str(imported['lead_id']),json.dumps({'account':account,'recipient':str(peer['id'])}))
        result['threads']+=1;result['messages']+=imported['inserted']
        memory.set_setting('instagram.history_progress',json.dumps(result))
    memory.set_setting('instagram.history_last_sync',json.dumps(result))
    return result
