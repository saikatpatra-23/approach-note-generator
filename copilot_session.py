from __future__ import annotations

import json
import re
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_DOCUMENT_CHARS, MAX_TOKENS_GENERATE, MAX_TOKENS_PROBE
from prompt_builder import build_generation_prompt, build_probe_prompt, build_system_prompt
from schemas import GeneratedArtifact, RouteDecision, TemplateFamily, WorkspaceSnapshot


class OpportunityCopilotSession:
    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key or ANTHROPIC_API_KEY)

    def start_probe(
        self,
        workspace: WorkspaceSnapshot,
        similar_contexts: list[dict],
        examples: list[dict],
    ) -> str:
        prompt = build_probe_prompt(self._trim_workspace(workspace), similar_contexts, examples)
        return self._call_messages(
            system=build_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS_PROBE,
        )

    def continue_probe(
        self,
        workspace: WorkspaceSnapshot,
        similar_contexts: list[dict],
        examples: list[dict],
        user_message: str | None = None,
    ) -> str:
        prompt = build_probe_prompt(self._trim_workspace(workspace), similar_contexts, examples)
        messages = [{"role": turn.role, "content": turn.text} for turn in workspace.probe_history]
        if user_message and messages and messages[-1]["role"] == "user" and messages[-1]["content"] == user_message:
            messages = messages[:-1]
        if user_message:
            prompt = (
                f"Latest user clarification:\n{user_message}\n\n"
                "Use the full workspace context below. First mirror back what changed or what stayed the same, "
                "especially if prior similar contexts may still apply. Then ask exactly one next high-value probing question.\n\n"
                + prompt
            )
        messages.append({"role": "user", "content": prompt})
        return self._call_messages(
            system=build_system_prompt(),
            messages=messages,
            max_tokens=MAX_TOKENS_PROBE,
        )

    def generate_artifact(
        self,
        workspace: WorkspaceSnapshot,
        route: RouteDecision,
        template_family: TemplateFamily,
        request_text: str,
        examples: list[dict],
        similar_contexts: list[dict],
    ) -> GeneratedArtifact:
        prompt = build_generation_prompt(
            self._trim_workspace(workspace),
            route,
            template_family,
            request_text,
            examples,
            similar_contexts,
        )
        messages = [{"role": turn.role, "content": turn.text} for turn in workspace.probe_history]
        messages.append({"role": "user", "content": prompt})
        raw = self._call_messages(
            system=build_system_prompt(route),
            messages=messages,
            max_tokens=MAX_TOKENS_GENERATE,
        )
        payload = self._parse_json(raw)
        title = payload.get("title") or f"{template_family.name} - {workspace.name}"
        preview = build_preview_text(route.artifact_type, payload)
        return GeneratedArtifact(
            artifact_type=route.artifact_type,
            title=title,
            template_family_id=template_family.id,
            renderer=template_family.export_renderer,
            payload=payload,
            preview_text=preview,
            rationale=route.rationale,
            confidence=route.confidence,
            reference_titles=[example.get("title", "") for example in examples],
        )

    def _call_messages(self, *, system: str, messages: list[dict[str, str]], max_tokens: int) -> str:
        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    def _parse_json(self, raw: str) -> dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end <= 0:
            raise ValueError("Model response did not contain a JSON object.")
        return json.loads(cleaned[start:end])

    def _trim_workspace(self, workspace: WorkspaceSnapshot) -> WorkspaceSnapshot:
        trimmed = WorkspaceSnapshot.from_dict(workspace.to_dict())
        for document in trimmed.source_documents:
            document.text = document.text[:MAX_DOCUMENT_CHARS]
        return trimmed


def build_preview_text(artifact_type: str, payload: dict[str, Any]) -> str:
    if artifact_type == "diagram":
        notes = payload.get("notes", [])
        return "\n".join(
            [
                payload.get("title", "Diagram"),
                payload.get("objective", ""),
                "Nodes: " + ", ".join(node.get("label", "") for node in payload.get("nodes", [])),
                "Notes:",
                *(f"- {note}" for note in notes),
            ]
        ).strip()

    lines: list[str] = []
    for key, value in payload.items():
        label = key.replace("_", " ").title()
        if isinstance(value, str):
            lines.append(f"{label}\n{value}")
        else:
            lines.append(f"{label}\n{json.dumps(value, indent=2)}")
    return "\n\n".join(lines)
