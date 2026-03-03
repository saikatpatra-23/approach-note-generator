import os

from dotenv import load_dotenv

load_dotenv()

# Keep module import side-effect free from Streamlit runtime requirements.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_TOKENS_PROBE = 1024
MAX_TOKENS_GENERATE = 8192
MAX_BRD_CHARS = 80_000
MAX_PROBE_ROUNDS = 12
MIN_PROBE_ROUNDS = 4  # minimum exchanges before "Generate" button appears

# ── Domain constants ────────────────────────────────────────────────────────

APPLICATIONS = [
    "Siebel OLTP (CRM)",
    "Siebel Analytics / OBIA (OLAP)",
    "Siebel Mobility",
    "BIP (BI Publisher)",
    "EIM (Enterprise Integration Manager)",
    "SAP / SAP Hana",
    "DMS (Dealer Management System)",
    "CTI (Computer Telephony Integration)",
    "DocuSign / eSign",
]

MODULES = [
    "Service Request (SR)",
    "Activity",
    "Quote / Order",
    "Asset Management",
    "Campaign",
    "Contact / Account",
    "Warranty",
    "Loyalty",
    "Complaint Management",
    "Smartscript",
    "Workflow / Assignment Manager",
    "BIP Reports",
    "EIM Jobs",
    "Interfaces (Inbound / Outbound)",
]

TECHNICAL_COMPONENTS = [
    "Business Component (BC)",
    "Business Object (BO)",
    "Applet",
    "View / Screen",
    "Workflow Process",
    "Business Service",
    "Assignment Rules",
    "EIM Table Mapping",
    "BIP Report Template",
    "Interface Mapping / Web Service",
    "Smartscript",
    "LOV (List of Values)",
    "Server Component / Job",
    "Access Control / Responsibility",
]

BUSINESS_UNITS = [
    "TMPC (Tata Motors Passenger Cars)",
    "TMCV (Tata Motors Commercial Vehicles)",
    "TPEM (Tata Power Engineering & Machines)",
    "EV (Electric Vehicles)",
    "Both TMPC & TMCV",
    "All BUs",
]

CHANGE_TYPES = ["New Enhancement", "Repeat / Reopen", "Bug Fix", "Process Change"]

TIMELINES = ["< 3 Months", "> 3 Months", "Ongoing / Maintenance"]

COMPLEXITIES = ["Low", "Medium", "High"]

PROJECTS = ["Tata Motors CRM (Siebel)", "Other"]
