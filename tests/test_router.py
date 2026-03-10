from __future__ import annotations

import unittest

from intent_router import IntentRouter
from schemas import WorkspaceSnapshot
from template_catalog import TemplateCatalog


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = IntentRouter(TemplateCatalog())

    def _workspace(self) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(
            id="ws1",
            name="Dealer App Opportunity",
            business_context="Need a mobile app flow for dealer lead capture with backend API integration.",
            application_name="Dealer Mobility App",
            module_name="Lead Capture",
            audience="Business Stakeholders",
            domain_hint="Auto-detect",
            output_preference="Balanced detail",
        )

    def test_routes_proposal_requests_to_proposal(self) -> None:
        route = self.router.route("Please generate a proposal for this opportunity.", self._workspace())
        self.assertEqual(route.artifact_type, "proposal")
        self.assertEqual(route.intent, "presales")
        self.assertEqual(route.template_family_id, "proposal_generic_presales")

    def test_routes_approach_note_without_estimation_sections(self) -> None:
        route = self.router.route("Share a functional approach note for this change.", self._workspace())
        self.assertEqual(route.artifact_type, "approach_note")
        self.assertEqual(route.intent, "functional")

    def test_infers_mobility_domain_from_context(self) -> None:
        domain, confidence = self.router.infer_domain(self._workspace())
        self.assertEqual(domain, "mobility")
        self.assertGreater(confidence, 0.5)


if __name__ == "__main__":
    unittest.main()
