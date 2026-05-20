# Gujarat TSR Agent - Streamlit Cloud Version
"""
Streamlit UI that delegates all business logic to services and components.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# CRITICAL: Add project root to sys.path BEFORE any project imports
# This must happen before importing any project modules
_project_root = str(Path(__file__).resolve().parents[1])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
import pandas as pd

# Set up environment variables for translation utils if needed
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

# Import core services and components (AFTER sys.path is set up)
from core.models import LandRecordRequest as CoreLandRecordRequest
from core.clients import get_client_library
from core.anyror_maintenance import (
    is_anyror_maintenance_window,
    maintenance_window_message,
)
from app.api_client import TSRAPIClient, APIResponse
from services.file_service import get_file_service

# Component imports
from app.components.single_record_form import single_record_form
from app.components.batch_processing_form import batch_processing_form
from app.components.results_display import results_display

# Page configuration
st.set_page_config(page_title="Gujarat TSR Agent", page_icon="📄", layout="centered")
st.title("Gujarat Land Record & TSR Generator")
st.caption("Fetch land records and generate Title Search Reports via Cloud API")

# Initialize session state
if "processing_results" not in st.session_state:
    st.session_state.processing_results = []
if "api_client" not in st.session_state:
    st.session_state.api_client = None

# Logging setup
# Configure logging to use IST (UTC+05:30)
from datetime import datetime, timedelta, timezone

def ist_converter(*args):
    """Convert time to IST (Indian Standard Time) for logging."""
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).timetuple()

logging.Formatter.converter = ist_converter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# Configuration from secrets
api_url = st.secrets.get("API_URL", "https://agent-gujarat-tsr-642363716512.asia-south1.run.app")
api_timeout = int(st.secrets.get("API_TIMEOUT", 1200))
max_retries = int(st.secrets.get("API_MAX_RETRIES", 2))
max_workers = int(st.secrets.get("MAX_WORKERS", 30))

# Initialize API client if needed
if st.session_state.api_client is None or st.session_state.api_client.api_url != api_url:
    st.session_state.api_client = TSRAPIClient(
        api_url=api_url, timeout=api_timeout, max_retries=max_retries
    )

# Initialize file service (global singleton)
file_service = get_file_service()

# Helper to format duration
def format_duration(delta: datetime) -> str:
    total_seconds = int(delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    if len(parts) > 1:
        return ", ".join(parts[:-1]) + f" and {parts[-1]}"
    return parts[0]

def _render_client_sidebar() -> None:
    """Render the 'Active Client' picker in the sidebar."""
    library = get_client_library()

    with st.sidebar:
        st.markdown("### Active Client")
        if not library.clients:
            st.warning(
                "No clients.json found. Falling back to hardcoded ABREL defaults. "
                "Add clients.json to the repo root to enable the picker."
            )
            st.session_state.active_client_id = None
            return

        client_ids = list(library.clients.keys())
        display_names = [library.clients[cid].display_name for cid in client_ids]

        # Pre-select default (or first) the very first time
        if "active_client_id" not in st.session_state:
            st.session_state.active_client_id = (
                library.default_client_id or client_ids[0]
            )

        current_idx = (
            client_ids.index(st.session_state.active_client_id)
            if st.session_state.active_client_id in client_ids
            else 0
        )

        selected_idx = st.selectbox(
            "Generating TSR for",
            options=range(len(client_ids)),
            format_func=lambda i: display_names[i],
            index=current_idx,
            key="sidebar_client_selector",
        )
        st.session_state.active_client_id = client_ids[selected_idx]

        selected = library.clients[st.session_state.active_client_id]
        with st.expander("View details", expanded=False):
            st.write(f"**Name:** {selected.client_name}")
            if selected.client_cin:
                st.write(f"**CIN:** {selected.client_cin}")
            st.write(f"**Address:** {selected.client_address}")
            if selected.kind_attn:
                st.write(f"**Attn:** {selected.kind_attn}")
            st.write(f"**Ref prefix:** {selected.ref_prefix or 'ABREL'}")

        st.caption("To add or edit a client, edit `clients.json` and redeploy.")


_render_client_sidebar()

# Show maintenance-window banner during the daily AnyRoR outage so users
# aren't confused by scrape timeouts.
if is_anyror_maintenance_window(datetime.now(timezone.utc)):
    st.warning(f"⚠️ {maintenance_window_message()}")

# Main UI – three tabs delegating to components
tab1, tab2, tab3 = st.tabs(["📄 Single Record", "📊 Batch (Excel)", "📋 Results"])

with tab1:
    single_record_form(st.session_state.api_client)

with tab2:
    batch_processing_form(st.session_state.api_client, max_workers=max_workers)

with tab3:
    results_display(st.session_state.api_client, st.session_state.processing_results)
