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
from utils.survey_utils import convert_survey_number



def batch_processing_form(api_client: TSRAPIClient, max_workers: int = 20) -> None:
    """Render the batch processing UI for Excel file uploads.

    Args:
        api_client: Initialized TSRAPIClient instance for making API calls.
        max_workers: Number of parallel workers for processing. Defaults to 20.
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

            # AI-based column detection
            st.divider()
            st.subheader("🤖 AI Column Mapping")
            
            # Use AI to detect columns
            detected_mapping, confidence_report = auto_detect_columns(df)
            
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

            # Filter to only valid rows (all required fields present)
            if mapping_valid:
                # Create mask for valid rows
                valid_mask = (
                    df[district_col].notna() & 
                    df[district_col].astype(str).str.strip().ne('') &
                    df[taluka_col].notna() & 
                    df[taluka_col].astype(str).str.strip().ne('') &
                    df[village_col].notna() & 
                    df[village_col].astype(str).str.strip().ne('') &
                    df[survey_col].notna() & 
                    df[survey_col].astype(str).str.strip().ne('')
                )
                
                valid_df = df[valid_mask].copy()
                invalid_count = len(df) - len(valid_df)
                
                if invalid_count > 0:
                    st.info(f"📋 {len(valid_df)} valid records found ({invalid_count} rows skipped due to empty values)")
                else:
                    st.info(f"📋 All {len(valid_df)} records are valid")
                
                if len(valid_df) == 0:
                    st.error("❌ No valid records found. Please ensure all required columns have values.")
                    mapping_valid = False

            # Process button
            st.divider()
            if st.button("🚀 Start Batch Processing", type="primary", disabled=not mapping_valid):
                _process_batch(
                    api_client=api_client,
                    df=valid_df,  # Use filtered DataFrame
                    district_col=district_col,
                    taluka_col=taluka_col,
                    village_col=village_col,
                    survey_col=survey_col,
                    max_workers=max_workers,
                    start_row=1
                )

        except Exception as e:
            st.error(f"❌ Error reading Excel file: {str(e)}")
    
    # Display persistent batch results (outside the file upload block)
    _display_batch_results(api_client, max_workers)


def _display_batch_results(api_client: TSRAPIClient, max_workers: int = 20) -> None:
    """Display batch results with Download ZIP and Retry buttons."""
    if "batch_results" not in st.session_state or not st.session_state.batch_results:
        return
    
    results = st.session_state.batch_results
    summary = st.session_state.get("batch_summary", {})
    
    st.divider()
    st.subheader("📦 Batch Results")
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total", summary.get("total", len(results)))
    with col2:
        st.metric("✅ Successful", summary.get("successful", sum(1 for r in results if r.get("success"))))
    with col3:
        st.metric("❌ Failed", summary.get("failed", sum(1 for r in results if not r.get("success"))))
    
    if "duration" in summary:
        st.info(f"⏱️ Total time: {_format_duration(summary['duration'])}")
    
    # Download ZIP button
    successful_results = [r for r in results if r.get("success")]
    if successful_results:
        from services.file_service import get_file_service
        from core.models import LandRecordRequest as CoreLandRecordRequest
        
        file_service = get_file_service()
        files_to_zip = {}
        
        for result in successful_results:
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
        
        if files_to_zip:
            if "batch_zip_data" not in st.session_state:
                st.session_state.batch_zip_data = file_service.create_zip(files_to_zip, "tsr_documents.zip")
            
            zip_data = st.session_state.batch_zip_data
            # Use summary timestamp to make key unique per batch run
            batch_id = st.session_state.get("batch_summary", {}).get("total", 0)
            st.download_button(
                "📥 Download All TSR Documents (ZIP)",
                data=zip_data,
                file_name="tsr_documents.zip",
                mime="application/zip",
                key=f"batch_zip_download_{batch_id}_{len(successful_results)}"
            )
    
    # Retry failed button
    failed_count = sum(1 for r in results if not r.get("success"))
    if failed_count > 0:
        if st.button(f"🔄 Retry {failed_count} Failed Entries", type="primary", key=f"batch_retry_btn_{failed_count}"):
            _retry_failed_entries(api_client, results, max_workers)


def _retry_failed_entries(api_client: TSRAPIClient, results: List[Dict[str, Any]], max_workers: int = 20) -> None:
    """Retry all failed entries."""
    failed_indices = [i for i, r in enumerate(results) if not r.get("success")]
    if not failed_indices:
        return
    
    progress = st.progress(0)
    status = st.empty()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                _process_single_record,
                api_client,
                results[i]['district'],
                results[i]['taluka'],
                results[i]['village'],
                results[i]['survey'],
                results[i].get('row_idx', i)
            ): i for i in failed_indices
        }
        
        for completed, future in enumerate(as_completed(future_to_idx), start=1):
            idx = future_to_idx[future]
            try:
                new_result = future.result()
                st.session_state.batch_results[idx] = new_result
            except Exception as e:
                st.error(f"Error retrying item {idx}: {e}")
            progress.progress(completed / len(failed_indices))
            status.text(f"Retried {completed}/{len(failed_indices)} records")
    
    # Update summary
    results = st.session_state.batch_results
    st.session_state.batch_summary["successful"] = sum(1 for r in results if r.get("success"))
    st.session_state.batch_summary["failed"] = sum(1 for r in results if not r.get("success"))
    
    st.success("Retry complete!")
    
    # Invalidate zip cache since results changed
    if "batch_zip_data" in st.session_state:
        del st.session_state.batch_zip_data
        
    st.rerun()


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

    # Clear previous results immediately to avoid confusion
    if "batch_results" in st.session_state:
        del st.session_state.batch_results
    if "batch_summary" in st.session_state:
        del st.session_state.batch_summary
    if "batch_zip_data" in st.session_state:
        del st.session_state.batch_zip_data

    st.info(f"🔄 Processing {total_records} records")
    
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
            # Convert survey number to proper format before processing
            survey_number = convert_survey_number(str(row[survey_col]).strip())
            future = executor.submit(
                _process_single_record,
                api_client,
                str(row[district_col]).strip(),
                str(row[taluka_col]).strip(),
                str(row[village_col]).strip(),
                survey_number,
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
                    "survey": convert_survey_number(row[survey_col]),
                    "success": False,
                    "docx_content": None,
                    "pdf_content": None,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                })

            # Update session state immediately so Results tab can show progress
            st.session_state.batch_results = results.copy()
            st.session_state.batch_summary = {
                "total": total_records,
                "successful": successful,
                "failed": failed,
                "in_progress": True,
                "completed": completed_count
            }

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

    # Store final results in session state
    st.session_state.batch_results = results
    
    st.session_state.batch_summary = {
        "total": total_records,
        "successful": successful,
        "failed": failed,
        "duration": elapsed_time,
        "in_progress": False,
        "completed": total_records
    }

    # Display summary
    st.divider()
    st.subheader("📊 Batch Processing Complete")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Processed", total_records)
    with col2:
        st.metric("✅ Successful", successful)
    with col3:
        st.metric("❌ Failed", failed)
    
    st.info(f"⏱️ Total time: {_format_duration(elapsed_time)}")

    if successful == total_records:
        st.success("🎉 All records processed successfully!")
    elif successful > 0:
        st.warning(f"⚠️ {failed} records failed.")
    else:
        st.error("❌ All records failed. Please check your inputs and API status.")
    
    # Force a rerun to ensure results are displayed correctly in the main view
    st.rerun()


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

