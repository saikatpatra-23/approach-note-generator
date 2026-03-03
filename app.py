"""
app.py
Approach Note Generator — 3-step Streamlit wizard.

Step 1: Upload template + BRD, fill cover details
Step 2: Probing chat with Claude
Step 3: Preview sections & download Word document
"""
from __future__ import annotations

import os
import json

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Approach Note Generator",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Password gate ─────────────────────────────────────────────────────────────

def _get_secret(key: str, default: str = "") -> str:
    val = os.getenv(key, "")
    if val:
        return val
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

APP_PASSWORD = _get_secret("APP_PASSWORD")

def _check_password() -> bool:
    """Show password form. Returns True if authenticated."""
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <div style='max-width:380px; margin: 80px auto; text-align:center'>
        <h2 style='color:#0047AB'>📋 Approach Note Generator</h2>
        <p style='color:#555'>Tata Technologies — Internal Tool</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Enter access password", type="password", key="pwd_input")
        if st.button("Login", use_container_width=True):
            if pwd == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False


if APP_PASSWORD and not _check_password():
    st.stop()


# ── Imports (after auth gate — avoid loading heavy deps on login screen) ──────

from brd_parser import parse_brd
from claude_client import ApproachNoteSession
from doc_generator import build_approach_note
from prompts import SECTIONS
from config import (
    ANTHROPIC_API_KEY,
    MIN_PROBE_ROUNDS,
    APPLICATIONS,
    MODULES,
    BUSINESS_UNITS,
    CHANGE_TYPES,
    TIMELINES,
    COMPLEXITIES,
    PROJECTS,
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    .step-header {font-size: 1.4rem; font-weight: 700; color: #0047AB; margin-bottom: 0.2rem;}
    .step-sub    {color: #555; font-size: 0.9rem; margin-bottom: 1.2rem;}
    .chat-user   {background:#DCE6F1; border-radius:8px; padding:10px 14px; margin:6px 0;}
    .chat-bot    {background:#F0F4F8; border-radius:8px; padding:10px 14px; margin:6px 0;}
    .ready-badge {background:#198754; color:white; padding:4px 10px; border-radius:12px;
                  font-size:0.8rem; font-weight:600;}
    div[data-testid="stButton"] button {border-radius: 8px;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state initialisation ──────────────────────────────────────────────

def _init_state() -> None:
    defaults = {
        "step": 1,
        "template_bytes": None,
        "brd_text": None,
        "cover_details": {},
        "session": None,          # ApproachNoteSession
        "chat_history": [],       # list of (role, text)
        "sections": {},           # generated content dict
        "doc_bytes": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Setup
# ═══════════════════════════════════════════════════════════════════════════════

def render_step1() -> None:
    st.markdown('<div class="step-header">Step 1 — Upload Documents & Fill Cover Details</div>', unsafe_allow_html=True)
    st.markdown('<div class="step-sub">Upload the Approach Note template and BRD, then fill in the CR details below.</div>', unsafe_allow_html=True)

    # ── File uploads ──────────────────────────────────────────────────────────
    col_l, col_r = st.columns(2)
    with col_l:
        tmpl_file = st.file_uploader(
            "Upload Approach Note Template (.docx)",
            type=["docx"],
            key="tmpl_upload",
            help="The standard template .docx — used for page layout and styles only.",
        )
    with col_r:
        brd_file = st.file_uploader(
            "Upload BRD (PDF / DOCX / PPTX)",
            type=["pdf", "docx", "pptx", "ppt"],
            key="brd_upload",
            help="The Business Requirements Document for this CR.",
        )

    st.divider()

    # ── Cover details form ────────────────────────────────────────────────────
    st.markdown("#### CR Cover Details")

    c1, c2, c3, c4 = st.columns(4)
    cr_number   = c1.text_input("CR Number",  placeholder="e.g. CR-2024-1023")
    project     = c2.selectbox("Project",     PROJECTS)
    application = c3.selectbox("Application", APPLICATIONS)
    module      = c4.selectbox("Module",      MODULES)

    c5, c6, c7, c8 = st.columns(4)
    change_type   = c5.selectbox("Change Type",    CHANGE_TYPES)
    timeline      = c6.selectbox("Timeline",       TIMELINES)
    business_unit = c7.selectbox("Business Unit",  BUSINESS_UNITS)
    complexity    = c8.selectbox("Complexity",      COMPLEXITIES)

    c9, c10, c11 = st.columns(3)
    brm_name = c9.text_input("BRM Name",  placeholder="Business Relationship Manager")
    bpo_name = c10.text_input("BPO Name", placeholder="Business Process Owner")
    ba_name  = c11.text_input("BA Name",  placeholder="Your name")

    summary = st.text_area(
        "CR Summary (2-3 lines)",
        placeholder="Brief description of what this change is about and why it is needed.",
        height=90,
    )

    st.divider()

    # ── Validation & proceed ──────────────────────────────────────────────────
    if st.button("Start Analysis →", type="primary", use_container_width=False):
        errors = []
        if not tmpl_file:
            errors.append("Please upload the Approach Note template (.docx).")
        if not brd_file:
            errors.append("Please upload the BRD.")
        if not cr_number.strip():
            errors.append("CR Number is required.")
        if not ba_name.strip():
            errors.append("BA Name is required.")
        if not summary.strip():
            errors.append("CR Summary is required.")

        if errors:
            for e in errors:
                st.error(e)
            return

        with st.spinner("Parsing BRD and initialising Claude..."):
            try:
                brd_bytes = brd_file.read()
                brd_text  = parse_brd(brd_file.name, brd_bytes)
            except Exception as exc:
                st.error(f"Failed to parse BRD: {exc}")
                return

            cover = {
                "cr_number":     cr_number.strip(),
                "project":       project,
                "application":   application,
                "module":        module,
                "change_type":   change_type,
                "timeline":      timeline,
                "business_unit": business_unit,
                "complexity":    complexity,
                "brm_name":      brm_name.strip(),
                "bpo_name":      bpo_name.strip(),
                "ba_name":       ba_name.strip(),
                "summary":       summary.strip(),
            }

            api_key = ANTHROPIC_API_KEY
            if not api_key:
                st.error("ANTHROPIC_API_KEY not set. Add it to the .env file.")
                return

            session = ApproachNoteSession(
                api_key=api_key,
                brd_text=brd_text,
                cover_details=cover,
            )

            try:
                first_message = session.start()
            except Exception as exc:
                st.error(f"Claude API error: {exc}")
                return

            st.session_state.template_bytes = tmpl_file.getvalue()
            st.session_state.brd_text       = brd_text
            st.session_state.cover_details  = cover
            st.session_state.session        = session
            st.session_state.chat_history   = [("assistant", first_message)]
            st.session_state.step           = 2

        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Probing Chat
# ═══════════════════════════════════════════════════════════════════════════════

def render_step2() -> None:
    session: ApproachNoteSession = st.session_state.session
    cover   = st.session_state.cover_details

    st.markdown('<div class="step-header">Step 2 — Probing Session</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="step-sub">CR: <strong>{cover.get("cr_number", "")}</strong> | '
        f'Module: <strong>{cover.get("module", "")}</strong> | '
        f'BU: <strong>{cover.get("business_unit", "")}</strong></div>',
        unsafe_allow_html=True,
    )

    # ── BRD summary expander ──────────────────────────────────────────────────
    with st.expander("View extracted BRD text", expanded=False):
        st.text(st.session_state.brd_text[:3000] + (" ..." if len(st.session_state.brd_text) > 3000 else ""))

    # ── Progress indicator ────────────────────────────────────────────────────
    exchanges = session.exchange_count
    ready     = session.ready_to_generate
    min_ex    = MIN_PROBE_ROUNDS

    prog_col, badge_col = st.columns([4, 1])
    with prog_col:
        progress = min(exchanges / min_ex, 1.0)
        st.progress(progress, text=f"Exchanges: {exchanges} / {min_ex} minimum")
    with badge_col:
        if ready:
            st.markdown('<span class="ready-badge">Ready to Generate</span>', unsafe_allow_html=True)

    st.divider()

    # ── Chat history ──────────────────────────────────────────────────────────
    chat_container = st.container()
    with chat_container:
        for role, text in st.session_state.chat_history:
            if role == "assistant":
                st.markdown(
                    f'<div class="chat-bot"><strong>Claude:</strong><br>{text.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="chat-user"><strong>You:</strong><br>{text.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True,
                )

    st.divider()

    # ── Input row ─────────────────────────────────────────────────────────────
    input_col, btn_col = st.columns([5, 1])
    with input_col:
        user_input = st.text_area(
            "Your response",
            placeholder="Type your answer here...",
            height=80,
            key=f"user_input_{session.exchange_count}",
            label_visibility="collapsed",
        )
    with btn_col:
        st.write("")  # spacing
        send_clicked = st.button("Send →", type="primary", use_container_width=True)

    if send_clicked and user_input.strip():
        with st.spinner("Claude is thinking..."):
            try:
                reply = session.send(user_input.strip())
            except Exception as exc:
                st.error(f"API error: {exc}")
                return

        st.session_state.chat_history.append(("user", user_input.strip()))
        st.session_state.chat_history.append(("assistant", reply))
        st.rerun()

    st.divider()

    # ── Generate button ───────────────────────────────────────────────────────
    can_generate = ready or (exchanges >= min_ex)
    gen_col, back_col = st.columns([2, 1])

    with gen_col:
        if can_generate:
            if st.button("Generate Approach Note Document", type="primary", use_container_width=True):
                with st.spinner("Claude is writing all 11 sections..."):
                    try:
                        sections = session.generate_document()
                    except ValueError as exc:
                        st.error(f"Generation error: {exc}")
                        return
                st.session_state.sections = sections
                st.session_state.step = 3
                st.rerun()
        else:
            st.info(f"Answer at least {min_ex} questions before generating (currently {exchanges}).")

    with back_col:
        if st.button("← Start Over", use_container_width=True):
            for k in ["step", "template_bytes", "brd_text", "cover_details",
                      "session", "chat_history", "sections", "doc_bytes"]:
                st.session_state.pop(k, None)
            _init_state()
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Preview & Download
# ═══════════════════════════════════════════════════════════════════════════════

def render_step3() -> None:
    cover    = st.session_state.cover_details
    sections = st.session_state.sections

    st.markdown('<div class="step-header">Step 3 — Review & Download</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="step-sub">Review each section below. Edit if needed, then generate the Word document.</div>',
        unsafe_allow_html=True,
    )

    st.info(
        f"CR: **{cover.get('cr_number', '')}** | Module: **{cover.get('module', '')}** | "
        f"BA: **{cover.get('ba_name', '')}** | Complexity: **{cover.get('complexity', '')}**"
    )

    # ── Editable section previews ─────────────────────────────────────────────
    edited: dict = {}

    for key, display_name in SECTIONS.items():
        raw = sections.get(key, "")

        with st.expander(display_name, expanded=False):
            if isinstance(raw, list):
                # Show as JSON in a text area for list sections
                edited_text = st.text_area(
                    f"Edit {display_name} (JSON)",
                    value=json.dumps(raw, indent=2),
                    height=200,
                    key=f"edit_{key}",
                )
                try:
                    edited[key] = json.loads(edited_text)
                except json.JSONDecodeError:
                    st.warning("Invalid JSON — using original content.")
                    edited[key] = raw
            else:
                edited_text = st.text_area(
                    f"Edit {display_name}",
                    value=str(raw) if raw else "",
                    height=200,
                    key=f"edit_{key}",
                )
                edited[key] = edited_text

    st.divider()

    # ── Generate Word document ─────────────────────────────────────────────────
    dl_col, back_col, restart_col = st.columns([2, 1, 1])

    with dl_col:
        if st.button("Build Word Document (.docx)", type="primary", use_container_width=True):
            with st.spinner("Building Word document..."):
                try:
                    doc_bytes = build_approach_note(
                        template_bytes=st.session_state.template_bytes,
                        cover_details=cover,
                        sections_dict=edited,
                    )
                    st.session_state.doc_bytes = doc_bytes
                except Exception as exc:
                    st.error(f"Document build error: {exc}")
                    return
            st.success("Document ready! Click the download button below.")

    if st.session_state.doc_bytes:
        cr = cover.get("cr_number", "CR").replace("/", "-").replace(" ", "_")
        st.download_button(
            label="Download Approach Note (.docx)",
            data=st.session_state.doc_bytes,
            file_name=f"Approach_Note_{cr}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=False,
        )

    with back_col:
        if st.button("← Back to Chat", use_container_width=True):
            st.session_state.step = 2
            st.rerun()

    with restart_col:
        if st.button("Start New CR", use_container_width=True):
            for k in ["step", "template_bytes", "brd_text", "cover_details",
                      "session", "chat_history", "sections", "doc_bytes"]:
                st.session_state.pop(k, None)
            _init_state()
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# Step router
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # Breadcrumb header
    steps = ["1. Setup", "2. Probing", "3. Download"]
    current = st.session_state.get("step", 1)

    st.markdown(
        "**Approach Note Generator** &nbsp;|&nbsp; " +
        " → ".join(
            f"**{s}**" if i + 1 == current else s
            for i, s in enumerate(steps)
        ),
        unsafe_allow_html=True,
    )
    st.divider()

    if current == 1:
        render_step1()
    elif current == 2:
        render_step2()
    elif current == 3:
        render_step3()


main()
