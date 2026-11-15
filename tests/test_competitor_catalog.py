import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.competitor_catalog import CompetitorCatalog
from core.memory import Memory


class CompetitorCatalogTests(unittest.TestCase):
    def test_catalog_is_detailed_and_sourced(self):
        catalog = CompetitorCatalog()
        self.assertGreaterEqual(len(catalog.all()), 12)
        for entry in catalog.all():
            self.assertGreaterEqual(len(entry["features"]), 4)
            self.assertGreaterEqual(len(entry["erp_advantages"]), 3)
            self.assertGreater(len(entry["dossier"]), 350)
            self.assertIn("1080x1350", entry["poster_prompt"])
            self.assertTrue(all(source["url"].startswith("https://") for source in entry["sources"]))

    def test_alias_matching_is_accent_insensitive(self):
        catalog = CompetitorCatalog()
        self.assertEqual(catalog.match("a clínica usa Clínica Ágil")["slug"], "clinica-agil")
        self.assertEqual(catalog.match("estamos no Ninsaude")["slug"], "ninsaude")
        self.assertIsNone(catalog.match("usamos uma planilha"))

    def test_seed_indexes_every_dossier_in_rag(self):
        with tempfile.TemporaryDirectory() as folder:
            with Memory(Path(folder) / "agent.sqlite3") as memory:
                catalog = CompetitorCatalog(memory)
                result = catalog.seed_memory()
                self.assertEqual(result["seeded"], len(catalog.all()))
                rows = memory.db.execute("select count(*) from rag_documents where source like 'competitor:%'").fetchone()[0]
                self.assertEqual(rows, len(catalog.all()))
                hits = __import__("core.sales_intelligence", fromlist=["SalesIntelligence"]).SalesIntelligence(memory).retrieve("Feegow perfil sensorial", 10)
                self.assertTrue(any(item["source"] == "competitor:feegow" for item in hits))


if __name__ == "__main__":
    unittest.main()
