"""jarvis_generate.py - Direct approach note generation bypassing Streamlit UI"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from brd_parser import parse_document
from schemas import WorkspaceSnapshot, SourceDocument
from workspace_store import WorkspaceStore
from knowledge_base import KnowledgeBaseService
from intent_router import IntentRouter, TemplateCatalog
from copilot_session import OpportunityCopilotSession
import uuid

BRD_PATH = Path(__file__).parent / "sample_brd_dealer_lead_capture.txt"
OUTPUT_PATH = Path(__file__).parent / "output_approach_note.md"

print("=== Jarvis: Approach Note Generator ===\n")

# 1. Parse BRD
print(f"[1] Parsing BRD...")
brd_text = parse_document(BRD_PATH.name, BRD_PATH.read_bytes())
print(f"    Done — {len(brd_text)} chars\n")

# 2. Create workspace
print("[2] Creating workspace...")
workspace = WorkspaceSnapshot(
    id=str(uuid.uuid4())[:8],
    name="Dealer Mobile App Lead Capture",
    business_context=(
        "Client wants a mobile app for dealers to capture and manage leads on the field. "
        "Dealers should be able to log new leads, track status, set follow-up reminders, "
        "and sync data back to central CRM. Timeline is Q2 2026 delivery."
    ),
    application_name="Mobility App",
    module_name="Lead Management",
    audience="Business Stakeholders",
    domain_hint="Auto-detect",
    output_preference="Balanced detail",
    source_documents=[
        SourceDocument(
            name=BRD_PATH.name,
            role="primary_brd",
            text=brd_text,
            extension="txt",
            file_path=str(BRD_PATH),
        )
    ],
)
print(f"    Workspace id: {workspace.id}\n")

# 3. Infer domain + route
print("[3] Routing...")
catalog = TemplateCatalog()
router = IntentRouter(catalog)
inferred_domain, domain_conf = router.infer_domain(workspace)
workspace.inferred_domain = inferred_domain.replace("_", " ").title() if inferred_domain != "generic" else "Generic Enterprise App"
workspace.inferred_app_type = workspace.application_name
workspace.confidence = round(domain_conf, 2)

artifact_request = "Generate a functional approach note"
route = router.route(artifact_request, workspace)
print(f"    Domain: {workspace.inferred_domain} | Artifact: {route.artifact_type}\n")

# 4. Get template family
candidates = catalog.find_candidates(route.artifact_type, inferred_domain, artifact_request)
template_family = candidates[0] if candidates else catalog.all()[1]  # approach_note_functional
print(f"    Template family: {template_family.name if template_family else 'default'}\n")

# 5. Similar contexts + examples
store = WorkspaceStore()
kb = KnowledgeBaseService()
similar_contexts = store.find_similar(workspace, limit=3)
example_matches = kb.search_examples(workspace.combined_context, domain=inferred_domain, limit=3)

# 6. Generate via copilot session
print("[5] Calling Claude to generate Functional Approach Note...")
copilot = OpportunityCopilotSession()
artifact = copilot.generate_artifact(
    workspace=workspace,
    route=route,
    template_family=template_family,
    request_text=artifact_request,
    examples=example_matches,
    similar_contexts=similar_contexts,
)

print(f"\n[6] Done! Artifact: {artifact.title}")

# Save output
import json
OUTPUT_PATH.write_text(artifact.preview_text or json.dumps(artifact.payload, indent=2), encoding="utf-8")
print(f"    Saved to: {OUTPUT_PATH}\n")
print("=" * 60)
output = artifact.preview_text or json.dumps(artifact.payload, indent=2)
print(output[:2500])
print("=" * 60)
if len(output) > 2500:
    print(f"\n[... {len(output)-2500} more chars saved to file]")
