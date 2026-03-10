from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Try os.environ first; fall back to Streamlit secrets when available."""
    val = os.getenv(key, "")
    if val:
        return val
    if not any(
        os.getenv(flag)
        for flag in ("STREAMLIT_SERVER_PORT", "STREAMLIT_RUNTIME", "STREAMLIT_RUN_ON_SAVE")
    ):
        return default
    try:
        import streamlit as st

        return st.secrets.get(key, default)
    except Exception:
        return default


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(_get_secret("DATA_DIR", str(BASE_DIR / ".data"))).resolve()
WORKSPACE_DIR = DATA_DIR / "workspaces"
KB_STORAGE_DIR = DATA_DIR / "kb_storage"
TEMPLATE_CATALOG_PATH = BASE_DIR / "template_families" / "catalog.json"

for path in (DATA_DIR, WORKSPACE_DIR, KB_STORAGE_DIR):
    path.mkdir(parents=True, exist_ok=True)


APP_TITLE = _get_secret("APP_TITLE", "Solution Copilot Workspace")
APP_SUBTITLE = _get_secret("APP_SUBTITLE", "Multi-artifact presales and BA copilot")
APP_PASSWORD = _get_secret("APP_PASSWORD")

ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _get_secret("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS_ROUTE = int(_get_secret("MAX_TOKENS_ROUTE", "768"))
MAX_TOKENS_PROBE = int(_get_secret("MAX_TOKENS_PROBE", "1200"))
MAX_TOKENS_GENERATE = int(_get_secret("MAX_TOKENS_GENERATE", "8192"))
MAX_DOCUMENT_CHARS = int(_get_secret("MAX_DOCUMENT_CHARS", "80000"))
MAX_REFERENCE_DOCS = int(_get_secret("MAX_REFERENCE_DOCS", "8"))

DATABASE_URL = _get_secret("DATABASE_URL")
KB_AUTO_INIT = _get_secret("KB_AUTO_INIT", "true").lower() == "true"
KB_EMBED_DIM = int(_get_secret("KB_EMBED_DIM", "96"))
RETRIEVAL_LIMIT = int(_get_secret("RETRIEVAL_LIMIT", "3"))

DEFAULT_AUDIENCES = [
    "Business Stakeholders",
    "Functional Team",
    "Technical Team",
    "Leadership / Steering Committee",
    "Delivery Team",
]

DEFAULT_DOMAINS = [
    "Auto-detect",
    "CRM",
    "Mobility",
    "Frontend",
    "Backend",
    "Integration",
    "Analytics",
    "Data / Platform",
    "Generic Enterprise App",
]

DEFAULT_OUTPUT_PREFERENCES = [
    "Keep it concise",
    "Balanced detail",
    "Detailed",
]

QUICK_ACTIONS = [
    ("Generate Proposal", "Create a proposal for this opportunity."),
    ("Generate Functional Approach Note", "Create a functional approach note."),
    ("Generate High Level Solution", "Create a high level solution."),
    ("Generate Effort Estimate", "Create an effort estimation."),
    ("Generate Architecture Diagram", "Create an architecture block diagram."),
    ("Generate Process Flow", "Create a process flow diagram."),
]
