from __future__ import annotations

import unittest

from artifact_renderers import build_diagram_svg, build_effort_workbook, build_word_artifact
from schemas import GeneratedArtifact, WorkspaceSnapshot


class RendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = WorkspaceSnapshot(
            id="ws_render",
            name="Portal Upgrade",
            business_context="Upgrade portal journey and integration flow.",
            application_name="React Portal",
            module_name="Lead Management",
            audience="Business Stakeholders",
            domain_hint="Frontend",
            output_preference="Balanced detail",
            summary="Upgrade the lead management flow and associated integrations.",
            inferred_domain="Frontend",
        )

    def test_build_word_artifact(self) -> None:
        artifact = GeneratedArtifact(
            artifact_type="approach_note",
            title="Functional Approach Note - Portal Upgrade",
            template_family_id="approach_note_functional",
            renderer="word",
            payload={
                "background": "Current lead handling is manual.",
                "requirement_statement": "The business requires a guided lead capture journey.",
                "impact_analysis": {
                    "application_areas": [{"area": "Portal", "impact": "Y", "remarks": "UI and APIs"}],
                    "change_dimensions": [{"dimension": "Frontend", "applicable": "Y"}],
                },
                "proposed_solution": "A new guided experience will be introduced.",
            },
            preview_text="Preview",
            rationale="Test",
            confidence=0.8,
        )
        payload = build_word_artifact(artifact, self.workspace)
        self.assertGreater(len(payload), 1000)

    def test_build_effort_workbook(self) -> None:
        artifact = GeneratedArtifact(
            artifact_type="effort_estimate",
            title="Effort Estimate",
            template_family_id="effort_estimation_delivery",
            renderer="excel",
            payload={
                "estimate_summary": "Core UI and API work.",
                "assumptions": ["Requirements stay stable."],
                "work_breakdown": [
                    {
                        "workstream": "Frontend",
                        "activity": "UI changes",
                        "role": "Developer",
                        "effort_days": 4,
                        "remarks": "Includes testing support",
                    }
                ],
                "totals": {"total_effort_days": 4, "recommended_team_shape": "1 dev + 1 QA"},
            },
            preview_text="Preview",
            rationale="Test",
            confidence=0.8,
        )
        payload = build_effort_workbook(artifact, self.workspace)
        self.assertGreater(len(payload), 1000)

    def test_build_diagram_svg(self) -> None:
        artifact = GeneratedArtifact(
            artifact_type="diagram",
            title="Architecture Diagram",
            template_family_id="diagram_architecture",
            renderer="svg",
            payload={
                "title": "Architecture Diagram",
                "objective": "Show the main integration points.",
                "nodes": [
                    {"id": "a", "label": "Portal", "category": "system"},
                    {"id": "b", "label": "API", "category": "service"},
                ],
                "edges": [{"source": "a", "target": "b", "label": "REST"}],
                "notes": ["Authentication handled at the gateway."],
            },
            preview_text="Preview",
            rationale="Test",
            confidence=0.8,
        )
        payload = build_diagram_svg(artifact, self.workspace)
        self.assertIn(b"<svg", payload)


if __name__ == "__main__":
    unittest.main()
