# Results Display Component
"""
Component for displaying processing results in the Streamlit app.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
import pandas as pd
from datetime import datetime
from core.models import LandRecordRequest as CoreLandRecordRequest
from services.file_service import get_file_service


def results_display(api_client, processing_results):
    """Render the results tab UI.

    Args:
        api_client: TSRAPIClient instance (not used directly but kept for signature compatibility).
        processing_results: List of result dictionaries stored in ``st.session_state.processing_results``.
    """
    st.subheader("📋 Processing Results")

    if not processing_results:
        st.info("No results yet. Process some records to see results here.")
        return

    total = len(processing_results)
    successful = sum(1 for r in processing_results if r.get('success'))
    failed = total - successful

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Processed", total)
    with col2:
        st.metric("✅ Successful", successful)
    with col3:
        st.metric("❌ Failed", failed)

    # Retry failed entries
    if failed > 0:
        st.divider()
        if st.button(f"🔄 Retry {failed} Failed Entries", type="primary"):
            _retry_failed(processing_results, api_client)

    # Results table
    st.divider()
    results_df = pd.DataFrame(processing_results)
    display_df = results_df[[
        'district', 'taluka', 'village', 'survey', 'success', 'error'
    ]].copy()
    display_df['status'] = display_df['success'].map({True: '✅ Success', False: '❌ Failed'})
    display_df = display_df.drop(columns=['success'])
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Export CSV
    csv = results_df.to_csv(index=False)
    st.download_button(
        "📥 Download Results CSV",
        data=csv,
        file_name=f"tsr_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )

    # Download all documents ZIP
    success_count = sum(1 for r in processing_results if r.get('success'))
    if success_count > 0:
        st.divider()
        st.subheader("📥 Download All TSR Documents (ZIP)")
        file_service = get_file_service()
        files_to_zip = {}
        for result in processing_results:
            if result.get('success'):
                core_req = CoreLandRecordRequest(
                    district=result['district'],
                    taluka=result['taluka'],
                    village=result['village'],
                    survey_number=result['survey']
                )
                if result.get('docx_content'):
                    filename = file_service.generate_filename(core_req, file_type='docx', prefix='TSR')
                    files_to_zip[filename] = result['docx_content']
                if result.get('pdf_content'):
                    filename = file_service.generate_filename(core_req, file_type='pdf', prefix='Original')
                    files_to_zip[filename] = result['pdf_content']
        zip_data = file_service.create_zip(files_to_zip, "tsr_documents.zip")
        st.download_button(
            "📥 Download All TSR Documents (ZIP)",
            data=zip_data,
            file_name="tsr_documents.zip",
            mime="application/zip",
        )

    # Individual downloads
    st.divider()
    st.subheader("📄 Individual Downloads")
    for idx, result in enumerate(processing_results):
        if result.get('success') and result.get('docx_content'):
            with st.expander(f"Row {result.get('row_idx', idx)}: {result['district']}, {result['taluka']}, {result['village']}, {result['survey']}"):
                st.download_button(
                    "Download TSR",
                    data=result['docx_content'],
                    file_name=f"{result['district']}_{result['taluka']}_{result['village']}_{result['survey']}_TSR.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        if result.get('success') and result.get('pdf_content'):
            with st.expander(f"Original PDF: {result['district']}, {result['taluka']}, {result['village']}, {result['survey']}"):
                st.download_button(
                    "Download Original PDF",
                    data=result['pdf_content'],
                    file_name=f"{result['district']}_{result['taluka']}_{result['village']}_{result['survey']}_Original.pdf",
                    mime="application/pdf",
                )


def _retry_failed(processing_results, api_client):
    """Retry all failed entries and update ``processing_results`` in place."""
    failed_indices = [i for i, r in enumerate(processing_results) if not r.get('success')]
    if not failed_indices:
        return
    progress = st.progress(0)
    status = st.empty()
    max_workers = st.secrets.get("MAX_WORKERS", 20)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                _process_record,
                api_client,
                processing_results[i]['district'],
                processing_results[i]['taluka'],
                processing_results[i]['village'],
                processing_results[i]['survey'],
                processing_results[i].get('row_idx')
            ): i for i in failed_indices
        }
        for completed, future in enumerate(as_completed(future_to_idx), start=1):
            idx = future_to_idx[future]
            try:
                new_result = future.result()
                processing_results[idx] = new_result
            except Exception as e:
                st.error(f"Error retrying item {idx}: {e}")
            progress.progress(completed / len(failed_indices))
            status.text(f"Retried {completed}/{len(failed_indices)} records")
    st.success("Retry complete!")
    st.rerun()


def _process_record(client, district, taluka, village, survey, row_idx=None):
    """Helper to call the API for a single record (same as in batch component)."""
    from app.api_client import TSRAPIClient, APIResponse
    try:
        response: APIResponse = client.process_record(
            district=district, taluka=taluka, village=village, survey_number=survey
        )
        docx_path = None
        pdf_path = None
        if response.success:
            if response.docx_content:
                docx_path = f"{district}_{taluka}_{village}_{survey}_TSR.docx"
            if response.pdf_content:
                pdf_path = f"{district}_{taluka}_{village}_{survey}_Original.pdf"
        return {
            "row_idx": row_idx,
            "district": district,
            "taluka": taluka,
            "village": village,
            "survey": survey,
            "success": response.success,
            "docx_path": docx_path,
            "docx_content": response.docx_content if response.success else None,
            "pdf_path": pdf_path,
            "pdf_content": response.pdf_content if response.success else None,
            "error": response.error,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "row_idx": row_idx,
            "district": district,
            "taluka": taluka,
            "village": village,
            "survey": survey,
            "success": False,
            "docx_path": None,
            "docx_content": None,
            "pdf_path": None,
            "pdf_content": None,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
