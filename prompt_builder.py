from __future__ import annotations

import json

from schemas import RouteDecision, TemplateFamily, WorkspaceSnapshot

BASE_SYSTEM_PROMPT = """You are a senior presales and business analysis copilot working across CRM, mobility, frontend, backend, integration, analytics, and enterprise platforms.

You help users understand requirements, clarify context, and generate the exact artifact requested.

Core behavior:
- Start from the BRD and user context first.
- If prior contexts look similar, use them as hints, not as facts.
- Ask targeted probing questions only for gaps that materially improve the requested output.
- Keep outputs aligned to the requested artifact and do not leak sections from other artifact types.
- Prefer plain, business-usable language unless the requested artifact is technical by nature.
"""


ARTIFACT_GUARDRAILS = {
    "proposal": "Proposal may include solution framing and delivery approach, but avoid detailed gantt, RACI, or resource loading unless explicitly requested.",
    "approach_note": "Functional Approach Note must remain functional/business-facing. Do not include effort estimation, gantt, RACI, resource loading, commercials, or detailed implementation steps.",
    "high_level_solution": "High Level Solution should explain the architecture and solution shape, not commercials or delivery governance tables.",
    "effort_estimate": "Effort Estimate must stay estimation-only. Do not add proposal copy, RACI, gantt, or commercial terms.",
    "diagram": "Diagram output must stay visual-structure focused with a short explanation. Do not add unrelated proposal or governance sections.",
}


def _format_references(title: str, items: list[dict]) -> str:
    if not items:
        return f"{title}: None"
    lines = [f"{title}:"]
    for item in items:
        summary = item.get("summary", "") or item.get("rationale", "")
        lines.append(f"- {item.get('title', item.get('name', 'Reference'))}: {summary[:300]}")
    return "\n".join(lines)


def build_probe_prompt(
    workspace: WorkspaceSnapshot,
    similar_contexts: list[dict],
    examples: list[dict],
) -> str:
    return f"""Current workspace:
Name: {workspace.name}
Business context: {workspace.business_context or "Not provided"}
Application: {workspace.application_name or "Not provided"}
Module: {workspace.module_name or "Not provided"}
Audience: {workspace.audience or "Not provided"}
Preferred detail: {workspace.output_preference}

Current inferred domain: {workspace.inferred_domain}

Primary documents:
{_document_bundle(workspace)}

{_format_references("Similar prior contexts", similar_contexts)}

{_format_references("Approved examples", examples)}

Your task:
1. Summarize the opportunity in 4-6 lines.
2. Decide what is still unclear to generate strong artifacts.
3. Ask exactly one high-value probing question.
4. If the current and prior context appear very similar, explicitly say what looks similar and ask the user to confirm whether the outcome should stay aligned or change.

Keep the tone collaborative and practical. Do not generate any deliverable yet.
"""


def build_generation_prompt(
    workspace: WorkspaceSnapshot,
    route: RouteDecision,
    template_family: TemplateFamily,
    request_text: str,
    examples: list[dict],
    similar_contexts: list[dict],
) -> str:
    return f"""Requested artifact: {request_text}

Route decision:
{json.dumps(route.to_dict(), indent=2)}

Template family:
{json.dumps(template_family.to_dict(), indent=2)}

Workspace summary:
{workspace.summary or "Not available yet"}

Workspace metadata:
- Name: {workspace.name}
- Application: {workspace.application_name or "Not provided"}
- Module: {workspace.module_name or "Not provided"}
- Audience: {workspace.audience or "Not provided"}
- Domain hint: {workspace.domain_hint}
- Inferred domain: {workspace.inferred_domain}
- User preference: {workspace.output_preference}

Conversation history:
{_conversation_history(workspace)}

Document context:
{_document_bundle(workspace)}

{_format_references("Similar prior contexts", similar_contexts)}

{_format_references("Approved examples", examples)}

Output instructions:
- Generate exactly one artifact that matches `{route.artifact_type}`.
- Respect this guardrail: {ARTIFACT_GUARDRAILS[route.artifact_type]}
- Required sections: {", ".join(template_family.required_sections)}
- Forbidden sections: {", ".join(template_family.forbidden_sections)}
- Use the output schema exactly as described below.
- Return valid JSON only. No markdown fences. No prose outside the JSON.

Output schema:
{json.dumps(template_family.output_schema, indent=2)}
"""


def build_system_prompt(route: RouteDecision | None = None) -> str:
    if not route:
        return BASE_SYSTEM_PROMPT
    return BASE_SYSTEM_PROMPT + "\n\nArtifact guardrail:\n" + ARTIFACT_GUARDRAILS[route.artifact_type]


def _document_bundle(workspace: WorkspaceSnapshot) -> str:
    parts = []
    for document in workspace.source_documents:
        excerpt = document.text[:5000]
        parts.append(f"Document: {document.name} ({document.role})\n{excerpt}")
    return "\n\n".join(parts) if parts else "No documents uploaded."


def _conversation_history(workspace: WorkspaceSnapshot) -> str:
    if not workspace.probe_history:
        return "No probing conversation yet."
    lines = []
    for turn in workspace.probe_history:
        lines.append(f"{turn.role.upper()}: {turn.text}")
    return "\n".join(lines)
