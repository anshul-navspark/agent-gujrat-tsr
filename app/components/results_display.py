# Results Display Component
"""
Component for displaying processing results in the Streamlit app.

Note: Batch processing results with Download ZIP and Retry buttons are now
displayed directly in the Batch Processing tab.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st


def results_display(api_client, processing_results):
    """Render the results tab UI.

    Args:
        api_client: TSRAPIClient instance (not used directly but kept for signature compatibility).
        processing_results: List of result dictionaries (legacy, not used).
    """
    st.subheader("📋 Results Information")
    
    st.info("""
    **Results are now displayed directly where you process them:**
    
    - **Single Record Results**: Stay visible in the **Single Record** tab after processing
    - **Batch Results**: Displayed in the **Batch (Excel)** tab with Download ZIP and Retry options
    
    Navigate to the appropriate tab to see your results.
    """)
    
    # Show batch results summary if available
    if "batch_results" in st.session_state and st.session_state.batch_results:
        results = st.session_state.batch_results
        summary = st.session_state.get("batch_summary", {})
        
        st.divider()
        st.subheader("📊 Last Batch Processing Summary")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total", summary.get("total", len(results)))
        with col2:
            st.metric("✅ Successful", summary.get("successful", sum(1 for r in results if r.get("success"))))
        with col3:
            st.metric("❌ Failed", summary.get("failed", sum(1 for r in results if not r.get("success"))))
        
        st.caption("Go to the **Batch (Excel)** tab to download documents or retry failed entries.")
