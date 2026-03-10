"""
app.py
Solution Copilot Workspace.

Create an opportunity workspace, ingest BRDs/reference docs, probe for missing
context, auto-route the requested artifact, and export the generated output.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from artifact_renderers import render_artifact
from brd_parser import parse_document
from config import (
    ANTHROPIC_API_KEY,
    APP_PASSWORD,
    APP_SUBTITLE,
    APP_TITLE,
    DEFAULT_AUDIENCES,
    DEFAULT_DOMAINS,
    DEFAULT_OUTPUT_PREFERENCES,
    QUICK_ACTIONS,
    RETRIEVAL_LIMIT,
    WORKSPACE_DIR,
)
from copilot_session import OpportunityCopilotSession, build_preview_text
from intent_router import IntentRouter
from knowledge_base import KnowledgeBaseService
from schemas import ArtifactType, GeneratedArtifact, SourceDocument, WorkspaceSnapshot, new_workspace_id
from template_catalog import TemplateCatalog
from workspace_store import WorkspaceStore

load_dotenv()

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📌",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        f"""
        <div style='max-width:420px; margin: 90px auto; text-align:center'>
        <h2 style='color:#114B8C'>📌 {APP_TITLE}</h2>
        <p style='color:#555'>{APP_SUBTITLE}</p>
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


@st.cache_resource
def get_catalog() -> TemplateCatalog:
    return TemplateCatalog()


@st.cache_resource
def get_workspace_store() -> WorkspaceStore:
    return WorkspaceStore()


@st.cache_resource
def get_knowledge_base() -> KnowledgeBaseService:
    return KnowledgeBaseService()


@st.cache_resource
def get_router() -> IntentRouter:
    return IntentRouter(get_catalog())


@st.cache_resource
def get_copilot() -> OpportunityCopilotSession | None:
    if not ANTHROPIC_API_KEY:
        return None
    return OpportunityCopilotSession(api_key=ANTHROPIC_API_KEY)


