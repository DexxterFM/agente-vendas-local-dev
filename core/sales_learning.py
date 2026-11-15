"""Biblioteca comercial, personalidade versionada e estimativas por resultados."""
import json
from datetime import datetime, timezone

DEFAULT_PERSONALITY = {
    'name':'Denis',
    'location':'Porto Alegre/RS',
    'tone':'vendedor experiente, simpático, natural, consultivo e objetivo',
    'detail':'adaptar à dúvida do cliente e usar fatos do RAG',
    'questions':'uma pergunta útil por vez',
    'objections':'acolher, investigar e argumentar; não desistir na primeira objeção',
    'closing':'próximo passo claro para testar por 3 meses',
    'emojis':'usar com moderação apenas 😊 👏 👍 ❤️',
    'persistence':'continuar educadamente enquanto houver diálogo; encerrar somente após recusa explícita de contato',
}

class SalesLearning:
    def __init__(self,memory):
        self.memory=memory
        self.db=memory.db
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sales_research(id INTEGER PRIMARY KEY,title TEXT NOT NULL,author TEXT,source TEXT,summary TEXT NOT NULL,method TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS personality_versions(id INTEGER PRIMARY KEY,profile TEXT NOT NULL,reason TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sales_trials(id INTEGER PRIMARY KEY,lead_id INTEGER NOT NULL,context TEXT NOT NULL,method TEXT NOT NULL,personality_id INTEGER,response_id TEXT UNIQUE NOT NULL,responded INTEGER,converted INTEGER,created_at TEXT NOT NULL);
        ''')

    def seed_research(self):
        from core.config import resource_root
        path=resource_root()/'research'/'sales_research.json'
        if not path.is_file():return {'added':0,'available':False}
        added=0
        for entry in json.loads(path.read_text(encoding='utf-8')):
            if not self.db.execute('SELECT 1 FROM sales_research WHERE source=?',(entry['source'],)).fetchone():
                self.research(**entry);added+=1
        return {'added':added,'available':True}

    def research(self,title=None,summary=None,author='',source='',method=''):
        if title is None:
            cursor=self.db.execute('SELECT id,title,author,source,summary,method,created_at FROM sales_research ORDER BY id DESC')
            return [dict(zip([col[0] for col in cursor.description],row)) for row in cursor.fetchall()]
        if not title.strip() or not summary.strip():raise ValueError('Informe título e resumo da pesquisa')
        from core.sales_intelligence import SalesIntelligence
        with self.db:
            cursor=self.db.execute('INSERT INTO sales_research(title,author,source,summary,method,created_at) VALUES(?,?,?,?,?,?)',(title,author,source,summary,method,datetime.now(timezone.utc).isoformat()))
            entry_id=cursor.lastrowid
        SalesIntelligence(self.memory).document('research:'+str(entry_id),title,f'Autor: {author}\nFonte: {source}\nMétodo: {method}\nResumo e aplicação: {summary}','playbook')
        return entry_id

    def personality(self,profile=None,reason='Configuração comercial'):
        if profile is not None:
            allowed={'name','location','tone','detail','greeting','questions','objections','closing','emojis','persistence'}
            if not isinstance(profile,dict) or set(profile)-allowed:raise ValueError('Campos de personalidade inválidos')
            with self.db:
                self.db.execute('INSERT INTO personality_versions(profile,reason,created_at) VALUES(?,?,?)',(json.dumps(profile,ensure_ascii=False),reason,datetime.now(timezone.utc).isoformat()))
        row=self.db.execute('SELECT id,profile FROM personality_versions ORDER BY id DESC LIMIT 1').fetchone()
        if row:
            return {'id':row[0],'profile':{**DEFAULT_PERSONALITY,**json.loads(row[1])}}
        return {'id':None,'profile':dict(DEFAULT_PERSONALITY)}

    def trial(self,lead_id,context,method,response_id):
        if not self.memory.get_lead_detail(int(lead_id)):raise ValueError('Lead inexistente')
        if not context.strip() or not method.strip() or not response_id.strip():raise ValueError('Informe contexto, método e ID da mensagem enviada')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO sales_trials(lead_id,context,method,personality_id,response_id,created_at) VALUES(?,?,?,?,?,?)',(lead_id,context,method,self.personality()['id'],response_id,datetime.now(timezone.utc).isoformat()))
        return True

    def outcome(self,response_id,responded=None,converted=None):
        if not self.db.execute('SELECT 1 FROM sales_trials WHERE response_id=?',(response_id,)).fetchone():raise ValueError('Interação não registrada')
        if responded not in (None,True,False) or converted not in (None,True,False):raise ValueError('Resultado inválido')
        with self.db:
            self.db.execute('UPDATE sales_trials SET responded=COALESCE(?,responded),converted=COALESCE(?,converted) WHERE response_id=?',(responded,converted,response_id))
        return True

    def probabilities(self,context):
        # Beta(1,1): resultados desconhecidos não contam como falha.
        rows=self.db.execute('SELECT method,responded,converted FROM sales_trials WHERE context=?',(context,)).fetchall()
        groups={}
        for method,responded,converted in rows:
            stat=groups.setdefault(method,{'method':method,'response_success':0,'response_n':0,'conversion_success':0,'conversion_n':0})
            for kind,value in [('response',responded),('conversion',converted)]:
                if value is not None:stat[kind+'_n']+=1;stat[kind+'_success']+=int(value)
        for stat in groups.values():
            for kind in ('response','conversion'):
                n=stat[kind+'_n'];success=stat[kind+'_success']
                stat[kind+'_probability']=(success+1)/(n+2)
            stat['evidence']='amostra inicial' if stat['response_n']<20 else 'estimativa observacional'
        return sorted(groups.values(),key=lambda stat:-stat['response_probability'])

    def installation(self,url=None,steps=None):
        if url is not None:
            from urllib.parse import urlparse
            parsed=urlparse(url)
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Informe um link HTTPS válido')
            self.memory.set_setting('sales.installation',json.dumps({'url':url,'steps':steps or ''},ensure_ascii=False))
        return json.loads(self.memory.get_setting('sales.installation','{}'))

    def context(self,lead_id,trail):
        self.seed_research()
        probabilities=self.probabilities(trail)
        preferred=next((r for r in probabilities if r['response_n']>=20),None)
        if preferred:self.memory.set_setting('sales.learned_strategy:'+trail,json.dumps(preferred,ensure_ascii=False))
        return {'personality':self.personality(),'installation':self.installation(),'probabilities':probabilities,'learned_strategy':preferred,'guidance':'Use as probabilidades apenas como estimativas com tamanho da amostra; não prometa conversão. Pesquisas são referências, não provas. Argumente sobre migração com necessidades reais e fontes documentadas; não invente desvantagens do concorrente. Se o cliente pedir instalação, forneça o link cadastrado, um passo por vez, e confirme onde ele está antes de seguir. Se faltar link, informe que precisa ser configurado.'}
