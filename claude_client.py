"""
claude_client.py
Manages the Anthropic API conversation for one Approach Note session.
"""
from __future__ import annotations

import json
import re

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    MAX_TOKENS_GENERATE,
    MAX_TOKENS_PROBE,
    MAX_BRD_CHARS,
)
from prompts import SYSTEM_PROMPT, GENERATE_PROMPT, build_probe_init

READY_MARKER = "[READY_TO_GENERATE]"


class ApproachNoteSession:
    """Holds the full conversation state for one CR's Approach Note."""

    def __init__(self, api_key: str, brd_text: str, cover_details: dict):
        self.client = anthropic.Anthropic(api_key=api_key or ANTHROPIC_API_KEY)
        self.messages: list[dict] = []
        self.brd_text = brd_text[:MAX_BRD_CHARS]
        self.cover_details = cover_details
        self.exchange_count = 0
        self.ready_to_generate = False

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> str:
        """Send the initial probe prompt and return Claude's first message."""
        init_text = build_probe_init(self.brd_text, self.cover_details)
        self.messages.append({"role": "user", "content": init_text})
        response_text = self._call_api(MAX_TOKENS_PROBE)
        self.messages.append({"role": "assistant", "content": response_text})
        self._check_ready(response_text)
        return self._strip_marker(response_text)

    def send(self, user_message: str) -> str:
        """Append a user message, get Claude's reply, return stripped reply."""
        self.messages.append({"role": "user", "content": user_message})
        response_text = self._call_api(MAX_TOKENS_PROBE)
        self.messages.append({"role": "assistant", "content": response_text})
        self.exchange_count += 1
        self._check_ready(response_text)
        return self._strip_marker(response_text)

    def generate_document(self) -> dict:
        """
        Append the generation prompt and return the parsed sections dict.
        Raises ValueError if the response is not valid JSON.
        """
        self.messages.append({"role": "user", "content": GENERATE_PROMPT})
        raw = self._call_api(MAX_TOKENS_GENERATE)
        self.messages.append({"role": "assistant", "content": raw})
        return self._parse_json(raw)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _call_api(self, max_tokens: int) -> str:
        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=self.messages,
        )
        return response.content[0].text

    def _check_ready(self, text: str) -> None:
        if READY_MARKER in text:
            self.ready_to_generate = True

    def _strip_marker(self, text: str) -> str:
        """Remove the [READY_TO_GENERATE] marker from text shown to BA."""
        return text.replace(READY_MARKER, "").strip()

    def _parse_json(self, raw: str) -> dict:
        """
        Extract JSON from Claude's response.
        Claude may occasionally wrap JSON in markdown fences even when told not to.
        """
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = cleaned.rstrip("`").strip()

        # Find the first { and last } to isolate JSON
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in Claude's response.")

        json_str = cleaned[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Claude returned malformed JSON: {exc}\n\nRaw:\n{raw[:500]}") from exc