def _init_state() -> None:
    defaults = {
        "workspace": None,
        "similar_contexts": [],
        "example_matches": [],
        "route_decision": None,
        "generated_artifact": None,
        "artifact_request_input": "",
        "artifact_payload_editor": "",
        "template_bytes": None,
        "approver_name": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_runtime_state() -> None:
    for key in [
        "workspace",
        "similar_contexts",
        "example_matches",
        "route_decision",
        "generated_artifact",
        "artifact_request_input",
        "artifact_payload_editor",
        "template_bytes",
    ]:
        st.session_state[key] = None if key in {"workspace", "route_decision", "generated_artifact", "template_bytes"} else []
    st.session_state.artifact_request_input = ""
    st.session_state.similar_contexts = []
    st.session_state.example_matches = []
    st.session_state.artifact_payload_editor = ""


def _workspace_upload_dir(workspace_id: str) -> Path:
    path = WORKSPACE_DIR / workspace_id / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_upload(workspace_id: str, uploaded_file) -> str:
    path = _workspace_upload_dir(workspace_id) / uploaded_file.name
    path.write_bytes(uploaded_file.getvalue())
    return str(path)


def _summary_from_message(message: str) -> str:
    parts = [part.strip() for part in message.split("\n") if part.strip()]
    if not parts:
        return ""
    summary_lines = []
    for part in parts:
        summary_lines.append(part)
        if part.endswith("?"):
            break
        if len(summary_lines) >= 3:
            break
    return " ".join(summary_lines).replace("?", ".").strip()


def _load_workspace(workspace_id: str) -> None:
    store = get_workspace_store()
    kb = get_knowledge_base()
    workspace = store.load(workspace_id)
    st.session_state.workspace = workspace
    st.session_state.template_bytes = None
    if workspace.default_template_path:
        template_path = Path(workspace.default_template_path)
        if template_path.exists():
            st.session_state.template_bytes = template_path.read_bytes()
    st.session_state.similar_contexts = store.find_similar(workspace, limit=RETRIEVAL_LIMIT)
    st.session_state.example_matches = kb.search_examples(
        workspace.combined_context,
        domain=workspace.inferred_domain.lower().replace(" ", "_"),
        limit=RETRIEVAL_LIMIT,
    )
    st.session_state.route_decision = None
    st.session_state.generated_artifact = workspace.artifacts[-1] if workspace.artifacts else None
    if st.session_state.generated_artifact:
        st.session_state.artifact_payload_editor = json.dumps(
            st.session_state.generated_artifact.payload,
            indent=2,
        )


def _persist_workspace(workspace: WorkspaceSnapshot) -> None:
    store = get_workspace_store()
    kb = get_knowledge_base()
    store.save(workspace)
    kb.record_workspace(workspace)


def _handle_workspace_creation() -> None:
    router = get_router()
    kb = get_knowledge_base()
    copilot = get_copilot()

    with st.form("workspace_create_form", clear_on_submit=False):
        st.markdown("#### Create Opportunity Workspace")
        c1, c2 = st.columns(2)
        workspace_name = c1.text_input("Workspace Name", placeholder="e.g. Dealer Mobile App Lead Capture")
        application_name = c2.text_input("Application / Platform", placeholder="e.g. Mobility App, Siebel CRM, React Portal")

        c3, c4 = st.columns(2)
        module_name = c3.text_input("Module / Capability", placeholder="e.g. Lead Management, Survey Capture")
        audience = c4.selectbox("Primary Audience", DEFAULT_AUDIENCES)

        c5, c6 = st.columns(2)
        domain_hint = c5.selectbox("Domain Hint", DEFAULT_DOMAINS)
        output_preference = c6.selectbox("Preferred Detail", DEFAULT_OUTPUT_PREFERENCES, index=1)

        business_context = st.text_area(
            "Opportunity / Business Context",
            placeholder="Share what the team is trying to solve, client context, timeline pressure, or any useful background.",
            height=100,
        )

        brd_file = st.file_uploader(
            "Primary BRD / requirement document",
            type=["pdf", "docx", "pptx", "ppt", "txt", "md", "csv", "json"],
            key="workspace_brd",
        )
        reference_files = st.file_uploader(
            "Reference documents (optional)",
            type=["pdf", "docx", "pptx", "ppt", "txt", "md", "csv", "json"],
            accept_multiple_files=True,
            key="workspace_refs",
        )
        word_template = st.file_uploader(
            "Default Word template for exports (optional)",
            type=["docx"],
            key="workspace_template",
        )

        create_clicked = st.form_submit_button("Create Workspace", type="primary")

    if not create_clicked:
        return

    errors: list[str] = []
    if not workspace_name.strip():
        errors.append("Workspace name is required.")
    if not brd_file:
        errors.append("A primary BRD / requirement document is required.")
    if errors:
        for error in errors:
            st.error(error)
        return

    workspace_id = new_workspace_id()
    source_documents: list[SourceDocument] = []
    try:
        brd_text = parse_document(brd_file.name, brd_file.getvalue())
        brd_path = _save_upload(workspace_id, brd_file)
        source_documents.append(
            SourceDocument(
                name=brd_file.name,
                role="primary_brd",
                text=brd_text,
                extension=brd_file.name.rsplit(".", 1)[-1].lower(),
                file_path=brd_path,
            )
        )
        for uploaded in reference_files or []:
            ref_text = parse_document(uploaded.name, uploaded.getvalue())
            ref_path = _save_upload(workspace_id, uploaded)
            source_documents.append(
                SourceDocument(
                    name=uploaded.name,
                    role="reference",
                    text=ref_text,
                    extension=uploaded.name.rsplit(".", 1)[-1].lower(),
                    file_path=ref_path,
                )
            )
    except Exception as exc:
        st.error(f"Failed to parse uploaded documents: {exc}")
        return

    template_path = None
    if word_template:
        template_path = _save_upload(workspace_id, word_template)
        st.session_state.template_bytes = word_template.getvalue()
    else:
        st.session_state.template_bytes = None

    workspace = WorkspaceSnapshot(
        id=workspace_id,
        name=workspace_name.strip(),
        business_context=business_context.strip(),
        application_name=application_name.strip(),
        module_name=module_name.strip(),
        audience=audience,
        domain_hint=domain_hint,
        output_preference=output_preference,
        source_documents=source_documents,
        default_template_path=template_path,
    )
    inferred_domain, domain_conf = router.infer_domain(workspace)
    workspace.inferred_domain = inferred_domain.replace("_", " ").title() if inferred_domain != "generic" else "Generic Enterprise App"
    workspace.inferred_app_type = application_name.strip() or inferred_domain
    workspace.confidence = round(domain_conf, 2)

    store = get_workspace_store()
    similar_contexts = store.find_similar(workspace, limit=RETRIEVAL_LIMIT)
    example_matches = kb.search_examples(
        workspace.combined_context,
        domain=inferred_domain,
        limit=RETRIEVAL_LIMIT,
    )

    initial_message = ""
    if copilot:
        try:
            initial_message = copilot.start_probe(workspace, similar_contexts, example_matches)
            workspace.add_probe_turn("assistant", initial_message)
            workspace.summary = _summary_from_message(initial_message)
        except Exception as exc:
            st.warning(f"Workspace created, but probing could not start automatically: {exc}")
    else:
        initial_message = (
            "API key is not configured, so probing is unavailable. "
            "You can still use the workspace and admin KB flows."
        )
        workspace.add_probe_turn("assistant", initial_message)
        workspace.summary = brd_text[:320]

    _persist_workspace(workspace)
    st.session_state.workspace = workspace
    st.session_state.similar_contexts = similar_contexts
    st.session_state.example_matches = example_matches
    st.session_state.route_decision = None
    st.session_state.generated_artifact = None
    st.session_state.artifact_request_input = ""
    st.session_state.artifact_payload_editor = ""
    st.success("Workspace created. Start probing or request an artifact.")


def _render_sidebar() -> None:
    store = get_workspace_store()
    kb = get_knowledge_base()
    st.sidebar.markdown(f"## {APP_TITLE}")
    st.sidebar.caption(APP_SUBTITLE)
    st.sidebar.info(kb.connection_status())

    if st.sidebar.button("Start New Workspace", use_container_width=True):
        _reset_runtime_state()
        st.rerun()

    st.sidebar.markdown("### Recent Workspaces")
    recent = store.list_workspaces()[:8]
    if not recent:
        st.sidebar.caption("No saved workspaces yet.")
    for workspace in recent:
        label = workspace.name if len(workspace.name) < 28 else workspace.name[:25] + "..."
        if st.sidebar.button(label, key=f"open_{workspace.id}", use_container_width=True):
            _load_workspace(workspace.id)
            st.rerun()


def _render_workspace_overview(workspace: WorkspaceSnapshot) -> None:
    st.markdown("#### Workspace Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Application", workspace.application_name or "-")
    c2.metric("Module", workspace.module_name or "-")
    c3.metric("Inferred Domain", workspace.inferred_domain)
    c4.metric("Context Confidence", f"{int(workspace.confidence * 100)}%")
    st.caption(workspace.summary or "Summary will become sharper as probing continues.")

    with st.expander("Source documents", expanded=False):
        for document in workspace.source_documents:
            st.markdown(f"**{document.name}** ({document.role})")
            st.text(document.text[:1500] + (" ..." if len(document.text) > 1500 else ""))

    with st.expander("Similar recent contexts", expanded=False):
        if not st.session_state.similar_contexts:
            st.caption("No similar prior workspaces found yet.")
        for match in st.session_state.similar_contexts:
            st.markdown(
                f"**{match['name']}** | similarity `{match['similarity']}` | "
                f"{match.get('application_name') or '-'} / {match.get('module_name') or '-'}"
            )
            if match.get("summary"):
                st.caption(match["summary"])


def _render_probe_chat(workspace: WorkspaceSnapshot) -> None:
    st.markdown("#### Adaptive Probing")
    st.caption(
        "The copilot uses BRD context first, then checks similar past workspaces. "
        "If something looks close, it will ask whether the end product should stay aligned."
    )

    for idx, turn in enumerate(workspace.probe_history):
        role_label = "Copilot" if turn.role == "assistant" else "You"
        background = "#F3F7FB" if turn.role == "assistant" else "#E8F2FF"
        st.markdown(
            f"<div style='background:{background}; padding:12px 14px; border-radius:10px; margin:8px 0;'>"
            f"<strong>{role_label}:</strong><br>{turn.text.replace(chr(10), '<br>')}</div>",
            unsafe_allow_html=True,
        )

    user_probe = st.text_area(
        "Continue the context chat",
        placeholder="Add missing context, confirm whether a similar older request still applies, or answer the latest question.",
        height=100,
        key=f"probe_input_{workspace.id}",
    )
    col1, col2 = st.columns([1, 1])
    with col1:
        send_clicked = st.button("Send Context", type="primary", use_container_width=True)
    with col2:
        refresh_clicked = st.button("Ask Next Smart Question", use_container_width=True)

    copilot = get_copilot()
    if send_clicked and user_probe.strip():
        workspace.add_probe_turn("user", user_probe.strip())
        if not copilot:
            st.warning("ANTHROPIC_API_KEY is not configured, so probing cannot continue.")
        else:
            try:
                reply = copilot.continue_probe(
                    workspace,
                    st.session_state.similar_contexts,
                    st.session_state.example_matches,
                    user_message=user_probe.strip(),
                )
                workspace.add_probe_turn("assistant", reply)
                workspace.summary = _summary_from_message(reply) or workspace.summary
                _persist_workspace(workspace)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not continue probing: {exc}")
    elif refresh_clicked:
        if not copilot:
            st.warning("ANTHROPIC_API_KEY is not configured, so probing cannot continue.")
        else:
            try:
                reply = copilot.continue_probe(
                    workspace,
                    st.session_state.similar_contexts,
                    st.session_state.example_matches,
                )
                workspace.add_probe_turn("assistant", reply)
                workspace.summary = _summary_from_message(reply) or workspace.summary
                _persist_workspace(workspace)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not generate the next question: {exc}")


def _render_artifact_studio(workspace: WorkspaceSnapshot) -> None:
    st.markdown("#### Artifact Studio")
    st.caption("Ask for exactly what you want. The router will suggest a template family and keep the output scoped to that artifact only.")

    action_cols = st.columns(3)
    for idx, (label, prompt) in enumerate(QUICK_ACTIONS):
        if action_cols[idx % 3].button(label, key=f"qa_{idx}", use_container_width=True):
            st.session_state.artifact_request_input = prompt

    request_text = st.text_input(
        "Artifact request",
        value=st.session_state.artifact_request_input,
        placeholder="e.g. Share a functional approach note for this change, or create a proposal for this opportunity.",
    )
    st.session_state.artifact_request_input = request_text

    route_col, clear_col = st.columns([2, 1])
    with route_col:
        route_clicked = st.button("Route Request", type="primary", use_container_width=True)
    with clear_col:
        if st.button("Clear Route", use_container_width=True):
            st.session_state.route_decision = None
            st.session_state.generated_artifact = None
            st.session_state.artifact_payload_editor = ""
            st.rerun()

    router = get_router()
    kb = get_knowledge_base()
    catalog = get_catalog()
    if route_clicked and request_text.strip():
        route = router.route(
            request_text,
            workspace,
            context_matches=st.session_state.similar_contexts,
        )
        st.session_state.route_decision = route
        st.session_state.example_matches = kb.search_examples(
            workspace.combined_context + "\n" + request_text,
            artifact_type=route.artifact_type,
            domain=route.domain,
            intent=route.intent,
            limit=RETRIEVAL_LIMIT,
        )
        st.session_state.generated_artifact = None
        st.session_state.artifact_payload_editor = ""

    route = st.session_state.route_decision
    if not route:
        _render_generated_artifact(workspace)
        return

    candidates = catalog.find_candidates(route.artifact_type, route.domain, route.intent)
    if not candidates:
        st.error("No template families are configured for this route.")
        _render_generated_artifact(workspace)
        return
    candidate_ids = [candidate.id for candidate in candidates]
    selected_template_id = st.selectbox(
        "Template family",
        candidate_ids,
        index=max(candidate_ids.index(route.template_family_id), 0) if route.template_family_id in candidate_ids else 0,
        format_func=lambda item: catalog.get(item).name,
    )
    route.template_family_id = selected_template_id

    st.info(
        f"Suggested artifact: **{route.artifact_type.replace('_', ' ').title()}** | "
        f"Intent: **{route.intent}** | Domain: **{route.domain}** | "
        f"Confidence: **{int(route.confidence * 100)}%**"
    )
    st.caption(route.rationale)
    if route.missing_context:
        st.warning("Missing context that could improve output: " + ", ".join(route.missing_context))

    with st.expander("References used for routing", expanded=False):
        if not st.session_state.example_matches:
            st.caption("No approved examples matched this request yet.")
        for example in st.session_state.example_matches:
            st.markdown(f"**{example['title']}** | similarity `{example['similarity']}`")
            st.caption(example.get("summary", "")[:250])

    if st.button("Generate Artifact", type="primary", use_container_width=True):
        copilot = get_copilot()
        if not copilot:
            st.error("ANTHROPIC_API_KEY is not configured, so artifact generation is unavailable.")
            return
        try:
            artifact = copilot.generate_artifact(
                workspace,
                route,
                catalog.get(route.template_family_id),
                request_text,
                st.session_state.example_matches,
                st.session_state.similar_contexts,
            )
            workspace.add_artifact(artifact)
            st.session_state.generated_artifact = artifact
            st.session_state.artifact_payload_editor = json.dumps(artifact.payload, indent=2)
            _persist_workspace(workspace)
            kb.record_artifact_run(workspace, route, artifact)
            st.success("Artifact generated. Review and export below.")
        except Exception as exc:
            st.error(f"Artifact generation failed: {exc}")

    _render_generated_artifact(workspace)


def _render_generated_artifact(workspace: WorkspaceSnapshot) -> None:
    artifact: GeneratedArtifact | None = st.session_state.generated_artifact
    if not artifact:
        return

    st.divider()
    st.markdown(f"#### Review: {artifact.title}")
    if artifact.renderer == "svg":
        svg_bytes, _, _ = render_artifact(
            artifact,
            workspace,
            template_bytes=st.session_state.template_bytes,
        )
        st.markdown(svg_bytes.decode("utf-8"), unsafe_allow_html=True)
    st.text_area(
        "Preview",
        value=artifact.preview_text,
        height=220,
        disabled=True,
        key=f"preview_{workspace.id}",
    )
    editor_text = st.text_area(
        "Edit artifact JSON",
        value=st.session_state.artifact_payload_editor or json.dumps(artifact.payload, indent=2),
        height=320,
        key=f"artifact_editor_{workspace.id}",
    )
    st.session_state.artifact_payload_editor = editor_text

    edit_col, download_col, approve_col = st.columns([1, 1, 1])
    with edit_col:
        if st.button("Save JSON Edits", use_container_width=True):
            try:
                artifact.payload = json.loads(editor_text)
                artifact.preview_text = build_preview_text(artifact.artifact_type, artifact.payload)
                _persist_workspace(workspace)
                st.success("Artifact JSON updated.")
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

    filename_root = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in artifact.title).strip("_") or "artifact"
    export_bytes, mime_type, extension = render_artifact(
        artifact,
        workspace,
        template_bytes=st.session_state.template_bytes,
    )
    with download_col:
        st.download_button(
            "Download Export",
            data=export_bytes,
            file_name=f"{filename_root}{extension}",
            mime=mime_type,
            use_container_width=True,
        )

    with approve_col:
        approver_name = st.text_input(
            "Approver Name",
            value=st.session_state.approver_name,
            key=f"approver_{workspace.id}",
        )
        st.session_state.approver_name = approver_name
        if st.button("Approve for Reuse", use_container_width=True):
            if not approver_name.strip():
                st.error("Approver name is required before approval.")
            else:
                kb = get_knowledge_base()
                kb.approve_artifact(workspace, artifact, approved_by=approver_name.strip())
                artifact.approved = True
                _persist_workspace(workspace)
                st.success("Approved artifact added to the reusable knowledge base.")


