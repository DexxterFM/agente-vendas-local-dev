"""Fila persistente: prazo mínimo, conversa atualizada e envio sem repetição cega."""
import json
import hashlib
import time
from datetime import datetime, timezone

class ReplyPacing:
    def __init__(self,memory,clock=time.time):
        self.memory=memory;self.db=memory.db;self.clock=clock
        self.db.execute('CREATE TABLE IF NOT EXISTS reply_schedule(action_id INTEGER PRIMARY KEY,lead_id INTEGER,due_at REAL,context_digest TEXT,state TEXT,external_id TEXT)')
        self.db.commit()

    def digest(self,lead_id):
        messages=self.memory.list_conversations(lead_id,100)
        return hashlib.sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest()

    def queue(self,lead_id,text):
        if not self.memory.get_lead_detail(lead_id):raise ValueError('Selecione um lead válido')
        if not text.strip():raise ValueError('Resposta vazia')
        seconds=max(3,min(30,int(self.memory.get_setting('reply.minimum_seconds','7'))))
        # Count the deliberate pause from queuing, even when generation was fast.
        due_at=self.clock()+seconds
        action_id=self.memory.create_pending_action('instagram_dm',{'lead_id':lead_id,'text':text,'not_before':due_at})
        if (self.memory.get_setting('sales.agent.active','false') == 'true'
                and self.memory.get_setting('sales.agent.automatic_replies','false') == 'true'):
            self.memory.decide_pending_action(action_id, True, 'Agente de vendas ativo')
        with self.db:self.db.execute('INSERT INTO reply_schedule VALUES(?,?,?,?,?,NULL)',(action_id,lead_id,due_at,self.digest(lead_id),'waiting'))
        return {'id':action_id,'minimum_seconds':seconds,'not_before':due_at}

    def process(self,sender):
        outcomes=[]
        rows=self.db.execute("SELECT s.action_id,s.lead_id,s.context_digest,p.payload FROM reply_schedule s JOIN pending_actions p ON p.id=s.action_id WHERE s.state='waiting' AND p.status='approved' AND s.due_at<=?",(self.clock(),)).fetchall()
        for action_id,lead_id,digest,payload in rows:
            if self.memory.get_setting('paused:'+str(lead_id),'false')=='true':continue
            if digest!=self.digest(lead_id):
                with self.db:
                    self.db.execute("UPDATE reply_schedule SET state='stale' WHERE action_id=?",(action_id,))
                    self.db.execute("UPDATE pending_actions SET status='stale' WHERE id=?",(action_id,))
                outcomes.append({'id':action_id,'state':'stale'});continue
            with self.db:
                claimed=self.db.execute("UPDATE reply_schedule SET state='sending' WHERE action_id=? AND state='waiting'",(action_id,)).rowcount
            if not claimed:continue
            data=json.loads(payload)
            try:
                result=sender(lead_id,data['text'])
                external_id=result['message_id']
            except Exception:
                # A timeout may mean delivery happened: do not automatically retry.
                with self.db:
                    self.db.execute("UPDATE reply_schedule SET state='needs_check' WHERE action_id=?",(action_id,))
                    self.db.execute("UPDATE pending_actions SET status='needs_check' WHERE id=?",(action_id,))
                outcomes.append({'id':action_id,'state':'needs_check'});continue
            with self.db:
                self.db.execute("UPDATE reply_schedule SET state='sent',external_id=? WHERE action_id=?",(str(external_id),action_id))
                self.db.execute("UPDATE pending_actions SET status='sent' WHERE id=?",(action_id,))
            self.memory.add_conversation(lead_id,'assistant',data['text'])
            outcomes.append({'id':action_id,'state':'sent'})
        return outcomes
