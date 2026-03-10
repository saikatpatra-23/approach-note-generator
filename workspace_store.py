from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from config import WORKSPACE_DIR
from schemas import WorkspaceSnapshot

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text or "")]


def _cosine_similarity(left: str, right: str) -> float:
    left_counts = Counter(_tokenize(left))
    right_counts = Counter(_tokenize(right))
    if not left_counts or not right_counts:
        return 0.0

    common = set(left_counts) & set(right_counts)
    dot = sum(left_counts[token] * right_counts[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class WorkspaceStore:
    def __init__(self, root: Path | None = None):
        self.root = root or WORKSPACE_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _workspace_path(self, workspace_id: str) -> Path:
        return self.root / workspace_id / "workspace.json"

    def _workspace_dir(self, workspace_id: str) -> Path:
        return self.root / workspace_id

    def save(self, workspace: WorkspaceSnapshot) -> None:
        workspace_dir = self._workspace_dir(workspace.id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        self._workspace_path(workspace.id).write_text(
            json.dumps(workspace.to_dict(), indent=2),
            encoding="utf-8",
        )

    def load(self, workspace_id: str) -> WorkspaceSnapshot:
        data = json.loads(self._workspace_path(workspace_id).read_text(encoding="utf-8"))
        return WorkspaceSnapshot.from_dict(data)

    def list_workspaces(self) -> list[WorkspaceSnapshot]:
        results: list[WorkspaceSnapshot] = []
        for workspace_path in sorted(self.root.glob("*/workspace.json"), reverse=True):
            try:
                data = json.loads(workspace_path.read_text(encoding="utf-8"))
                results.append(WorkspaceSnapshot.from_dict(data))
            except Exception:
                continue
        results.sort(key=lambda item: item.updated_at, reverse=True)
        return results

    def find_similar(self, workspace: WorkspaceSnapshot, limit: int = 3) -> list[dict[str, Any]]:
        current_text = workspace.combined_context
        scored: list[dict[str, Any]] = []
        for candidate in self.list_workspaces():
            if candidate.id == workspace.id:
                continue
            similarity = _cosine_similarity(current_text, candidate.combined_context)
            if candidate.application_name and candidate.application_name == workspace.application_name:
                similarity += 0.15
            if candidate.module_name and candidate.module_name == workspace.module_name:
                similarity += 0.1
            if similarity <= 0:
                continue
            scored.append(
                {
                    "workspace_id": candidate.id,
                    "name": candidate.name,
                    "application_name": candidate.application_name,
                    "module_name": candidate.module_name,
                    "summary": candidate.summary,
                    "updated_at": candidate.updated_at,
                    "similarity": round(min(similarity, 1.0), 3),
                }
            )
        scored.sort(key=lambda item: (item["similarity"], item["updated_at"]), reverse=True)
        return scored[:limit]
