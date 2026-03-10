from __future__ import annotations

import re
from collections import defaultdict

from schemas import RouteDecision, WorkspaceSnapshot
from template_catalog import TemplateCatalog


ARTIFACT_KEYWORDS = {
    "proposal": ["proposal", "pitch", "bid", "rfp", "response", "solution proposal"],
    "approach_note": ["approach note", "functional note", "change note", "ba note"],
    "high_level_solution": ["high level solution", "hld", "solution overview", "architecture note"],
    "effort_estimate": ["estimate", "estimation", "effort", "sizing", "man-days", "efforting"],
    "diagram_architecture": ["architecture diagram", "architecture block diagram", "block diagram", "system diagram"],
    "diagram_process_flow": ["process flow", "workflow", "flow diagram", "process diagram", "journey flow"],
}

DOMAIN_KEYWORDS = {
    "frontend": ["frontend", "ui", "ux", "screen", "react", "angular", "vue", "web app", "portal"],
    "backend": ["backend", "service", "microservice", "api", "database", "batch", "scheduler"],
    "crm": ["crm", "siebel", "salesforce", "service request", "campaign", "lead", "customer"],
    "mobility": ["mobility", "mobile", "android", "ios", "dealer app", "field app"],
    "integration": ["integration", "interface", "api", "middleware", "sap", "dms", "etl", "web service"],
    "analytics": ["analytics", "report", "dashboard", "bi", "warehouse", "olap"],
    "data_platform": ["data", "lake", "warehouse", "platform", "migration"],
}


def _score_keywords(text_value: str, keywords: dict[str, list[str]]) -> dict[str, float]:
    normalized = text_value.lower()
    scores = defaultdict(float)
    for label, terms in keywords.items():
        for term in terms:
            if term in normalized:
                scores[label] += 1.0
    return dict(scores)


def _normalize_domain(domain_hint: str) -> str:
    normalized = domain_hint.strip().lower()
    if normalized in {"auto-detect", "", "generic enterprise app"}:
        return "generic"
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


class IntentRouter:
    def __init__(self, catalog: TemplateCatalog):
        self.catalog = catalog

    def infer_domain(self, workspace: WorkspaceSnapshot) -> tuple[str, float]:
        domain = _normalize_domain(workspace.domain_hint)
        application_scores = _score_keywords(workspace.application_name.lower(), DOMAIN_KEYWORDS)
        module_scores = _score_keywords(workspace.module_name.lower(), DOMAIN_KEYWORDS)
        business_scores = _score_keywords(workspace.business_context.lower(), DOMAIN_KEYWORDS)
        document_scores = _score_keywords(workspace.combined_context[:4000].lower(), DOMAIN_KEYWORDS)
        domain_scores = defaultdict(float)
        for label, score in application_scores.items():
            domain_scores[label] += score * 2.4
        for label, score in module_scores.items():
            domain_scores[label] += score * 1.4
        for label, score in business_scores.items():
            domain_scores[label] += score * 1.2
        for label, score in document_scores.items():
            domain_scores[label] += score * 0.8
        if domain != "generic":
            return domain, 0.72
        if domain_scores:
            best_domain = max(domain_scores, key=domain_scores.get)
            return best_domain, min(0.55 + domain_scores[best_domain] * 0.08, 0.9)
        return "generic", 0.35

    def route(
        self,
        request_text: str,
        workspace: WorkspaceSnapshot,
        context_matches: list[dict] | None = None,
    ) -> RouteDecision:
        request_lower = request_text.lower()
        artifact_scores = _score_keywords(request_lower, ARTIFACT_KEYWORDS)
        combined_context = "\n".join(
            [
                request_text,
                workspace.business_context,
                workspace.application_name,
                workspace.module_name,
                workspace.summary,
                workspace.combined_context[:4000],
            ]
        )

        artifact_type = "approach_note"
        intent = "functional"
        confidence = 0.45
        rationale_parts: list[str] = []

        if artifact_scores:
            best_artifact = max(artifact_scores, key=artifact_scores.get)
            score = artifact_scores[best_artifact]
            confidence = min(0.55 + score * 0.12, 0.95)
            if best_artifact.startswith("diagram_"):
                artifact_type = "diagram"
                intent = "architecture_diagram" if best_artifact.endswith("architecture") else "process_flow"
            else:
                artifact_type = best_artifact
                intent = {
                    "proposal": "presales",
                    "approach_note": "functional",
                    "high_level_solution": "architecture",
                    "effort_estimate": "estimation",
                }[best_artifact]
            rationale_parts.append(f"Request keywords point to `{artifact_type}`.")
        else:
            rationale_parts.append("No strong artifact keyword found, defaulting to functional approach note.")

        domain, domain_confidence = self.infer_domain(workspace)
        if domain != "generic" and _normalize_domain(workspace.domain_hint) != "generic":
            rationale_parts.append(f"Using workspace domain hint `{workspace.domain_hint}`.")
            confidence = min(confidence + 0.05, 0.95)
        elif domain != "generic":
            rationale_parts.append(f"Context keywords suggest `{domain}` domain.")
            confidence = min(confidence + domain_confidence * 0.1, 0.95)
        else:
            rationale_parts.append("Falling back to generic domain.")

        candidates = self.catalog.find_candidates(artifact_type, domain, intent)
        template_id = candidates[0].id if candidates else self.catalog.find_candidates(artifact_type, "generic", intent)[0].id
        if candidates and candidates[0].domain == "generic" and domain != "generic":
            rationale_parts.append("Using generic template family because a domain-specific family is not available yet.")
        else:
            rationale_parts.append(f"Selected template family `{template_id}`.")

        missing_context: list[str] = []
        if not workspace.application_name:
            missing_context.append("Application / platform name")
        if not workspace.module_name:
            missing_context.append("Module or capability in scope")
        if len(workspace.probe_history) < 2:
            missing_context.append("Clarified end-to-end user flow")

        if context_matches:
            top_match = context_matches[0]
            rationale_parts.append(
                "Found similar prior context"
                f" `{top_match['name']}` with similarity {top_match['similarity']}."
            )
            confidence = min(confidence + 0.05, 0.95)

        return RouteDecision(
            artifact_type=artifact_type,
            domain=domain,
            intent=intent,
            rationale=" ".join(rationale_parts),
            confidence=round(confidence, 2),
            template_family_id=template_id,
            missing_context=missing_context,
            context_matches=context_matches or [],
        )
