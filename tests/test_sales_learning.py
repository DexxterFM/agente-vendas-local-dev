import tempfile
import unittest
from pathlib import Path
from core.memory import Memory
from core.sales_learning import SalesLearning
from core.sales_intelligence import SalesIntelligence

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.memory=Memory(Path(self.temp.name)/'test.db');self.learning=SalesLearning(self.memory)
    def tearDown(self):
        self.memory.close();self.temp.cleanup()
    def test_unknown_is_not_a_failure(self):
        lead=self.memory.add_lead('Contato')
        self.learning.trial(lead,'descoberta','pergunta contextual','msg1')
        row=self.learning.probabilities('descoberta')[0]
        self.assertEqual(row['response_n'],0)
        self.learning.outcome('msg1',True,None)
        row=self.learning.probabilities('descoberta')[0]
        self.assertEqual(row['response_n'],1);self.assertEqual(row['conversion_n'],0)
        self.assertAlmostEqual(row['response_probability'],2/3)
        self.learning.trial(lead,'descoberta','pergunta contextual','msg1')
        self.assertEqual(self.learning.probabilities('descoberta')[0]['response_n'],1)
    def test_research_is_retrievable(self):
        self.learning.research('Venda consultiva','Pergunte sobre a dificuldade antes de apresentar a solução.','Autor','https://example.com','Descoberta')
        self.assertEqual(len(self.learning.research()),1)
        self.assertEqual(SalesIntelligence(self.memory).retrieve('dificuldade solução')[0]['category'],'playbook')
    def test_personality_version_and_installation(self):
        first=self.learning.personality({'tone':'objetivo'})
        second=self.learning.personality({'tone':'acolhedor'})
        self.assertGreater(second['id'],first['id'])
        with self.assertRaises(ValueError):self.learning.installation('http://example.com')
        self.learning.installation('https://example.com/instalar','Abrir instalador')
        self.assertEqual(self.learning.installation()['steps'],'Abrir instalador')
