import tempfile
import unittest
from pathlib import Path
from core.memory import Memory
from core.sales_intelligence import SalesIntelligence

class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.memory=Memory(Path(self.temp.name)/'test.db')
        self.engine=SalesIntelligence(self.memory)
    def tearDown(self):
        self.memory.close();self.temp.cleanup()
    def test_reimport_preserves_timestamps_and_no_duplicates(self):
        messages=[{'id':'1','role':'assistant','text':'Quer conhecer os planos?','created_at':'2026-01-01T12:00:00+00:00'},{'id':'2','role':'user','text':'Qual o preço para contratar hoje?','created_at':'2026-01-01T12:01:00+00:00'}]
        first=self.engine.import_thread('a','t','@lead',messages)
        second=self.engine.import_thread('a','t','@lead',messages)
        self.assertEqual(first['lead_id'],second['lead_id']);self.assertEqual(second['inserted'],0)
        self.assertEqual(len(self.memory.list_conversations(first['lead_id'])),2)
        self.assertEqual(self.memory.get_lead_detail(first['lead_id'])['stage'],'hot')
        stat=self.engine.analytics()[0]
        self.assertEqual(stat['reply_rate'],1);self.assertEqual(stat['median_reply_seconds'],60)
        self.assertIsNone(stat['time_saved_seconds'])
    def test_accounts_are_isolated(self):
        message=[{'id':'same','role':'user','text':'Olá','created_at':'2026-01-01T12:00:00Z'}]
        a=self.engine.import_thread('a','thread','lead',message)
        b=self.engine.import_thread('b','thread','lead',message)
        self.assertNotEqual(a['lead_id'],b['lead_id'])
    def test_rag_updates_and_excludes_project_notes(self):
        self.engine.document('product','Plano do ERP','ERP inclui agenda e prontuário.','product')
        self.engine.document('internal','Decisões ERP','ERP custa um valor antigo.','project')
        self.engine.document('product','Plano do ERP','ERP inclui agenda e relatórios.','product')
        hits=self.engine.retrieve('ERP agenda')
        self.assertEqual(len(hits),1);self.assertIn('relatórios',hits[0]['text'])
    def test_credentials_are_rejected(self):
        with self.assertRaises(ValueError):self.engine.document('secret','Config','access_token=abc123')

if __name__=='__main__':unittest.main()
