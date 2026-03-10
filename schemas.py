from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ArtifactType(str, Enum):
    PROPOSAL = "proposal"
    APPROACH_NOTE = "approach_note"
    HIGH_LEVEL_SOLUTION = "high_level_solution"
    EFFORT_ESTIMATE = "effort_estimate"
    DIAGRAM = "diagram"


ARTIFACT_LABELS = {
    ArtifactType.PROPOSAL: "Proposal",
    ArtifactType.APPROACH_NOTE: "Functional Approach Note",
    ArtifactType.HIGH_LEVEL_SOLUTION: "High Level Solution",
    ArtifactType.EFFORT_ESTIMATE: "Effort Estimate",
    ArtifactType.DIAGRAM: "Diagram",
}


@dataclass
class SourceDocument:
    name: str
    role: str
    text: str
    extension: str
    file_path: str | None = None
    uploaded_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProbeTurn:
    role: str
    text: str
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TemplateFamily:
    id: str
    name: str
    artifact_type: str
    domain: str
    intent: str
    audience: str
    description: str
    required_sections: list[str]
    forbidden_sections: list[str]
    output_schema: dict[str, Any]
    export_renderer: str
    prompt_instructions: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RouteDecision:
    artifact_type: str
    domain: str
    intent: str
    rationale: str
    confidence: float
    template_family_id: str
    missing_context: list[str] = field(default_factory=list)
    context_matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GeneratedArtifact:
    artifact_type: str
    title: str
    template_family_id: str
    renderer: str
    payload: dict[str, Any]
    preview_text: str
    rationale: str
    confidence: float
    reference_titles: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkspaceSnapshot:
    id: str
    name: str
    business_context: str
    application_name: str
    module_name: str
    audience: str
    domain_hint: str
    output_preference: str
    source_documents: list[SourceDocument] = field(default_factory=list)
    probe_history: list[ProbeTurn] = field(default_factory=list)
    artifacts: list[GeneratedArtifact] = field(default_factory=list)
    summary: str = ""
    inferred_domain: str = "Generic Enterprise App"
    inferred_app_type: str = ""
    confidence: float = 0.0
    default_template_path: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @property
    def combined_context(self) -> str:
        parts = [
            self.business_context,
            self.application_name,
            self.module_name,
            self.summary,
        ]
        parts.extend(doc.text for doc in self.source_documents)
        parts.extend(turn.text for turn in self.probe_history)
        return "\n\n".join(part for part in parts if part)

    def add_probe_turn(self, role: str, text: str) -> None:
        self.probe_history.append(ProbeTurn(role=role, text=text))
        self.updated_at = utc_now_iso()

    def add_artifact(self, artifact: GeneratedArtifact) -> None:
        self.artifacts.append(artifact)
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_documents"] = [doc.to_dict() for doc in self.source_documents]
        data["probe_history"] = [turn.to_dict() for turn in self.probe_history]
        data["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceSnapshot":
        return cls(
            id=data["id"],
            name=data["name"],
            business_context=data.get("business_context", ""),
            application_name=data.get("application_name", ""),
            module_name=data.get("module_name", ""),
            audience=data.get("audience", ""),
            domain_hint=data.get("domain_hint", "Auto-detect"),
            output_preference=data.get("output_preference", "Balanced detail"),
            source_documents=[SourceDocument(**doc) for doc in data.get("source_documents", [])],
            probe_history=[ProbeTurn(**turn) for turn in data.get("probe_history", [])],
            artifacts=[GeneratedArtifact(**artifact) for artifact in data.get("artifacts", [])],
            summary=data.get("summary", ""),
            inferred_domain=data.get("inferred_domain", "Generic Enterprise App"),
            inferred_app_type=data.get("inferred_app_type", ""),
            confidence=float(data.get("confidence", 0.0)),
            default_template_path=data.get("default_template_path"),
            created_at=data.get("created_at", utc_now_iso()),
            updated_at=data.get("updated_at", utc_now_iso()),
        )


def new_workspace_id() -> str:
    return uuid4().hex[:12]
