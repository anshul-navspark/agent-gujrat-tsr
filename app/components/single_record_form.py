# Single Record Form Component
"""
Component for processing a single land record in the Streamlit app.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
from datetime import datetime
from core.models import LandRecordRequest as CoreLandRecordRequest
from app.api_client import TSRAPIClient, APIResponse


def single_record_form(api_client: TSRAPIClient) -> None:
    """Render the single record processing UI.

    Args:
        api_client: Initialized TSRAPIClient instance for making API calls.
    """
    st.subheader("Process Single Land Record")
    col1, col2 = st.columns(2)
    with col1:
        district = st.text_input("District", key="single_district")
        taluka = st.text_input("Taluka", key="single_taluka")
    with col2:
        village = st.text_input("Village", key="single_village")
        survey = st.text_input("Survey Number", key="single_survey")

    if st.button("🚀 Generate TSR", type="primary"):
        if not all([district, taluka, village, survey]):
            st.error("⚠️ Please fill in all fields")
            return
        with st.spinner("Processing via API..."):
            start_time = datetime.now()
            result = process_single_record_api(
                api_client, district, taluka, village, survey
            )
            duration = datetime.now() - start_time
            st.session_state.processing_results.append(result)
            if result["success"]:
                st.success(f"✅ TSR generated successfully in {duration}!\n")
                if result.get("docx_content"):
                    st.download_button(
                        "📥 Download TSR (DOCX)",
                        data=result["docx_content"],
                        file_name=f"{district}_{taluka}_{village}_{survey}_TSR.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                if result.get("pdf_content"):
                    st.download_button(
                        "📥 Download Original Record (PDF)",
                        data=result["pdf_content"],
                        file_name=f"{district}_{taluka}_{village}_{survey}_Original.pdf",
                        mime="application/pdf",
                    )
            else:
                st.error(f"❌ Failed: {result['error']}")

def process_single_record_api(
    client: TSRAPIClient,
    district: str,
    taluka: str,
    village: str,
    survey: str,
) -> dict:
    """Helper to call the API and format the response.

    Returns a dict compatible with the existing processing_results schema.
    """
    try:
        response: APIResponse = client.process_record(
            district=district,
            taluka=taluka,
            village=village,
            survey_number=survey,
        )
        docx_path = None
        pdf_path = None
        if response.success:
            if response.docx_content:
                docx_path = f"{district}_{taluka}_{village}_{survey}_TSR.docx"
            if response.pdf_content:
                pdf_path = f"{district}_{taluka}_{village}_{survey}_Original.pdf"
        return {
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
