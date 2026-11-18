import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.desktop_rpc import execute
from core.activation_flow import ActivationFlow, ActivationRequest, _validate_cnpj, _validate_email, _hash_password
from core.memory import Memory


class ActivationFlowValidationTests(unittest.TestCase):
    def test_validate_cnpj_valid(self):
        self.assertTrue(_validate_cnpj("11.222.333/0001-81"))
        self.assertTrue(_validate_cnpj("11222333000181"))

    def test_validate_cnpj_invalid(self):
        self.assertFalse(_validate_cnpj(""))
        self.assertFalse(_validate_cnpj("11.111.111/1111-11"))
        self.assertFalse(_validate_cnpj("00.000.000/0000-00"))
        self.assertFalse(_validate_cnpj("123"))

    def test_validate_email(self):
        self.assertTrue(_validate_email("clinica@exemplo.com"))
        self.assertFalse(_validate_email(""))
        self.assertFalse(_validate_email("semaroiba"))

    def test_hash_password(self):
        h = _hash_password("senha123")
        self.assertTrue(h.startswith("pbkdf2_sha256$"))


class ActivationFlowRegisterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "agent.sqlite3"

    def tearDown(self):
        self.folder.cleanup()

    def _memory(self):
        return Memory(self.db)

    def test_register_success_activates_trial(self):
        with self._memory() as memory:
            flow = ActivationFlow(memory)
            req = ActivationRequest(
                company_name="Clínica Teste",
                cnpj="11.222.333/0001-81",
                email="clinica@exemplo.com",
                password="senha123",
                phone="(11) 99999-9999",
                plan="clinic_multi",
            )
            result = flow.register(req)
        self.assertTrue(result.ok)
        self.assertTrue(result.activation_code.startswith("ACT"))
        self.assertEqual(result.company_name, "Clínica Teste")
        self.assertEqual(result.cnpj, "11222333000181")
        self.assertEqual(result.email, "clinica@exemplo.com")
        self.assertEqual(result.plan, "clinic_multi")
        self.assertTrue(result.trial_ends_at)
        self.assertIn("3 meses", result.message)

    def test_register_duplicate_cnpj_rejected(self):
        with self._memory() as memory:
            flow = ActivationFlow(memory)
            req = ActivationRequest(
                company_name="Clínica A", cnpj="11.222.333/0001-81",
                email="a@exemplo.com", password="senha123", plan="clinic_multi",
            )
            flow.register(req)
            req2 = ActivationRequest(
                company_name="Clínica B", cnpj="11.222.333/0001-81",
                email="b@exemplo.com", password="senha123", plan="clinic_multi",
            )
            result = flow.register(req2)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "duplicate")

    def test_register_duplicate_email_rejected(self):
        with self._memory() as memory:
            flow = ActivationFlow(memory)
            req = ActivationRequest(
                company_name="Clínica A", cnpj="11.222.333/0001-81",
                email="a@exemplo.com", password="senha123", plan="clinic_multi",
            )
            flow.register(req)
            req2 = ActivationRequest(
                company_name="Clínica B", cnpj="12.345.678/0001-95",
                email="a@exemplo.com", password="senha123", plan="clinic_multi",
            )
            result = flow.register(req2)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "duplicate")

    def test_register_invalid_cnpj(self):
        with self._memory() as memory:
            flow = ActivationFlow(memory)
            req = ActivationRequest(
                company_name="X", cnpj="00.000.000/0000-00",
                email="x@exemplo.com", password="senha123", plan="clinic_multi",
            )
            result = flow.register(req)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "invalid_cnpj")

    def test_register_weak_password(self):
        with self._memory() as memory:
            flow = ActivationFlow(memory)
            req = ActivationRequest(
                company_name="X", cnpj="11.222.333/0001-81",
                email="x@exemplo.com", password="123", plan="clinic_multi",
            )
            result = flow.register(req)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "weak_password")

    def test_status_lookup(self):
        with self._memory() as memory:
            flow = ActivationFlow(memory)
            req = ActivationRequest(
                company_name="Clínica Status", cnpj="11.222.333/0001-81",
                email="status@exemplo.com", password="senha123", plan="clinic_multi",
            )
            reg = flow.register(req)
            st = flow.status(activation_code=reg.activation_code)
        self.assertIsNotNone(st)
        self.assertEqual(st["company_name"], "Clínica Status")
        self.assertEqual(st["status"], "provisioned")

    def test_status_not_found(self):
        with self._memory() as memory:
            flow = ActivationFlow(memory)
            self.assertIsNone(flow.status(activation_code="ACTnonexistent"))


class ActivationRPCTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "agent.sqlite3"

    def tearDown(self):
        self.folder.cleanup()

    def test_activation_config_rpc(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            result = execute("activationConfig", {})
        self.assertIn("clinic_link", result)
        self.assertIn("professional_link", result)
        self.assertEqual(result["months_free"], 3)
        self.assertTrue(any(f["id"] == "cnpj" for f in result["fields"]))
        self.assertTrue(any(f["id"] == "email" for f in result["fields"]))
        self.assertTrue(any(f["id"] == "password" for f in result["fields"]))

    def test_activation_register_rpc(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            result = execute("activationRegister", {
                "company_name": "Clínica RPC",
                "cnpj": "11.222.333/0001-81",
                "email": "rpc@exemplo.com",
                "password": "senha123",
                "plan": "clinic_multi",
            })
        self.assertTrue(result["ok"])
        self.assertTrue(result["activation_code"].startswith("ACT"))
        self.assertTrue(result["trial_ends_at"])

    def test_activation_status_rpc(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            reg = execute("activationRegister", {
                "company_name": "Clínica Status RPC",
                "cnpj": "11.222.333/0001-81",
                "email": "statusrpc@exemplo.com",
                "password": "senha123",
                "plan": "clinic_multi",
            })
            st = execute("activationStatus", {"activation_code": reg["activation_code"]})
        self.assertIsNotNone(st)
        self.assertEqual(st["company_name"], "Clínica Status RPC")
        self.assertEqual(st["status"], "provisioned")


if __name__ == "__main__":
    unittest.main()
