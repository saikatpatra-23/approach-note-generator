from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from schemas import WorkspaceSnapshot
from workspace_store import WorkspaceStore


class WorkspaceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="workspace_store_"))
        self.store = WorkspaceStore(root=self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_similar_prefers_same_app_and_module(self) -> None:
        prior = WorkspaceSnapshot(
            id="old1",
            name="Existing Mobility Lead Flow",
            business_context="Mobile lead capture with approval flow.",
            application_name="Dealer App",
            module_name="Lead Capture",
            audience="Business Stakeholders",
            domain_hint="Mobility",
            output_preference="Balanced detail",
            summary="Lead capture flow in dealer app.",
        )
        current = WorkspaceSnapshot(
            id="new1",
            name="New Mobility Lead Flow",
            business_context="Need the latest dealer app lead capture journey.",
            application_name="Dealer App",
            module_name="Lead Capture",
            audience="Business Stakeholders",
            domain_hint="Auto-detect",
            output_preference="Balanced detail",
            summary="Lead capture flow for dealer app.",
        )
        self.store.save(prior)
        matches = self.store.find_similar(current, limit=1)
        self.assertEqual(matches[0]["workspace_id"], "old1")
        self.assertGreater(matches[0]["similarity"], 0.2)


if __name__ == "__main__":
    unittest.main()