def _render_admin_library() -> None:
    kb = get_knowledge_base()
    st.markdown("#### Admin Knowledge Base")
    st.caption("Upload approved templates or exemplars so the copilot can learn beyond the current workspace.")
    st.info(kb.connection_status())

    with st.form("kb_upload_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        title = col1.text_input("Reference title")
        artifact_type = col2.selectbox("Artifact type", [item.value for item in ArtifactType])
        col3, col4 = st.columns(2)
        domain = col3.text_input("Domain", value="generic")
        intent = col4.text_input("Intent", value="presales")
        upload_file = st.file_uploader(
            "Upload approved example/template",
            type=["pdf", "docx", "pptx", "ppt", "txt", "md", "csv", "json"],
            key="kb_upload_file",
        )
        submit = st.form_submit_button("Add to Knowledge Base", type="primary")

    if submit:
        if not title.strip() or not upload_file:
            st.error("Both title and file are required.")
        else:
            try:
                text_value = parse_document(upload_file.name, upload_file.getvalue())
                kb.ingest_uploaded_reference(
                    title=title.strip(),
                    artifact_type=artifact_type,
                    domain=domain.strip().lower() or "generic",
                    intent=intent.strip().lower() or "generic",
                    content_text=text_value,
                    original_name=upload_file.name,
                    file_bytes=upload_file.getvalue(),
                )
                st.success("Approved reference added to the library.")
            except Exception as exc:
                st.error(f"Could not ingest the uploaded reference: {exc}")

    with st.expander("Recent approved references", expanded=False):
        examples = kb.list_examples()[:10]
        if not examples:
            st.caption("No approved references yet.")
        for example in examples:
            st.markdown(
                f"**{example['title']}** | `{example['artifact_type']}` | "
                f"`{example['domain']}` | `{example['intent']}`"
            )
            st.caption(example.get("summary", "")[:260])


def main() -> None:
    _init_state()
    _render_sidebar()

    st.markdown(f"# {APP_TITLE}")
    st.caption(APP_SUBTITLE)

    workspace: WorkspaceSnapshot | None = st.session_state.workspace
    workspace_tab, artifact_tab, admin_tab = st.tabs(
        ["Workspace", "Artifact Studio", "Admin Library"]
    )

    with workspace_tab:
        if not workspace:
            _handle_workspace_creation()
        else:
            _render_workspace_overview(workspace)
            st.divider()
            _render_probe_chat(workspace)

    with artifact_tab:
        if not workspace:
            st.info("Create or open a workspace first.")
        else:
            _render_artifact_studio(workspace)

    with admin_tab:
        _render_admin_library()

if __name__ == "__main__":
    main()
