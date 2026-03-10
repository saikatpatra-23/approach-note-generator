from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import DATABASE_URL, KB_AUTO_INIT, KB_EMBED_DIM, KB_STORAGE_DIR, RETRIEVAL_LIMIT
from schemas import GeneratedArtifact, RouteDecision, WorkspaceSnapshot

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def normalize_domain_value(domain: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (domain or "").strip().lower()).strip("_")
    if normalized in {"", "generic_enterprise_app", "auto_detect"}:
        return "generic"
    return normalized

try:
    from pgvector.sqlalchemy import Vector
    from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, create_engine, select, text
    from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

    SQLALCHEMY_AVAILABLE = True
except Exception:
    SQLALCHEMY_AVAILABLE = False
    Vector = None
    DeclarativeBase = object  # type: ignore[assignment]
    Mapped = object  # type: ignore[assignment]
    mapped_column = None  # type: ignore[assignment]
    Session = None  # type: ignore[assignment]
    create_engine = None  # type: ignore[assignment]
    select = None  # type: ignore[assignment]
    text = None  # type: ignore[assignment]
    JSON = Boolean = DateTime = Float = String = Text = None  # type: ignore[assignment]


def _tokenize(text_value: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text_value or "")]


def build_embedding(text_value: str, dim: int = KB_EMBED_DIM) -> list[float]:
    vector = [0.0] * dim
    for token in _tokenize(text_value):
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        index = int(digest, 16) % dim
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(l_val * r_val for l_val, r_val in zip(left, right))


