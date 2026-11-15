import json
import os
import re
import urllib.request
from datetime import datetime, timezone

def send_reply(memory,lead_id,text):
    # O PostFlow permanece como caminho principal quando a conexão Meta já
    # está autenticada nele. O Graph direto só é usado como fallback explícito.
    if os.getenv('META_PROVIDER','direct').strip().lower() == 'postflow' and (os.getenv('POSTFLOW_API_TOKEN','').strip() or os.getenv('POSTFLOW_SESSION_COOKIE','').strip()):
        from adapters.postflow import create_reply, approve_reply, send_approved
        item=create_reply(str(memory.get_setting('instagram.thread:'+str(lead_id),'') or lead_id), text)
        item_id=((item.get('item') or {}).get('id') or item.get('id'))
        if not item_id:
            raise ValueError('PostFlow não retornou o item de DM')
        approved=approve_reply(str(item_id), text)
        if approved.get('ok') is False:
            raise ValueError('PostFlow não aprovou a resposta')
        return send_approved(str(item_id))
    target=json.loads(memory.get_setting('instagram.recipient:'+str(lead_id),'{}'))
    from core.meta_credentials import values
    account,token,version=values(memory)
    recipient=str(target.get('recipient',''))
    if not token or target.get('account')!=account or not recipient.isdigit() or not account.isdigit():
        raise ValueError('Conexão Instagram ou destinatário não configurado')
    if not re.fullmatch(r'v\d+\.\d+',version):raise ValueError('Versão Graph inválida')
    row=memory.db.execute("SELECT created_at FROM imported_messages WHERE account=? AND lead_id=? AND role='user' ORDER BY created_at DESC LIMIT 1",(account,lead_id)).fetchone()
    if not row:raise ValueError('Conversa recebida não localizada')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(row[0].replace('Z','+00:00'))).total_seconds()
    if age<0 or age>=86400:raise ValueError('É necessária uma nova mensagem do contato para responder pela API')
    body=json.dumps({'recipient':{'id':recipient},'message':{'text':text}}).encode()
    host='graph.facebook.com' if token.startswith(('EA','IG')) else 'graph.instagram.com'
    request=urllib.request.Request(f'https://{host}/{version}/{account}/messages',data=body,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
