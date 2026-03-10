from __future__ import annotations

import json
from pathlib import Path

from config import TEMPLATE_CATALOG_PATH
from schemas import TemplateFamily


class TemplateCatalog:
    def __init__(self, catalog_path: Path | None = None):
        self.catalog_path = catalog_path or TEMPLATE_CATALOG_PATH
        self._families = self._load()

    def _load(self) -> dict[str, TemplateFamily]:
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        families: dict[str, TemplateFamily] = {}
        for item in raw["template_families"]:
            family = TemplateFamily(**item)
            families[family.id] = family
        return families

    def all(self) -> list[TemplateFamily]:
        return list(self._families.values())

    def get(self, family_id: str) -> TemplateFamily:
        return self._families[family_id]

    def find_candidates(self, artifact_type: str, domain: str, intent: str) -> list[TemplateFamily]:
        exact = [
            family
            for family in self._families.values()
            if family.artifact_type == artifact_type
            and family.intent == intent
            and family.domain == domain
        ]
        if exact:
            return exact

        domain_fallback = [
            family
            for family in self._families.values()
            if family.artifact_type == artifact_type
            and family.intent == intent
            and family.domain in {domain, "generic"}
        ]
        if domain_fallback:
            return domain_fallback

        return [
            family
            for family in self._families.values()
            if family.artifact_type == artifact_type
        ]