if SQLALCHEMY_AVAILABLE:
    class Base(DeclarativeBase):
        pass


    class TemplateFamilyModel(Base):
        __tablename__ = "template_families"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        name: Mapped[str] = mapped_column(String(200))
        artifact_type: Mapped[str] = mapped_column(String(50), index=True)
        domain: Mapped[str] = mapped_column(String(80), index=True)
        intent: Mapped[str] = mapped_column(String(80), index=True)
        audience: Mapped[str] = mapped_column(String(120))
        description: Mapped[str] = mapped_column(Text)
        metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


    class TemplateModel(Base):
        __tablename__ = "templates"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        template_family_id: Mapped[str] = mapped_column(String(80), index=True)
        title: Mapped[str] = mapped_column(String(200))
        source_path: Mapped[str] = mapped_column(String(400))
        approval_status: Mapped[str] = mapped_column(String(40), default="approved")
        metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


    class KbExampleModel(Base):
        __tablename__ = "kb_examples"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        title: Mapped[str] = mapped_column(String(200))
        artifact_type: Mapped[str] = mapped_column(String(50), index=True)
        domain: Mapped[str] = mapped_column(String(80), index=True)
        intent: Mapped[str] = mapped_column(String(80), index=True)
        summary: Mapped[str] = mapped_column(Text)
        source_path: Mapped[str] = mapped_column(String(400))
        metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
        approval_status: Mapped[str] = mapped_column(String(40), index=True, default="approved")
        embedding: Mapped[list[float]] = mapped_column(Vector(KB_EMBED_DIM))
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


    class WorkspaceModel(Base):
        __tablename__ = "workspaces"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        name: Mapped[str] = mapped_column(String(200))
        domain: Mapped[str] = mapped_column(String(80), index=True)
        application_name: Mapped[str] = mapped_column(String(120), default="")
        module_name: Mapped[str] = mapped_column(String(120), default="")
        summary: Mapped[str] = mapped_column(Text, default="")
        confidence: Mapped[float] = mapped_column(Float, default=0.0)
        metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


    class SourceDocumentModel(Base):
        __tablename__ = "source_documents"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        workspace_id: Mapped[str] = mapped_column(String(80), index=True)
        name: Mapped[str] = mapped_column(String(200))
        role: Mapped[str] = mapped_column(String(40))
        extension: Mapped[str] = mapped_column(String(20))
        source_path: Mapped[str] = mapped_column(String(400))
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


    class ArtifactRunModel(Base):
        __tablename__ = "artifact_runs"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        workspace_id: Mapped[str] = mapped_column(String(80), index=True)
        artifact_type: Mapped[str] = mapped_column(String(50), index=True)
        template_family_id: Mapped[str] = mapped_column(String(80), index=True)
        confidence: Mapped[float] = mapped_column(Float, default=0.0)
        rationale: Mapped[str] = mapped_column(Text, default="")
        metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


    class ArtifactModel(Base):
        __tablename__ = "artifacts"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        workspace_id: Mapped[str] = mapped_column(String(80), index=True)
        artifact_type: Mapped[str] = mapped_column(String(50), index=True)
        title: Mapped[str] = mapped_column(String(200))
        payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
        preview_text: Mapped[str] = mapped_column(Text)
        approved: Mapped[bool] = mapped_column(Boolean, default=False)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


    class ApprovalModel(Base):
        __tablename__ = "approvals"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        artifact_id: Mapped[str] = mapped_column(String(80), index=True)
        approved_by: Mapped[str] = mapped_column(String(120))
        comments: Mapped[str] = mapped_column(Text, default="")
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeBaseService:
    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or KB_STORAGE_DIR
        self.examples_dir = self.storage_dir / "examples"
        self.uploads_dir = self.storage_dir / "uploads"
        self.examples_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.engine = None
        self.db_available = False
        if DATABASE_URL and SQLALCHEMY_AVAILABLE:
            self.engine = create_engine(DATABASE_URL, future=True)
            if KB_AUTO_INIT:
                self._init_db()

    def _init_db(self) -> None:
        if not self.engine or not SQLALCHEMY_AVAILABLE:
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            Base.metadata.create_all(self.engine)
            self.db_available = True
        except Exception:
            self.db_available = False

    def connection_status(self) -> str:
        if DATABASE_URL and not SQLALCHEMY_AVAILABLE:
            return "DATABASE_URL set but SQLAlchemy/pgvector dependencies are unavailable."
        if DATABASE_URL and self.db_available:
            return "Connected to Postgres + pgvector."
        if DATABASE_URL and not self.db_available:
            return "DATABASE_URL configured, but DB init failed. Using local fallback."
        return "Using local file-backed knowledge store. Add DATABASE_URL for Postgres + pgvector."

    def ingest_uploaded_reference(
        self,
        *,
        title: str,
        artifact_type: str,
        domain: str,
        intent: str,
        content_text: str,
        original_name: str,
        file_bytes: bytes,
        approval_status: str = "approved",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record_id = uuid4().hex[:12]
        safe_name = f"{record_id}_{original_name}"
        file_path = self.uploads_dir / safe_name
        file_path.write_bytes(file_bytes)

        record = {
            "id": record_id,
            "title": title,
            "artifact_type": artifact_type,
            "domain": normalize_domain_value(domain),
            "intent": intent,
            "summary": content_text[:4000],
            "source_path": str(file_path),
            "metadata": metadata or {},
            "approval_status": approval_status,
            "embedding": build_embedding(content_text),
            "created_at": datetime.utcnow().isoformat(),
        }
        self._save_local_example(record)
        self._save_db_example(record)
        return record

    def _save_local_example(self, record: dict[str, Any]) -> None:
        path = self.examples_dir / f"{record['id']}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def _save_db_example(self, record: dict[str, Any]) -> None:
        if not self.db_available or not self.engine:
            return
        try:
            with Session(self.engine) as session:
                session.merge(
                    KbExampleModel(
                        id=record["id"],
                        title=record["title"],
                        artifact_type=record["artifact_type"],
                        domain=record["domain"],
                        intent=record["intent"],
                        summary=record["summary"],
                        source_path=record["source_path"],
                        metadata_json=record.get("metadata", {}),
                        approval_status=record["approval_status"],
                        embedding=record["embedding"],
                    )
                )
                session.commit()
        except Exception:
            self.db_available = False

    def list_examples(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self.examples_dir.glob("*.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return records

    def search_examples(
        self,
        query_text: str,
        artifact_type: str | None = None,
        domain: str | None = None,
        intent: str | None = None,
        limit: int = RETRIEVAL_LIMIT,
    ) -> list[dict[str, Any]]:
        query_embedding = build_embedding(query_text)
        matches: list[dict[str, Any]] = []

        for record in self.list_examples():
            if record.get("approval_status") != "approved":
                continue
            if artifact_type and record.get("artifact_type") != artifact_type:
                continue
            if intent and record.get("intent") not in {intent, "generic"}:
                continue
            if domain and record.get("domain") not in {normalize_domain_value(domain), "generic"}:
                continue
            similarity = cosine_similarity(query_embedding, record.get("embedding", []))
            matches.append(
                {
                    **record,
                    "similarity": round(similarity, 3),
                }
            )

        matches.sort(key=lambda item: item["similarity"], reverse=True)
        return matches[:limit]

    def record_workspace(self, workspace: WorkspaceSnapshot) -> None:
        if not self.db_available or not self.engine:
            return
        try:
            with Session(self.engine) as session:
                session.merge(
                    WorkspaceModel(
                        id=workspace.id,
                        name=workspace.name,
                        domain=workspace.inferred_domain,
                        application_name=workspace.application_name,
                        module_name=workspace.module_name,
                        summary=workspace.summary,
                        confidence=workspace.confidence,
                        metadata_json={
                            "audience": workspace.audience,
                            "domain_hint": workspace.domain_hint,
                            "output_preference": workspace.output_preference,
                        },
                    )
                )
                session.commit()
        except Exception:
            self.db_available = False

    def record_artifact_run(
        self,
        workspace: WorkspaceSnapshot,
        route: RouteDecision,
        artifact: GeneratedArtifact,
    ) -> None:
        if not self.db_available or not self.engine:
            return
        try:
            with Session(self.engine) as session:
                session.merge(
                    ArtifactRunModel(
                        id=uuid4().hex[:12],
                        workspace_id=workspace.id,
                        artifact_type=route.artifact_type,
                        template_family_id=route.template_family_id,
                        confidence=route.confidence,
                        rationale=route.rationale,
                        metadata_json=route.to_dict(),
                    )
                )
                session.merge(
                    ArtifactModel(
                        id=uuid4().hex[:12],
                        workspace_id=workspace.id,
                        artifact_type=artifact.artifact_type,
                        title=artifact.title,
                        payload_json=artifact.payload,
                        preview_text=artifact.preview_text,
                        approved=artifact.approved,
                    )
                )
                session.commit()
        except Exception:
            self.db_available = False

    def approve_artifact(
        self,
        workspace: WorkspaceSnapshot,
        artifact: GeneratedArtifact,
        approved_by: str,
    ) -> dict[str, Any]:
        text_blob = "\n\n".join(
            [
                workspace.summary,
                artifact.preview_text,
                json.dumps(artifact.payload, indent=2),
            ]
        )
        record = self.ingest_uploaded_reference(
            title=artifact.title,
            artifact_type=artifact.artifact_type,
            domain=workspace.inferred_domain,
            intent=artifact.template_family_id,
            content_text=text_blob,
            original_name=f"{artifact.title}.json",
            file_bytes=json.dumps(artifact.payload, indent=2).encode("utf-8"),
            approval_status="approved",
            metadata={
                "workspace_id": workspace.id,
                "approved_by": approved_by,
                "source": "generated_artifact",
            },
        )
        if self.db_available and self.engine:
            try:
                with Session(self.engine) as session:
                    session.add(
                        ApprovalModel(
                            id=uuid4().hex[:12],
                            artifact_id=record["id"],
                            approved_by=approved_by,
                            comments="Approved from workspace artifact",
                        )
                    )
                    session.commit()
            except Exception:
                self.db_available = False
        return record
