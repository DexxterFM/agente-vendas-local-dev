import tempfile
import unittest
from pathlib import Path
from core.memory import Memory
from core.reply_pacing import ReplyPacing
from core.sales_learning import SalesLearning

class ReplyPacingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.memory=Memory(Path(self.temp.name)/'test.db')
        self.lead=self.memory.add_lead('Teste');self.time=100
        self.queue=ReplyPacing(self.memory,lambda:self.time)
    def tearDown(self):self.memory.close();self.temp.cleanup()
    def approved(self):
        item=self.queue.queue(self.lead,'Resposta contextual')
        self.memory.decide_pending_action(item['id'],True)
        return item
    def test_no_early_send_and_no_duplicate(self):
        item=self.approved();sent=[]
        def sender(*args):sent.append(args);return {'message_id':'one'}
        self.queue.process(sender);self.assertEqual(sent,[])
        self.time=item['not_before'];self.queue.process(sender);self.queue.process(sender)
        self.assertEqual(len(sent),1)
    def test_new_inbound_invalidates_reply(self):
        item=self.approved();self.memory.add_conversation(self.lead,'user','Mais uma dúvida')
        self.time=item['not_before'];self.assertEqual(self.queue.process(lambda *a:self.fail('Não enviar'))[0]['state'],'stale')
    def test_ambiguous_failure_not_retried(self):
        item=self.approved();self.time=item['not_before'];calls=[]
        def sender(*args):calls.append(1);raise TimeoutError()
        self.queue.process(sender);self.queue.process(sender);self.assertEqual(len(calls),1)
    def test_research_seed_idempotent(self):
        learning=SalesLearning(self.memory)
        self.assertEqual(learning.seed_research()['added'],6)
        self.assertEqual(learning.seed_research()['added'],0)

if __name__=='__main__':unittest.main()
