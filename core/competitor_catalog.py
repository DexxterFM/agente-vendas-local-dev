"""Catálogo verificável de concorrentes e recuperação de comparativos."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from core.config import data_root, is_frozen, resource_root


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


class CompetitorCatalog:
    def __init__(self, memory=None, catalog_path: str | Path | None = None):
        self.memory = memory
        self.path = Path(catalog_path) if catalog_path else resource_root() / "research" / "competitor_catalog.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self._validate()

    def _validate(self) -> None:
        if not self.data.get("verified_at") or not self.data.get("erp"):
            raise ValueError("Catálogo de concorrentes incompleto")
        slugs: set[str] = set()
        for entry in self.data.get("competitors", []):
            required = ("slug", "name", "aliases", "pricing", "features", "dossier", "sources", "poster_prompt", "asset")
            if any(not entry.get(key) for key in required):
                raise ValueError(f"Concorrente incompleto: {entry.get('name', '?')}")
            if entry["slug"] in slugs:
                raise ValueError(f"Slug duplicado: {entry['slug']}")
            slugs.add(entry["slug"])
            if not all(str(source.get("url", "")).startswith("https://") for source in entry["sources"]):
                raise ValueError(f"Fonte inválida em {entry['name']}")

    def all(self) -> list[dict]:
        return list(self.data.get("competitors", []))

    def match(self, text: str) -> dict | None:
        haystack = f" {normalize(text)} "
        matches: list[tuple[int, dict]] = []
        for entry in self.all():
            names = [entry["name"], *entry.get("aliases", [])]
            for alias in names:
                needle = normalize(alias)
                if needle and f" {needle} " in haystack:
                    matches.append((len(needle), entry))
                    break
        return max(matches, key=lambda item: item[0])[1] if matches else None

    def dossier_text(self, entry: dict) -> str:
        erp = self.data["erp"]
        lines = [
            f"COMPARATIVO: ERP Clínica TEA x {entry['name']}",
            f"Verificado em: {self.data['verified_at']}",
            f"Posicionamento do concorrente: {entry['positioning']}",
            f"Preço público: {entry['pricing']['summary']}",
            "Funcionalidades publicadas pelo concorrente:",
            *[f"- {item}" for item in entry["features"]],
            "Vantagens documentadas do ERP Clínica TEA para a conversa:",
            *[f"- {item}" for item in entry["erp_advantages"]],
            "Dossiê comercial:",
            entry["dossier"],
            "Perguntas de descoberta:",
            *[f"- {item}" for item in entry["discovery_questions"]],
            "Respostas a objeções:",
            *[f"- {item}" for item in entry["objection_answers"]],
            "Fontes oficiais consultadas:",
            *[f"- {source['title']}: {source['url']} (consulta: {source['checked_at']})" for source in entry["sources"]],
            "Regra: não afirmar que um recurso está ausente no concorrente apenas porque não apareceu na página consultada.",
            "Prompt do pôster:",
            entry["poster_prompt"],
        ]
        lines.extend(["", "BASE DO ERP CLÍNICA TEA:", *[f"- {item}" for item in erp["features"]]])
        return "\n".join(lines)

    def asset_path(self, entry: dict) -> Path:
        bundled = resource_root() / entry["asset"]["path"]
        if not is_frozen():
            return bundled
        # O backend empacotado é executado em uma pasta temporária que some ao
        # fim do processo. Copiamos pôsteres embarcados para o diretório durável
        # do aplicativo e sempre devolvemos esse caminho ao Electron.
        persistent = data_root() / "comparativos" / Path(entry["asset"]["path"]).name
        if bundled.is_file() and not persistent.is_file():
            import shutil
            persistent.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundled, persistent)
        return persistent

    def lookup(self, text: str) -> dict | None:
        entry = self.match(text)
        if not entry:
            return None
        asset = self.asset_path(entry)
        return {
            "slug": entry["slug"],
            "name": entry["name"],
            "pricing": entry["pricing"],
            "dossier": self.dossier_text(entry),
            "poster_prompt": entry["poster_prompt"],
            "asset_path": str(asset),
            "asset_ready": asset.is_file(),
            "sources": entry["sources"],
        }

    def seed_memory(self) -> dict:
        if self.memory is None:
            raise ValueError("Memória não fornecida")
        from core.sales_intelligence import SalesIntelligence

        intelligence = SalesIntelligence(self.memory)
        ids = []
        for entry in self.all():
            ids.append(
                intelligence.document(
                    f"competitor:{entry['slug']}",
                    f"ERP Clínica TEA x {entry['name']}",
                    self.dossier_text(entry),
                    "comparison",
                )
            )
        self.memory.set_setting("competitor.catalog.verified_at", self.data["verified_at"])
        self.memory.set_setting("competitor.catalog.count", str(len(ids)))
        return {"seeded": len(ids), "verified_at": self.data["verified_at"]}

