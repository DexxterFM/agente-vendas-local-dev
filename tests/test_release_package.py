"""Contratos do pacote instalável de operação do painel."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleasePackageTests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        path = ROOT / relative
        self.assertTrue(path.exists(), f"arquivo ausente: {relative}")
        return path.read_text(encoding="utf-8")

    def test_default_remote_config_is_neutral(self):
        config = json.loads(self._read("desktop/remote-control.default.json"))
        self.assertFalse(config["enabled"])
        self.assertEqual("", config["sshHost"].strip())
        self.assertEqual(8787, config["localPort"])
        self.assertEqual(8787, config["remotePort"])

    def test_remote_build_copies_neutral_config(self):
        source = self._read("desktop/build-remote.cjs")
        self.assertIn("remote-control.default.json", source)
        self.assertIn("'resources','remote-control.json'", source)
        self.assertIn("'remote-control.default.json'", source)
        self.assertNotIn("'desktop','remote-control.json'", source)
        self.assertFalse((ROOT / "desktop/remote-control.json").exists())
        self.assertNotIn("erpclinicatea-vps", self._read("operar_agente_vps.ps1"))

    def test_package_json_exposes_remote_build(self):
        manifest = json.loads(self._read("package.json"))
        self.assertIn("desktop:build:remote", manifest["scripts"])

    def test_remote_installer_ships_operation_scripts(self):
        source = self._read("installer-remote.iss")
        self.assertIn("scripts\\configurar-conexao.ps1", source)
        self.assertIn("scripts\\operar-painel.ps1", source)
        self.assertIn("OPERACAO.md", source)
        self.assertIn("Configurar conexao VPS", source)
        self.assertNotIn("erpclinicatea-vps", source)

    def test_configuration_script_writes_user_profile(self):
        source = self._read("scripts/configurar-conexao.ps1")
        self.assertIn("AgenteVendasControleVPS", source)
        self.assertIn("remote-control.json", source)
        self.assertIn("SshHost", source)
        self.assertIn("Test-SshTarget", source)
        self.assertIn("BatchMode=yes", source)

    def test_operation_script_exposes_all_actions(self):
        source = self._read("scripts/operar-painel.ps1")
        for action in ("open", "configure", "status", "logs", "stop", "start"):
            self.assertIn(action, source)
        self.assertIn("operar-painel.ps1 -Action status", self._read("OPERACAO.md"))

    def test_release_script_builds_both_panels_and_zip(self):
        source = self._read("build-release.ps1")
        self.assertIn("desktop:build:remote", source)
        self.assertIn("AgenteVendasControleVPS-Setup.exe", source)
        self.assertIn("AgenteVendasLocal-Setup.exe", source)
        self.assertIn("ZipArchive", source)
        self.assertNotIn("Compress-Archive", source)
        self.assertIn("SkipTests", source)
        self.assertIn("version.iss", source)

    def test_installers_share_single_version_source(self):
        self.assertIn("#define AppVersion", self._read("version.iss"))
        self.assertIn('#include "version.iss"', self._read("installer.iss"))
        self.assertIn('#include "version.iss"', self._read("installer-remote.iss"))

    def test_local_launcher_accepts_browseros_overrides(self):
        source = self._read("run_local.ps1")
        self.assertIn("BROWSEROS_SERVER", source)
        self.assertIn("BROWSEROS_CONFIG", source)

    def test_operation_guide_covers_lifecycle(self):
        guide = self._read("OPERACAO.md")
        for section in (
            "## 1. Pré-requisitos",
            "## 2. Instalação",
            "## 3. Configurar a conexão",
            "## 4. Operação diária",
            "## 5. Logs e arquivos",
            "## 6. Atualização",
            "## 8. Solução de problemas",
        ):
            self.assertIn(section, guide)
        self.assertNotIn("erpclinicatea-vps", guide)


if __name__ == "__main__":
    unittest.main()
