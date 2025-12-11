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
import pandas as pd
from io import BytesIO
from datetime import datetime


def results_display(api_client, processing_results):
    """Render the results tab UI.

    Args:
        api_client: TSRAPIClient instance (not used directly but kept for signature compatibility).
        processing_results: List of result dictionaries (legacy, not used).
    """
    st.subheader("📋 Batch Processing Results")
    
    # Check if batch results exist
    if "batch_results" not in st.session_state or not st.session_state.batch_results:
        st.info("""
        **No batch processing results available yet.**
        
        - **Single Record Results**: Stay visible in the **Single Record** tab after processing
        - **Batch Results**: Process records in the **Batch (Excel)** tab to see results here
        
        Navigate to the **Batch (Excel)** tab to upload and process an Excel file.
        """)
        return
    
    results = st.session_state.batch_results
    summary = st.session_state.get("batch_summary", {})
    
    # Display summary metrics
    st.subheader("📊 Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Records", summary.get("total", len(results)))
    with col2:
        st.metric("✅ Successful", summary.get("successful", sum(1 for r in results if r.get("success"))))
    with col3:
        st.metric("❌ Failed", summary.get("failed", sum(1 for r in results if not r.get("success"))))
    with col4:
        if "duration" in summary:
            total_seconds = int(summary["duration"].total_seconds())
            st.metric("⏱️ Duration", f"{total_seconds}s")
    
    st.divider()
    
    # Filter options
    st.subheader("� Filter Results")
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox(
            "Status Filter",
            ["All", "Successful Only", "Failed Only"],
            key="results_status_filter"
        )
    with col2:
        search_text = st.text_input(
            "Search (District/Taluka/Village/Survey)",
            key="results_search_text",
            placeholder="Enter search term..."
        )
    
    # Filter results based on selection
    filtered_results = results.copy()
    
    if status_filter == "Successful Only":
        filtered_results = [r for r in filtered_results if r.get("success")]
    elif status_filter == "Failed Only":
        filtered_results = [r for r in filtered_results if not r.get("success")]
    
    if search_text:
        search_lower = search_text.lower()
        filtered_results = [
            r for r in filtered_results
            if search_lower in r.get("district", "").lower()
            or search_lower in r.get("taluka", "").lower()
            or search_lower in r.get("village", "").lower()
            or search_lower in str(r.get("survey", "")).lower()
        ]
    
    st.caption(f"Showing {len(filtered_results)} of {len(results)} records")
    
    # Convert results to DataFrame for display
    if filtered_results:
        df_data = []
        for r in filtered_results:
            df_data.append({
                "Row": r.get("row_idx", "N/A"),
                "District": r.get("district", ""),
                "Taluka": r.get("taluka", ""),
                "Village": r.get("village", ""),
                "Survey No.": r.get("survey", ""),
                "Status": "✅ Success" if r.get("success") else "❌ Failed",
                "Error": r.get("error", "") if not r.get("success") else "",
                "Timestamp": r.get("timestamp", "")
            })
        
        df = pd.DataFrame(df_data)
        
        # Display the dataframe
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Row": st.column_config.NumberColumn("Row #", format="%d"),
                "Status": st.column_config.TextColumn("Status"),
                "Error": st.column_config.TextColumn("Error Message", width="large"),
                "Timestamp": st.column_config.TextColumn("Timestamp", width="medium")
            }
        )
        
        # Download results as Excel
        st.divider()
        st.subheader("📥 Export Results")
        
        # Create Excel file in memory
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Results')
        excel_buffer.seek(0)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_filename = f"batch_results_{timestamp}.xlsx"
        
        col1, col2 = st.columns([1, 3])
        with col1:
            st.download_button(
                label="📊 Download Results (Excel)",
                data=excel_buffer,
                file_name=excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_results_excel"
            )
        with col2:
            st.caption("Download the results table as an Excel file for further analysis")
        
        # Link to batch processing tab for document downloads
        st.info("💡 **Tip**: Go to the **Batch (Excel)** tab to download generated TSR documents (ZIP) or retry failed entries.")
    else:
        st.warning("No results match the current filters.")
