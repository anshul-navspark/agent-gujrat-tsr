# Batch Processing Form Component
"""
Component for processing multiple land records from Excel files in the Streamlit app.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from core.models import LandRecordRequest as CoreLandRecordRequest
from app.api_client import TSRAPIClient, APIResponse
from utils.ai_column_detector import AIColumnDetector, auto_detect_columns



def batch_processing_form(api_client: TSRAPIClient) -> None:
    """Render the batch processing UI for Excel file uploads.

    Args:
        api_client: Initialized TSRAPIClient instance for making API calls.
    """
    st.subheader("📊 Batch Processing (Excel)")
    st.caption("Upload an Excel file with land records to process in batch.")

    # File uploader
    uploaded_file = st.file_uploader(
        "Upload Excel File",
        type=["xlsx", "xls"],
        key="batch_file_uploader",
        help="Excel file should contain columns for District, Taluka, Village, and Survey Number"
    )

    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            st.success(f"✅ Loaded {len(df)} records from {uploaded_file.name}")

            # Display preview
            with st.expander("📋 Preview Data", expanded=True):
                st.dataframe(df.head(10), use_container_width=True, hide_index=True)

            # AI-based column detection
            st.divider()
            st.subheader("🤖 AI Column Mapping")
            
            # Use AI to detect columns
            detected_mapping, confidence_report = auto_detect_columns(df)
            
            # Show AI detection report
            with st.expander("🔍 AI Detection Report", expanded=False):
                st.text(confidence_report)
            
            # Prepare available columns with empty option
            available_columns = [""] + list(df.columns)
            
            # Function to get index for detected column
            def get_detected_index(field: str) -> int:
                detected_col = detected_mapping.get(field)
                if detected_col and detected_col in df.columns:
                    return list(df.columns).index(detected_col) + 1  # +1 for empty option
                return 0

            col1, col2 = st.columns(2)
            with col1:
                district_col = st.selectbox(
                    "District Column",
                    available_columns,
                    index=get_detected_index('district'),
                    key="batch_district_col"
                )
                taluka_col = st.selectbox(
                    "Taluka Column",
                    available_columns,
                    index=get_detected_index('taluka'),
                    key="batch_taluka_col"
                )
            with col2:
                village_col = st.selectbox(
                    "Village Column",
                    available_columns,
                    index=get_detected_index('village'),
                    key="batch_village_col"
                )
                survey_col = st.selectbox(
                    "Survey Number Column",
                    available_columns,
                    index=get_detected_index('survey'),
                    key="batch_survey_col"
                )

            # Validate mapping
            mapping_valid = all([district_col, taluka_col, village_col, survey_col])
            if not mapping_valid:
                st.warning("⚠️ Please map all required columns before processing.")

            # Process button
            st.divider()
            if st.button("🚀 Start Batch Processing", type="primary", disabled=not mapping_valid):
                _process_batch(
                    api_client=api_client,
                    df=df,
                    district_col=district_col,
                    taluka_col=taluka_col,
                    village_col=village_col,
                    survey_col=survey_col,
                    max_workers=20,
                    start_row=1
                )

        except Exception as e:
            st.error(f"❌ Error reading Excel file: {str(e)}")


def _process_batch(
    api_client: TSRAPIClient,
    df: pd.DataFrame,
    district_col: str,
    taluka_col: str,
    village_col: str,
    survey_col: str,
    max_workers: int,
    start_row: int
) -> None:
    """Process all records in the batch using parallel API calls.

    Args:
        api_client: TSRAPIClient instance for making API calls.
        df: DataFrame containing the records.
        district_col: Column name for district.
        taluka_col: Column name for taluka.
        village_col: Column name for village.
        survey_col: Column name for survey number.
        max_workers: Number of parallel workers.
        start_row: Row to start processing from (1-indexed).
    """
    # Slice the dataframe based on start_row
    df_to_process = df.iloc[start_row - 1:].reset_index(drop=True)
    total_records = len(df_to_process)

    if total_records == 0:
        st.warning("No records to process.")
        return

    st.info(f"🔄 Processing {total_records} records with {max_workers} parallel workers...")

    # Progress tracking
    progress_bar = st.progress(0)
    status_container = st.empty()
    metrics_container = st.container()

    # Results tracking
    results: List[Dict[str, Any]] = []
    successful = 0
    failed = 0
    start_time = datetime.now()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_row = {}
        for idx, row in df_to_process.iterrows():
            future = executor.submit(
                _process_single_record,
                api_client,
                str(row[district_col]).strip(),
                str(row[taluka_col]).strip(),
                str(row[village_col]).strip(),
                str(row[survey_col]).strip(),
                idx + start_row  # Original row index
            )
            future_to_row[future] = idx

        # Collect results as they complete
        for completed_count, future in enumerate(as_completed(future_to_row), start=1):
            try:
                result = future.result()
                results.append(result)

                if result["success"]:
                    successful += 1
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                idx = future_to_row[future]
                row = df_to_process.iloc[idx]
                results.append({
                    "row_idx": idx + start_row,
                    "district": str(row[district_col]).strip(),
                    "taluka": str(row[taluka_col]).strip(),
                    "village": str(row[village_col]).strip(),
                    "survey": str(row[survey_col]).strip(),
                    "success": False,
                    "docx_content": None,
                    "pdf_content": None,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                })

            # Update progress
            progress = completed_count / total_records
            progress_bar.progress(progress)
            status_container.text(
                f"Processed {completed_count}/{total_records} records | "
                f"✅ {successful} successful | ❌ {failed} failed"
            )

    # Final summary
    elapsed_time = datetime.now() - start_time
    progress_bar.progress(1.0)

    # Store results in session state
    st.session_state.processing_results.extend(results)

    # Display summary
    st.divider()
    st.subheader("📊 Batch Processing Complete")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Processed", total_records)
    with col2:
        st.metric("✅ Successful", successful)
    with col3:
        st.metric("❌ Failed", failed)
    with col4:
        st.metric("⏱️ Duration", _format_duration(elapsed_time))

    if successful == total_records:
        st.success("🎉 All records processed successfully!")
    elif successful > 0:
        st.warning(f"⚠️ {failed} records failed. Check the Results tab for details and retry options.")
    else:
        st.error("❌ All records failed. Please check your inputs and API status.")

    st.info("💡 Go to the **Results** tab to download documents and retry failed entries.")


def _process_single_record(
    client: TSRAPIClient,
    district: str,
    taluka: str,
    village: str,
    survey: str,
    row_idx: int
) -> Dict[str, Any]:
    """Process a single record via the API.

    Args:
        client: TSRAPIClient instance.
        district: District name.
        taluka: Taluka name.
        village: Village name.
        survey: Survey number.
        row_idx: Row index from the original Excel file.

    Returns:
        Dictionary with processing result.
    """
    try:
        response: APIResponse = client.process_record(
            district=district,
            taluka=taluka,
            village=village,
            survey_number=survey
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


def _format_duration(delta) -> str:
    """Format a timedelta into a human-readable string.

    Args:
        delta: timedelta object.

    Returns:
        Formatted duration string like "x hours, y minutes and z seconds".
    """
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

