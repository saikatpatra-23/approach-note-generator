"""Utilities for loading runtime secrets from env or Streamlit secrets."""
from __future__ import annotations

import os


def get_secret(key: str, default: str = "") -> str:
    """Try os.environ (.env) first; fall back to Streamlit secrets."""
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st

        return st.secrets.get(key, default)
    except Exception:
        return default
