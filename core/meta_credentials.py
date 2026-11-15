"""Credenciais da conexão Meta pertencentes ao agente local.

O token pode vir do .env (instalação automatizada) ou da memória local da
aplicação (configuração feita pelo operador). Nenhum dado é enviado ao
PostFlow.
"""
from __future__ import annotations
import json, os, secrets, urllib.parse, urllib.request

SCOPES = ('instagram_business_basic','instagram_business_manage_messages','instagram_business_manage_comments','instagram_business_manage_insights')

def values(memory):
    environment_account=(os.getenv('IG_BUSINESS_ACCOUNT_ID','') or os.getenv('INSTAGRAM_BUSINESS_ACCOUNT_ID','')).strip()
    environment_token=(os.getenv('INSTAGRAM_ACCESS_TOKEN','') or os.getenv('PAGE_ACCESS_TOKEN','')).strip()
    environment_version=os.getenv('META_GRAPH_VERSION','').strip()
    # No VPS o cofre de EnvironmentFile é a fonte rotacionável. Evita que um
    # token histórico do SQLite vença uma credencial recém-atualizada. O app
    # desktop mantém o comportamento OAuth local por padrão.
    prefer_environment=os.getenv('SALES_AGENT_PREFER_ENV_CREDENTIALS','').strip().lower() in {'1','true','yes'}
    if prefer_environment:
        account=(environment_account or memory.get_setting('meta.account_id','')).strip()
        token=(environment_token or memory.get_setting('meta.access_token','')).strip()
        version=(environment_version or memory.get_setting('meta.graph_version','') or 'v23.0').strip()
    else:
        account=(memory.get_setting('meta.account_id','') or environment_account).strip()
        token=(memory.get_setting('meta.access_token','') or environment_token).strip()
        version=(memory.get_setting('meta.graph_version','') or environment_version or 'v23.0').strip()
    return account,token,version

def authorization_url(memory):
    app_id=(os.getenv('INSTAGRAM_APP_ID','') or os.getenv('META_APP_ID','')).strip()
    redirect=os.getenv('META_REDIRECT_URI','http://127.0.0.1:8765/meta/callback').strip()
    if not app_id: raise ValueError('Configure INSTAGRAM_APP_ID no .env do agente')
    state=secrets.token_urlsafe(24); memory.set_setting('meta.oauth_state',state)
    q=urllib.parse.urlencode({'client_id':app_id,'redirect_uri':redirect,'response_type':'code','scope':','.join(SCOPES),'state':state})
    return {'url':'https://www.instagram.com/oauth/authorize?'+q,'redirect_uri':redirect,'state':state}

def exchange_code(memory, code, state=''):
    expected=memory.get_setting('meta.oauth_state','')
    if not code or (state and expected and state!=expected): raise ValueError('Estado OAuth Meta inválido')
    app_id=(os.getenv('INSTAGRAM_APP_ID','') or os.getenv('META_APP_ID','')).strip(); secret=os.getenv('INSTAGRAM_APP_SECRET','').strip()
    redirect=os.getenv('META_REDIRECT_URI','http://127.0.0.1:8765/meta/callback').strip()
    if not app_id or not secret: raise ValueError('Configure INSTAGRAM_APP_ID e INSTAGRAM_APP_SECRET no .env do agente')
    form=urllib.parse.urlencode({'client_id':app_id,'client_secret':secret,'grant_type':'authorization_code','redirect_uri':redirect,'code':code}).encode()
    req=urllib.request.Request('https://api.instagram.com/oauth/access_token',data=form,headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')
    with urllib.request.urlopen(req,timeout=20) as response: short=json.load(response)
    short_token=str(short.get('access_token','')); user_id=str(short.get('user_id',''))
    if not short_token or not user_id.isdigit(): raise ValueError('Meta não retornou uma credencial válida')
    query=urllib.parse.urlencode({'grant_type':'ig_exchange_token','client_secret':secret,'access_token':short_token})
    with urllib.request.urlopen('https://graph.instagram.com/access_token?'+query,timeout=20) as response: long=json.load(response)
    token=str(long.get('access_token','')); expires=int(long.get('expires_in',0) or 0)
    if not token or expires<=0: raise ValueError('Meta não retornou o token de longa duração')
    memory.set_setting('meta.access_token',token); memory.set_setting('meta.account_id',user_id); memory.set_setting('meta.token_expires_at',str(expires)); memory.set_setting('meta.oauth_state','')
    return {'connected':True,'account_id':user_id,'expires_in':expires}
