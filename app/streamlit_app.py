import os
import io
import shutil
import tempfile
import zipfile
import pandas as pd
import streamlit as st
import logging
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from collections import deque
from typing import Deque, Dict, Any

# Module-level, thread-safe event queue to avoid touching Streamlit from worker threads
PIPELINE_EVENTS: Deque[Dict[str, Any]] = deque()
PIPELINE_EVENTS_LOCK = threading.Lock()

# Ensure project root is on sys.path for package imports when running via Streamlit
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.processing_service import LandRecordProcessor
from services.parallel_processing_service import ParallelProcessingService, PipelineTask, PipelineStats
from services.ai_batch_service import AIBatchService
from utils.ai_column_detector import auto_detect_columns
from tsr_generator.utils.text_utils import translate_gujarati_text


st.set_page_config(page_title="Gujarat TSR", page_icon="📄", layout="centered")
st.title("Gujarat Land Record & TSR")
st.caption("Fetch land records (PDF) and generate Title Search Reports (DOCX) without coding.")

# Initialize session state for tracking processing
if 'processing_results' not in st.session_state:
    st.session_state.processing_results = []
if 'processing_log' not in st.session_state:
    st.session_state.processing_log = []
if 'current_sheet' not in st.session_state:
    st.session_state.current_sheet = None
if 'processing_paused' not in st.session_state:
    st.session_state.processing_paused = False
if 'processing_history' not in st.session_state:
    st.session_state.processing_history = []
if 'processing_start_time' not in st.session_state:
    st.session_state.processing_start_time = None
if 'processing_speeds' not in st.session_state:
    st.session_state.processing_speeds = []
if 'all_records' not in st.session_state:
    st.session_state.all_records = []
if 'records_summary' not in st.session_state:
    st.session_state.records_summary = []
if 'pipeline_service' not in st.session_state:
    st.session_state.pipeline_service = None
if 'ai_batch_service' not in st.session_state:
    st.session_state.ai_batch_service = None

# Simple user preference persistence for workflow mode
PREFS_FILE = 'user_prefs.json'

def _load_user_prefs():
    try:
        with open(PREFS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_user_prefs(prefs: dict):
    try:
        with open(PREFS_FILE, 'w', encoding='utf-8') as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# Ensure logs dir and basic logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(threadName)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/app_streamlit.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

with st.sidebar:
    st.header("Settings")
    output_dir = st.text_input("Output directory", value="output")
    headless = st.toggle("Run headless (recommended)", value=True)
    regenerate_pdf = st.toggle("Re-fetch PDFs even if they exist", value=False)
    if regenerate_pdf:
        st.info("🔄 Will re-fetch all PDFs regardless of existing files")
    else:
        st.success("📁 Will skip existing PDFs (faster processing)")
    generate_tsr = st.toggle("Generate TSR after fetching PDF", value=True)
    st.subheader("Workflow Mode")
    if 'use_agent_mode' not in st.session_state:
        prefs = _load_user_prefs()
        st.session_state.use_agent_mode = bool(prefs.get('use_agent_mode', False))
    use_agent_mode = st.toggle("🤖 Agentic Mode (beta)", value=st.session_state.use_agent_mode, help="Switch between Agentic and Legacy TSR generation")
    st.session_state.use_agent_mode = use_agent_mode
    _save_user_prefs({'use_agent_mode': use_agent_mode})
    
    # New parallel processing settings
    st.subheader("Performance Settings")
    use_pipeline = st.toggle("🚀 High-Performance Pipeline", value=False, help="Use advanced pipeline architecture for maximum speed (RECOMMENDED)")
    
    if use_pipeline:
        st.success("⚡ Pipeline mode: PDF fetching and TSR generation run in parallel!")
        col1, col2 = st.columns(2)
        with col1:
            max_pdf_workers = st.slider("PDF Workers", min_value=1, max_value=3, value=2, help="Concurrent PDF fetchers")
        with col2:
            max_tsr_workers = st.slider("TSR Workers", min_value=2, max_value=6, value=4, help="Concurrent TSR generators")
    else:
        use_parallel = st.toggle("Enable parallel processing", value=False, help="Process multiple records simultaneously")
        max_workers = st.slider("Max parallel workers", min_value=2, max_value=8, value=4, help="Number of simultaneous processes")
        selenium_max_sessions = st.slider(
            "Max Selenium sessions",
            min_value=1,
            max_value=4,
            value=1,
            help="Limit concurrent ChromeDriver sessions to reduce crashes and port conflicts"
        )
    
    # Sheet selection
    st.subheader("Excel Sheet Selection")
    process_all_sheets = st.toggle("Process all sheets", value=True, help="Process all sheets in the Excel file")
    # Note: Sheet selection will be dynamic based on uploaded file

processor = LandRecordProcessor(output_base_dir=output_dir, headless=headless)

def english_to_gujarati_inputs(district_en: str, taluka_en: str, village_en: str, survey_raw: str):
    """Translate simple English inputs to Gujarati using existing dictionary.

    We piggyback on translate_gujarati_text by mapping English→Gujarati via a small reverse map.
    This is heuristic and intended for common districts/talukas/villages already present.
    """
    # Minimal reverse map for known terms used in utils (extend as needed)
    reverse = {
        'Bhavnagar': 'ભાવનગર',
        'Talaja': 'તળાજા',
        'Datha': 'દાઠા',
        'Kutch': 'કચ્છ',
        'Kachchh': 'કચ્છ',
        'Abdasa': 'અબડાસા',
        'Jamnagar': 'જામનગર',
        'Jamjodhpur': 'જામજોધપુર',
        'Hothiji Khadaba': 'હોથીજી ખડબા',
        'Hothiji Khadba': 'હોથીજી ખડબા',
        'Trambau': 'ત્રંબો',
        # Trambo mapping example used in data
        'Trambo - 033': 'ત્રંબો - 033',
        'Trambo': 'ત્રંબો - 033',
        'Trambau': 'ત્રંબો - 033',
    }

    def to_guj(name: str) -> str:
        name = (name or '').strip()
        return reverse.get(name, name)

    # Survey is often already in Gujarati form upstream, keep as is
    return to_guj(district_en), to_guj(taluka_en), to_guj(village_en), (survey_raw or '').strip()

def process_single_record_parallel(args):
    """Process a single record for parallel execution"""
    try:
        semaphore, district_guj, taluka_guj, village_guj, survey_guj, regenerate_pdf, generate_tsr = args
        # Throttle Selenium concurrency to avoid ChromeDriver instability
        with semaphore:
            result = processor.fetch_pdf_and_tsr(
                district_guj=district_guj,
                taluka_guj=taluka_guj,
                village_guj=village_guj,
                survey_number_guj=survey_guj,
                regenerate_pdf=regenerate_pdf,
                generate_tsr=generate_tsr,
            )
        return {
            'district': district_guj,
            'taluka': taluka_guj,
            'village': village_guj,
            'survey': survey_guj,
            'success': result.success,
            'pdf_path': result.pdf_path,
            'tsr_path': result.tsr_path,
            'error': result.error,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'district': district_guj,
            'taluka': taluka_guj,
            'village': village_guj,
            'survey': survey_guj,
            'success': False,
            'pdf_path': None,
            'tsr_path': None,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

def categorize_error(error_msg):
    """Categorize errors and provide recovery suggestions"""
    error_msg_lower = str(error_msg).lower()
    
    if 'connection refused' in error_msg_lower or 'chromedriver' in error_msg_lower:
        return {
            'category': 'Driver Issue',
            'severity': 'High',
            'suggestion': 'Try reducing Max Selenium sessions to 1, or restart the application'
        }
    elif 'captcha' in error_msg_lower:
        return {
            'category': 'CAPTCHA Issue',
            'severity': 'Medium', 
            'suggestion': 'The website CAPTCHA failed. This is usually temporary - try again'
        }
    elif 'survey' in error_msg_lower and 'not found' in error_msg_lower:
        return {
            'category': 'Data Issue',
            'severity': 'Low',
            'suggestion': 'Survey number not found. Check if the survey number is correct'
        }
    elif 'timeout' in error_msg_lower:
        return {
            'category': 'Network Issue',
            'severity': 'Medium',
            'suggestion': 'Network timeout. Check internet connection and try again'
        }
    else:
        return {
            'category': 'General Error',
            'severity': 'Medium',
            'suggestion': 'Try processing this record individually or check the logs'
        }

def log_processing_event(event_type, message, details=None):
    """Log processing events to session state"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'event_type': event_type,
        'message': message,
        'details': details
    }
    st.session_state.processing_log.append(log_entry)

def calculate_processing_stats(completed, total, start_time):
    """Calculate processing statistics"""
    if not start_time or completed == 0:
        return None
    
    elapsed = (datetime.now() - start_time).total_seconds()
    speed = completed / elapsed  # records per second
    
    # Store recent speeds for smoothing
    st.session_state.processing_speeds.append(speed)
    if len(st.session_state.processing_speeds) > 10:
        st.session_state.processing_speeds.pop(0)
    
    avg_speed = sum(st.session_state.processing_speeds) / len(st.session_state.processing_speeds)
    remaining = total - completed
    eta_seconds = remaining / avg_speed if avg_speed > 0 else 0
    
    return {
        'elapsed': elapsed,
        'speed': avg_speed,
        'eta_seconds': eta_seconds,
        'records_per_minute': avg_speed * 60
    }

def update_records_summary(records_to_process):
    """Update the records summary with current batch"""
    st.session_state.records_summary = []
    for record in records_to_process:
        summary_record = {
            'row_idx': record['row_idx'],
            'sheet_name': record['sheet_name'],
            'district': record['district'],
            'taluka': record['taluka'],
            'village': record['village'],
            'survey': record['survey'],
            'status': 'Queued',
            'error': None,
            'pdf_path': None,
            'tsr_path': None,
            'processing_time': None,
            'timestamp': None
        }
        st.session_state.records_summary.append(summary_record)

def update_record_status(row_idx, sheet_name, status, error=None, pdf_path=None, tsr_path=None, processing_time=None):
    """Update the status of a specific record"""
    for record in st.session_state.records_summary:
        if record['row_idx'] == row_idx and record['sheet_name'] == sheet_name:
            record['status'] = status
            record['error'] = error
            record['pdf_path'] = pdf_path
            record['tsr_path'] = tsr_path
            record['processing_time'] = processing_time
            record['timestamp'] = datetime.now().isoformat()
            break

def pipeline_progress_callback(task: PipelineTask, stats: PipelineStats):
    """Background-thread safe: enqueue events for main thread to apply."""
    try:
        event = {
            'row_idx': task.row_idx,
            'sheet_name': task.sheet_name,
            'district': task.district_guj,
            'taluka': task.taluka_guj,
            'village': task.village_guj,
            'survey': task.survey_number_guj,
            'status': task.status,
            'error': task.error,
            'pdf_path': task.pdf_path,
            'tsr_path': task.tsr_path,
            'timestamp': datetime.now().isoformat(),
        }
        # Append to shared deque under lock (no Streamlit context access)
        with PIPELINE_EVENTS_LOCK:
            PIPELINE_EVENTS.append(event)
    except Exception:
        return

def _apply_pipeline_events():
    """Drain queued events and apply to session_state (main thread only)."""
    updates = []
    with PIPELINE_EVENTS_LOCK:
        while PIPELINE_EVENTS:
            updates.append(PIPELINE_EVENTS.popleft())
    if not updates:
        return
    status_mapping = {
        "queued": "Queued",
        "pdf_fetching": "Running",
        "pdf_ready": "Running",
        "tsr_generating": "Running",
        "completed": "Success",
        "failed": "Failed",
    }
    for ev in updates:
        mapped_status = status_mapping.get(ev['status'], ev['status'])
        update_record_status(
            ev['row_idx'],
            ev['sheet_name'],
            mapped_status,
            error=ev['error'],
            pdf_path=ev['pdf_path'],
            tsr_path=ev['tsr_path'],
        )
        # sync processing_results
        result_dict = {
            'row_idx': ev['row_idx'],
            'sheet_name': ev['sheet_name'],
            'district': ev['district'],
            'taluka': ev['taluka'],
            'village': ev['village'],
            'survey': ev['survey'],
            'success': ev['status'] == "completed",
            'pdf_path': ev['pdf_path'],
            'tsr_path': ev['tsr_path'],
            'error': ev['error'],
            'timestamp': ev['timestamp'],
        }
        existing_idx = None
        for i, result in enumerate(st.session_state.processing_results):
            if (result.get('row_idx') == ev['row_idx'] and result.get('sheet_name') == ev['sheet_name']):
                existing_idx = i
                break
        if existing_idx is not None:
            st.session_state.processing_results[existing_idx] = result_dict
        else:
            st.session_state.processing_results.append(result_dict)

def display_records_summary():
    """Display comprehensive records summary"""
    if not st.session_state.records_summary:
        st.info("No records to display. Process a batch to see the summary.")
        return
    
    st.subheader("📋 Records Summary")
    
    # Summary statistics
    total_records = len(st.session_state.records_summary)
    completed = len([r for r in st.session_state.records_summary if r['status'] in ['Success', 'Failed']])
    successful = len([r for r in st.session_state.records_summary if r['status'] == 'Success'])
    failed = len([r for r in st.session_state.records_summary if r['status'] == 'Failed'])
    queued = len([r for r in st.session_state.records_summary if r['status'] == 'Queued'])
    running = len([r for r in st.session_state.records_summary if r['status'] == 'Running'])
    
    # Display metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total", total_records)
    with col2:
        st.metric("✅ Success", successful)
    with col3:
        st.metric("❌ Failed", failed)
    with col4:
        st.metric("⏳ Queued", queued)
    with col5:
        st.metric("🔄 Running", running)
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["All", "Queued", "Running", "Success", "Failed"])
    with col2:
        sheet_filter = st.selectbox("Filter by Sheet", ["All"] + list(set([r['sheet_name'] for r in st.session_state.records_summary])))
    with col3:
        show_errors_only = st.checkbox("Show only records with errors")
    
    # Filter records
    filtered_records = st.session_state.records_summary.copy()
    
    if status_filter != "All":
        filtered_records = [r for r in filtered_records if r['status'] == status_filter]
    
    if sheet_filter != "All":
        filtered_records = [r for r in filtered_records if r['sheet_name'] == sheet_filter]
    
    if show_errors_only:
        filtered_records = [r for r in filtered_records if r['error'] is not None]
    
    if not filtered_records:
        st.info("No records match the selected filters.")
        return
    
    # Display records table
    st.write(f"Showing {len(filtered_records)} of {total_records} records")
    
    # Convert to DataFrame for better display
    df_records = pd.DataFrame(filtered_records)
    
    # Format the DataFrame
    if not df_records.empty:
        # Add status icons
        status_icons = {
            'Queued': '⏳',
            'Running': '🔄',
            'Success': '✅',
            'Failed': '❌'
        }
        df_records['Status'] = df_records['status'].map(lambda x: f"{status_icons.get(x, '❓')} {x}")
        
        # Select and rename columns for display
        display_columns = {
            'row_idx': 'Row',
            'sheet_name': 'Sheet',
            'district': 'District',
            'taluka': 'Taluka', 
            'village': 'Village',
            'survey': 'Survey',
            'Status': 'Status',
            'error': 'Error',
            'processing_time': 'Time (s)'
        }
        
        df_display = df_records.rename(columns=display_columns)[list(display_columns.values())]
        
        # Handle long error messages
        if 'Error' in df_display.columns:
            df_display['Error'] = df_display['Error'].apply(lambda x: str(x)[:50] + "..." if x and len(str(x)) > 50 else x)
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # Add retry functionality for failed records
        failed_records = [r for r in filtered_records if r['status'] == 'Failed']
        if failed_records:
            st.subheader("🔄 Retry Failed Records")
            if st.button(f"Retry {len(failed_records)} Failed Records"):
                st.session_state.retry_records = failed_records
                st.success(f"Marked {len(failed_records)} records for retry. Click 'Process Excel' to retry them.")
    
    # Export functionality
    if st.button("📥 Export Records Summary"):
        csv = df_records.to_csv(index=False)
        st.download_button(
            "Download Records Summary (CSV)",
            csv,
            file_name=f"records_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

def display_processing_summary():
    """Display processing summary and logs"""
    st.subheader("📊 Processing Summary")
    
    # Processing History
    if st.session_state.processing_history:
        st.subheader("🕒 Processing History")
        history_df = pd.DataFrame(st.session_state.processing_history)
        if not history_df.empty:
            history_df['start_time'] = pd.to_datetime(history_df['start_time']).dt.strftime('%H:%M:%S')
            history_df['end_time'] = pd.to_datetime(history_df['end_time']).dt.strftime('%H:%M:%S')
            st.dataframe(history_df[['start_time', 'end_time', 'total_records', 'successful', 'failed', 'duration_minutes']], use_container_width=True)
    
    if not st.session_state.processing_results:
        return
    
    # Calculate statistics
    total_processed = len(st.session_state.processing_results)
    successful = sum(1 for r in st.session_state.processing_results if r.get('success', False))
    failed = total_processed - successful
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Processed", total_processed)
    with col2:
        st.metric("Successful", successful)
    with col3:
        st.metric("Failed", failed)
    with col4:
        success_rate = (successful / total_processed * 100) if total_processed > 0 else 0
        st.metric("Success Rate", f"{success_rate:.1f}%")
    
    # Error Analysis
    if failed > 0:
        st.subheader("🔍 Error Analysis")
        error_results = [r for r in st.session_state.processing_results if not r.get('success', False)]
        error_categories = {}
        for result in error_results:
            error_info = categorize_error(result.get('error', ''))
            category = error_info['category']
            if category not in error_categories:
                error_categories[category] = {'count': 0, 'suggestion': error_info['suggestion']}
            error_categories[category]['count'] += 1
        
        for category, info in error_categories.items():
            with st.expander(f"{category} ({info['count']} errors)"):
                st.warning(f"💡 **Suggestion**: {info['suggestion']}")
    
    # Display recent logs
    if st.session_state.processing_log:
        st.subheader("📝 Recent Processing Log")
        log_df = pd.DataFrame(st.session_state.processing_log[-20:])  # Show last 20 entries
        if not log_df.empty:
            log_df['timestamp'] = pd.to_datetime(log_df['timestamp']).dt.strftime('%H:%M:%S')
            st.dataframe(log_df[['timestamp', 'event_type', 'message']], use_container_width=True)
    
    # Download results
    if st.session_state.processing_results:
        results_df = pd.DataFrame(st.session_state.processing_results)
        csv = results_df.to_csv(index=False)
        st.download_button(
            "📥 Download Processing Results (CSV)",
            csv,
            file_name=f"processing_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

tab1, tab2, tab3, tab4 = st.tabs(["Single Record", "Batch (Excel)", "Records Summary", "Processing Summary"])

with tab1:
    st.subheader("Single Record")
    c1, c2 = st.columns(2)
    with c1:
        district_raw = st.text_input("District (English or Gujarati)", key="single_district")
        taluka_raw = st.text_input("Taluka (English or Gujarati)", key="single_taluka")
    with c2:
        village_raw = st.text_input("Village (English or Gujarati)", key="single_village")
        survey_raw = st.text_input("Survey/Block (Gujarati preferred)", key="single_survey")

    # Auto-translate to Gujarati if user typed English
    district, taluka, village, survey = english_to_gujarati_inputs(district_raw, taluka_raw, village_raw, survey_raw)

    if st.button("Fetch Record", type="primary"):
        if not all([district, taluka, village, survey]):
            st.error("Please fill all the fields.")
        else:
            with st.spinner("Fetching record and generating outputs..."):
                log_processing_event("START", f"Processing single record: {district}, {taluka}, {village}, {survey}")
                
                result = processor.fetch_pdf_and_tsr(
                    district_guj=district,
                    taluka_guj=taluka,
                    village_guj=village,
                    survey_number_guj=survey,
                    regenerate_pdf=regenerate_pdf,
                    generate_tsr=generate_tsr,
                    use_agent=st.session_state.use_agent_mode,
                )
                
                # Log result
                if result.success:
                    log_processing_event("SUCCESS", f"Successfully processed: {district}, {taluka}, {village}, {survey}")
                else:
                    log_processing_event("ERROR", f"Failed to process: {district}, {taluka}, {village}, {survey}", result.error)
                
                # Add to results
                st.session_state.processing_results.append({
                    'district': district,
                    'taluka': taluka,
                    'village': village,
                    'survey': survey,
                    'success': result.success,
                    'pdf_path': result.pdf_path,
                    'tsr_path': result.tsr_path,
                    'error': result.error,
                    'timestamp': datetime.now().isoformat()
                })
            
            if result.success:
                st.success("Success! Files generated.")
                if result.pdf_path and os.path.exists(result.pdf_path):
                    with open(result.pdf_path, "rb") as f:
                        st.download_button("Download PDF", f, file_name=os.path.basename(result.pdf_path), mime="application/pdf")
                if result.tsr_path and os.path.exists(result.tsr_path):
                    with open(result.tsr_path, "rb") as f:
                        st.download_button("Download TSR (DOCX)", f, file_name=os.path.basename(result.tsr_path), mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            else:
                st.error(f"Failed: {result.error}")

with tab2:
    st.subheader("Batch via Excel")
    st.markdown("Upload an Excel with Gujarati columns: `District`, `Taluka`, `Village`, `Survey`. Alternatively map columns below.")
    file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"]) 
    
    if file:
        # Read Excel file with all sheets
        try:
            excel_file = pd.ExcelFile(file)
            available_sheets = excel_file.sheet_names
            
            if len(available_sheets) > 1:
                st.info(f"📋 Found {len(available_sheets)} sheets: {', '.join(available_sheets)}")
                
                # Dynamic sheet selection based on available sheets
                if not process_all_sheets:
                    selected_sheet = st.selectbox(
                        "Select sheet to process", 
                        options=available_sheets, 
                        index=0,
                        key="dynamic_sheet_selector"
                    )
                    st.info(f"📄 Processing sheet: {selected_sheet}")
                else:
                    st.success("✅ Will process all sheets in the Excel file")
                    selected_sheet = None  # Not needed when processing all sheets
            else:
                st.info(f"📋 Found 1 sheet: {available_sheets[0]}")
                selected_sheet = available_sheets[0]  # Use the only available sheet
            
            # Read data based on sheet selection
            if process_all_sheets and len(available_sheets) > 1:
                all_dataframes = []
                for sheet_name in available_sheets:
                    try:
                        df_sheet = pd.read_excel(file, sheet_name=sheet_name, dtype=str).fillna("")
                        df_sheet['_sheet_name'] = sheet_name  # Add sheet identifier
                        all_dataframes.append(df_sheet)
                        st.success(f"✅ Loaded sheet: {sheet_name} ({len(df_sheet)} rows)")
                    except Exception as e:
                        st.error(f"❌ Error loading sheet '{sheet_name}': {e}")
                
                if all_dataframes:
                    df = pd.concat(all_dataframes, ignore_index=True)
                    st.success(f"📊 Combined {len(df)} total rows from {len(all_dataframes)} sheets")
                else:
                    st.error("❌ No sheets could be loaded successfully")
                    df = None
            else:
                # Process single sheet
                sheet_to_read = selected_sheet if selected_sheet else available_sheets[0]
                try:
                    df = pd.read_excel(file, sheet_name=sheet_to_read, dtype=str).fillna("")
                    st.success(f"📊 Loaded {len(df)} rows from sheet: {sheet_to_read}")
                except Exception as e:
                    st.error(f"❌ Error reading sheet '{sheet_to_read}': {e}")
                    df = None
            
            if df is not None and len(df) > 0:
                st.dataframe(df.astype(str).head())
                
                # AI-powered automatic column detection
                st.subheader("🤖 Smart Column Mapping")
                
                with st.spinner("🔍 AI analyzing columns..."):
                    try:
                        auto_mapping, confidence_report = auto_detect_columns(df)
                        
                        # Show auto-detection results
                        auto_detected = all(v is not None for v in auto_mapping.values())
                        
                        # Display confidence report
                        with st.expander("📊 AI Detection Report", expanded=False):
                            st.code(confidence_report)
                            
                            # Show sample data for verification
                            if auto_detected:
                                try:
                                    st.write("**📝 Sample Data Preview:**")
                                    sample_df = df[[auto_mapping[field] for field in ['district', 'taluka', 'village', 'survey'] if auto_mapping[field]]].head(3)
                                    st.dataframe(sample_df)
                                except Exception as sample_error:
                                    st.info(f"Sample preview unavailable: {sample_error}")
                        
                        if auto_detected:
                            st.success("✅ All columns automatically detected!")
                        else:
                            missing_fields = [k for k, v in auto_mapping.items() if v is None]
                            st.warning(f"⚠️ Could not auto-detect: {', '.join(missing_fields)}")
                        
                    except Exception as e:
                        st.error(f"❌ AI detection failed: {e}")
                        # Provide helpful fallback information
                        st.info("💡 **Fallback**: Using manual column selection. Please select columns manually below.")
                        auto_mapping = {'district': None, 'taluka': None, 'village': None, 'survey': None}
                        auto_detected = False
                
                # Column mapping section with AI suggestions
                st.subheader("📋 Column Mapping")
                use_ai_detection = st.checkbox("🤖 Use AI detection", value=auto_detected, 
                                             help="Automatically use AI-detected column mapping")
                
                cols = list(df.columns)
                
                if use_ai_detection and auto_detected:
                    # Use AI-detected mapping
                    col_district = auto_mapping['district']
                    col_taluka = auto_mapping['taluka'] 
                    col_village = auto_mapping['village']
                    col_survey = auto_mapping['survey']
                    
                    # Show the mapping in a nice format
                    st.info(f"🤖 **AI Mapping**: District→{col_district} | Taluka→{col_taluka} | Village→{col_village} | Survey→{col_survey}")
                    
                else:
                    # Manual selection with AI suggestions as defaults
                    c1, c2 = st.columns(2)
                    with c1:
                        district_default = cols.index(auto_mapping['district']) if auto_mapping['district'] in cols else 0
                        col_district = st.selectbox("District column", options=cols, index=district_default,
                                                  help="🤖 AI suggests: " + (auto_mapping['district'] or "None detected"))
                        
                        taluka_default = cols.index(auto_mapping['taluka']) if auto_mapping['taluka'] in cols else 0
                        col_taluka = st.selectbox("Taluka column", options=cols, index=taluka_default,
                                                help="🤖 AI suggests: " + (auto_mapping['taluka'] or "None detected"))
                    with c2:
                        village_default = cols.index(auto_mapping['village']) if auto_mapping['village'] in cols else 0
                        col_village = st.selectbox("Village column", options=cols, index=village_default,
                                                 help="🤖 AI suggests: " + (auto_mapping['village'] or "None detected"))
                        
                        survey_default = cols.index(auto_mapping['survey']) if auto_mapping['survey'] in cols else 0
                        col_survey = st.selectbox("Survey column", options=cols, index=survey_default,
                                                help="🤖 AI suggests: " + (auto_mapping['survey'] or "None detected"))
            else:
                st.warning("⚠️ No data available to display")
                col_district = col_taluka = col_village = col_survey = None

            if st.button("Process Excel", type="primary", disabled=(df is None or len(df) == 0 or col_district is None)):
                # Clear previous results for this batch
                st.session_state.processing_results = []
                st.session_state.processing_log = []
                st.session_state.processing_paused = False
                st.session_state.processing_start_time = datetime.now()
                st.session_state.processing_speeds = []
                
                log_processing_event("BATCH_START", f"Starting batch processing of {len(df)} records")
                
                # Prepare data for processing
                records_to_process = []
                for idx, row in df.iterrows():
                    d_raw = row.get(col_district)
                    t_raw = row.get(col_taluka)
                    v_raw = row.get(col_village)
                    s_raw = row.get(col_survey)
                    
                    # Skip rows with missing data
                    if not all([d_raw, t_raw, v_raw, s_raw]):
                        continue
                    
                    # Auto-translate to Gujarati
                    district_guj, taluka_guj, village_guj, survey_guj = english_to_gujarati_inputs(
                        d_raw, t_raw, v_raw, s_raw
                    )
                    
                    records_to_process.append({
                        'row_idx': idx,
                        'district': district_guj,
                        'taluka': taluka_guj,
                        'village': village_guj,
                        'survey': survey_guj,
                        'sheet_name': row.get('_sheet_name', 'Unknown')
                    })
                
                if not records_to_process:
                    st.error("No valid records found to process.")
                    st.stop()
                
                st.info(f"📝 Processing {len(records_to_process)} valid records...")
                
                # Initialize records summary
                update_records_summary(records_to_process)
                
                # Per-row progress UI
                st.divider()
                st.subheader("Per-row progress")

                row_ui = {}
                for display_idx, record in enumerate(records_to_process, start=1):
                    label = f"{display_idx}. [{record['sheet_name']}] {record['district']} / {record['taluka']} / {record['village']} / {record['survey']}"
                    exp = st.expander(label, expanded=False)
                    with exp:
                        status_placeholder = st.empty()
                        progress_placeholder = st.progress(0.0)
                    key = (record['sheet_name'], record['row_idx'])
                    row_ui[key] = {
                        'status': status_placeholder,
                        'progress': progress_placeholder,
                    }
                    status_placeholder.info("Queued")
                
                # Process records
                if use_pipeline:
                    # High-Performance Pipeline Processing
                    st.info(f"🚀 Using high-performance pipeline: {max_pdf_workers} PDF workers + {max_tsr_workers} TSR workers")
                    
                    # Initialize pipeline service
                    if st.session_state.pipeline_service is None:
                        st.session_state.pipeline_service = ParallelProcessingService(
                            output_base_dir=output_dir,
                            headless=headless,
                            max_pdf_workers=max_pdf_workers,
                            max_tsr_workers=max_tsr_workers,
                            logger=None,
                            use_agent=st.session_state.use_agent_mode,
                        )
                        st.session_state.pipeline_service.add_progress_callback(pipeline_progress_callback)
                    
                    # Progress and control section
                    progress_container = st.container()
                    with progress_container:
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            progress_bar = st.progress(0)
                        with col2:
                            if st.button("⏸️ Pause Pipeline", key="pipeline_pause"):
                                st.session_state.pipeline_service.pause_processing()
                                st.success("Pipeline paused")
                        with col3:
                            if st.button("⏹️ Stop Pipeline", key="pipeline_stop"):
                                st.session_state.pipeline_service.stop_processing()
                                st.warning("Pipeline stopped")
                    
                    # Pipeline metrics
                    metrics_container = st.container()
                    status_text = st.empty()
                    pipeline_stats_text = st.empty()
                    
                    # Start workers
                    st.session_state.pipeline_service.start_workers()
                    
                    # Submit all tasks to pipeline
                    task_ids = st.session_state.pipeline_service.submit_tasks(records_to_process)
                    
                    # Monitor progress
                    start_time = time.time()
                    last_update = time.time()
                    
                    while True:
                        current_time = time.time()
                        # Apply any pending background progress updates
                        _apply_pipeline_events()
                        
                        # Get current stats
                        stats = st.session_state.pipeline_service.get_stats()
                        
                        # Update progress bar
                        total_tasks = len(records_to_process)
                        completed_tasks = stats.completed_count + stats.failed_count
                        progress = completed_tasks / total_tasks if total_tasks > 0 else 0
                        progress_bar.progress(progress)
                        
                        # Update status
                        status_text.text(f"Processed {completed_tasks}/{total_tasks} records")
                        
                        # Update pipeline metrics
                        elapsed = current_time - start_time
                        throughput = completed_tasks / elapsed if elapsed > 0 else 0
                        eta = (total_tasks - completed_tasks) / throughput if throughput > 0 else 0
                        
                        pipeline_stats_text.text(
                            f"⚡ Pipeline: PDF Queue: {stats.pdf_queue_size} | TSR Queue: {stats.tsr_queue_size} | "
                            f"Speed: {throughput*60:.1f} records/min | ETA: {int(eta//60)}m {int(eta%60)}s"
                        )
                        
                        # Check if completed
                        if completed_tasks >= total_tasks:
                            break
                        
                        # Check for pause/stop
                        if st.session_state.processing_paused:
                            st.session_state.pipeline_service.pause_processing()
                            status_text.text("⏸️ Pipeline paused")
                            while st.session_state.processing_paused:
                                time.sleep(0.5)
                            st.session_state.pipeline_service.resume_processing()
                        
                        # Update UI every 500ms
                        if current_time - last_update > 0.5:
                            last_update = current_time
                            st.rerun()
                        
                        time.sleep(0.1)
                    
                    # Get final results
                    pipeline_results = st.session_state.pipeline_service.get_results()
                    results = []
                    
                    for i, result in enumerate(pipeline_results):
                        task = records_to_process[i] if i < len(records_to_process) else None
                        if task:
                            result_dict = {
                                'row_idx': task['row_idx'],
                                'sheet_name': task['sheet_name'],
                                'district': task['district'],
                                'taluka': task['taluka'],
                                'village': task['village'],
                                'survey': task['survey'],
                                'success': result.success,
                                'pdf_path': result.pdf_path,
                                'tsr_path': result.tsr_path,
                                'error': result.error,
                                'timestamp': datetime.now().isoformat()
                            }
                            results.append(result_dict)
                    
                    progress_bar.progress(1.0)
                    status_text.text("✅ Pipeline processing completed!")
                    
                elif use_parallel:
                    # Parallel processing
                    st.info(f"⚡ Using parallel processing with {max_workers} workers")
                    
                    # Progress and control section
                    progress_container = st.container()
                    with progress_container:
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            progress_bar = st.progress(0)
                        with col2:
                            pause_button = st.button("⏸️ Pause" if not st.session_state.processing_paused else "▶️ Resume")
                        with col3:
                            stop_button = st.button("⏹️ Stop")
                        
                        if pause_button:
                            st.session_state.processing_paused = not st.session_state.processing_paused
                            st.rerun()
                    
                    # Real-time metrics
                    metrics_container = st.container()
                    status_text = st.empty()
                    stats_text = st.empty()
                    
                    results = []
                    # Create a semaphore to limit concurrent Selenium sessions
                    sel_semaphore = threading.Semaphore(selenium_max_sessions)
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        # Submit all tasks
                        future_to_record = {}
                        for record in records_to_process:
                            args = (
                                sel_semaphore,
                                record['district'], record['taluka'], record['village'], record['survey'],
                                regenerate_pdf, generate_tsr
                            )
                            future = executor.submit(process_single_record_parallel, args)
                            future_to_record[future] = record
                            key = (record['sheet_name'], record['row_idx'])
                            ui = row_ui.get(key)
                            if ui:
                                ui['status'].warning("Running")
                                ui['progress'].progress(0.1)
                            
                            # Update records summary status
                            update_record_status(record['row_idx'], record['sheet_name'], 'Running')
                        
                        # Process completed tasks
                        completed = 0
                        for future in as_completed(future_to_record):
                            # Check for pause/stop
                            while st.session_state.processing_paused:
                                time.sleep(0.5)
                                if stop_button:  # This won't work in practice, but shows the intent
                                    break
                            
                            record = future_to_record[future]
                            try:
                                result = future.result()
                                result['row_idx'] = record['row_idx']
                                result['sheet_name'] = record['sheet_name']
                                results.append(result)
                                
                                # Update progress
                                completed += 1
                                progress = completed / len(records_to_process)
                                progress_bar.progress(progress)
                                
                                # Calculate and display real-time stats
                                stats = calculate_processing_stats(completed, len(records_to_process), st.session_state.processing_start_time)
                                if stats:
                                    eta_str = f"{int(stats['eta_seconds']//60)}m {int(stats['eta_seconds']%60)}s" if stats['eta_seconds'] > 0 else "Calculating..."
                                    status_text.text(f"Processed {completed}/{len(records_to_process)} records")
                                    stats_text.text(f"⚡ Speed: {stats['records_per_minute']:.1f} records/min | ⏱️ ETA: {eta_str} | ⏲️ Elapsed: {int(stats['elapsed']//60)}m {int(stats['elapsed']%60)}s")
                                else:
                                    status_text.text(f"Processed {completed}/{len(records_to_process)} records")
                                
                                # Log progress
                                if result['success']:
                                    log_processing_event("SUCCESS", f"Row {record['row_idx']}: {record['district']}, {record['taluka']}, {record['village']}, {record['survey']}")
                                else:
                                    log_processing_event("ERROR", f"Row {record['row_idx']}: {record['district']}, {record['taluka']}, {record['village']}, {record['survey']}", result['error'])
                                
                                key = (record['sheet_name'], record['row_idx'])
                                ui = row_ui.get(key)
                                if ui:
                                    if result.get('success'):
                                        ui['status'].success("Done")
                                    else:
                                        err_text = result.get('error') or "Failed"
                                        ui['status'].error(f"Failed: {err_text}")
                                    ui['progress'].progress(1.0)
                                
                                # Update records summary status
                                status = 'Success' if result.get('success') else 'Failed'
                                update_record_status(
                                    record['row_idx'], 
                                    record['sheet_name'], 
                                    status,
                                    error=result.get('error'),
                                    pdf_path=result.get('pdf_path'),
                                    tsr_path=result.get('tsr_path')
                                )
                                
                            except Exception as e:
                                error_result = {
                                    'row_idx': record['row_idx'],
                                    'sheet_name': record['sheet_name'],
                                    'district': record['district'],
                                    'taluka': record['taluka'],
                                    'village': record['village'],
                                    'survey': record['survey'],
                                    'success': False,
                                    'pdf_path': None,
                                    'tsr_path': None,
                                    'error': str(e),
                                    'timestamp': datetime.now().isoformat()
                                }
                                results.append(error_result)
                                log_processing_event("ERROR", f"Row {record['row_idx']}: Processing exception", str(e))
                                key = (record['sheet_name'], record['row_idx'])
                                ui = row_ui.get(key)
                                if ui:
                                    ui['status'].error(f"Failed: {e}")
                                    ui['progress'].progress(1.0)
                                
                                # Update records summary status
                                update_record_status(record['row_idx'], record['sheet_name'], 'Failed', error=str(e))
                    
                    progress_bar.progress(1.0)
                    status_text.text("✅ Processing completed!")
                    
                else:
                    # Sequential processing
                    st.info("🐌 Using sequential processing")
                    
                    # Progress and control section
                    progress_container = st.container()
                    with progress_container:
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            progress_bar = st.progress(0)
                        with col2:
                            pause_button_seq = st.button("⏸️ Pause" if not st.session_state.processing_paused else "▶️ Resume", key="seq_pause")
                        with col3:
                            stop_button_seq = st.button("⏹️ Stop", key="seq_stop")
                        
                        if pause_button_seq:
                            st.session_state.processing_paused = not st.session_state.processing_paused
                            st.rerun()
                    
                    # Real-time metrics
                    status_text = st.empty()
                    stats_text = st.empty()
                    
                    results = []
                    sel_semaphore = threading.Semaphore(selenium_max_sessions)
                    for i, record in enumerate(records_to_process):
                        # Check for pause/stop
                        while st.session_state.processing_paused:
                            time.sleep(0.5)
                            
                        if stop_button_seq:
                            break
                            
                        key = (record['sheet_name'], record['row_idx'])
                        ui = row_ui.get(key)
                        if ui:
                            ui['status'].warning("Running")
                            ui['progress'].progress(0.1)
                        
                        # Update records summary status
                        update_record_status(record['row_idx'], record['sheet_name'], 'Running')
                        
                        status_text.text(f"Processing record {i+1}/{len(records_to_process)}: {record['district']}, {record['taluka']}, {record['village']}, {record['survey']}")
                        
                        # Update real-time stats
                        stats = calculate_processing_stats(i, len(records_to_process), st.session_state.processing_start_time)
                        if stats:
                            eta_str = f"{int(stats['eta_seconds']//60)}m {int(stats['eta_seconds']%60)}s" if stats['eta_seconds'] > 0 else "Calculating..."
                            stats_text.text(f"⚡ Speed: {stats['records_per_minute']:.1f} records/min | ⏱️ ETA: {eta_str} | ⏲️ Elapsed: {int(stats['elapsed']//60)}m {int(stats['elapsed']%60)}s")
                        
                        try:
                            # Throttle Selenium concurrency even in sequential block to share with other threads
                            with sel_semaphore:
                                result = processor.fetch_pdf_and_tsr(
                                    district_guj=record['district'],
                                    taluka_guj=record['taluka'],
                                    village_guj=record['village'],
                                    survey_number_guj=record['survey'],
                                    regenerate_pdf=regenerate_pdf,
                                    generate_tsr=generate_tsr,
                                )
                            
                            result_dict = {
                                'row_idx': record['row_idx'],
                                'sheet_name': record['sheet_name'],
                                'district': record['district'],
                                'taluka': record['taluka'],
                                'village': record['village'],
                                'survey': record['survey'],
                                'success': result.success,
                                'pdf_path': result.pdf_path,
                                'tsr_path': result.tsr_path,
                                'error': result.error,
                                'timestamp': datetime.now().isoformat()
                            }
                            results.append(result_dict)
                            
                            # Log result
                            if result.success:
                                log_processing_event("SUCCESS", f"Row {record['row_idx']}: {record['district']}, {record['taluka']}, {record['village']}, {record['survey']}")
                            else:
                                log_processing_event("ERROR", f"Row {record['row_idx']}: {record['district']}, {record['taluka']}, {record['village']}, {record['survey']}", result.error)
                            
                            key = (record['sheet_name'], record['row_idx'])
                            ui = row_ui.get(key)
                            if ui:
                                if result.success:
                                    ui['status'].success("Done")
                                else:
                                    ui['status'].error(f"Failed: {result.error}")
                                ui['progress'].progress(1.0)
                            
                            # Update records summary status
                            status = 'Success' if result.success else 'Failed'
                            update_record_status(
                                record['row_idx'], 
                                record['sheet_name'], 
                                status,
                                error=result.error,
                                pdf_path=result.pdf_path,
                                tsr_path=result.tsr_path
                            )
                            
                        except Exception as e:
                            error_result = {
                                'row_idx': record['row_idx'],
                                'sheet_name': record['sheet_name'],
                                'district': record['district'],
                                'taluka': record['taluka'],
                                'village': record['village'],
                                'survey': record['survey'],
                                'success': False,
                                'pdf_path': None,
                                'tsr_path': None,
                                'error': str(e),
                                'timestamp': datetime.now().isoformat()
                            }
                            results.append(error_result)
                            log_processing_event("ERROR", f"Row {record['row_idx']}: Processing exception", str(e))
                            key = (record['sheet_name'], record['row_idx'])
                            ui = row_ui.get(key)
                            if ui:
                                ui['status'].error(f"Failed: {e}")
                                ui['progress'].progress(1.0)
                            
                            # Update records summary status
                            update_record_status(record['row_idx'], record['sheet_name'], 'Failed', error=str(e))
                        
                        # Update progress
                        progress = (i + 1) / len(records_to_process)
                        progress_bar.progress(progress)
                    
                    status_text.text("✅ Processing completed!")
                
                # Store results
                st.session_state.processing_results.extend(results)
                
                # Display summary
                success_count = sum(1 for r in results if r['success'])
                fail_count = len(results) - success_count
                st.success(f"✅ Completed. Success: {success_count}, Failed: {fail_count}")
                st.write("Outputs saved under:", os.path.abspath(output_dir))

                # Zip outputs for single-click download
                try:
                    with tempfile.TemporaryDirectory() as tmpd:
                        zip_path = os.path.join(tmpd, "outputs.zip")
                        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                            # PDFs
                            pdf_dir = os.path.join(output_dir, "pdfs")
                            if os.path.isdir(pdf_dir):
                                for name in os.listdir(pdf_dir):
                                    full = os.path.join(pdf_dir, name)
                                    if os.path.isfile(full):
                                        zf.write(full, arcname=os.path.join("pdfs", name))
                            # TSRs
                            tsr_dir = os.path.join(output_dir, "tsr")
                            if os.path.isdir(tsr_dir):
                                for name in os.listdir(tsr_dir):
                                    full = os.path.join(tsr_dir, name)
                                    if os.path.isfile(full):
                                        zf.write(full, arcname=os.path.join("tsr", name))

                        with open(zip_path, "rb") as f:
                            st.download_button(
                                "Download All Outputs (ZIP)",
                                f,
                                file_name="outputs.zip",
                                mime="application/zip",
                            )
                except Exception as e:
                    st.warning(f"Could not create ZIP: {e}")
                
                log_processing_event("BATCH_COMPLETE", f"Batch processing completed. Success: {success_count}, Failed: {fail_count}")
                
                # Add to processing history
                if st.session_state.processing_start_time:
                    end_time = datetime.now()
                    duration = (end_time - st.session_state.processing_start_time).total_seconds() / 60  # minutes
                    history_entry = {
                        'start_time': st.session_state.processing_start_time.isoformat(),
                        'end_time': end_time.isoformat(),
                        'total_records': len(results),
                        'successful': success_count,
                        'failed': fail_count,
                        'duration_minutes': round(duration, 2),
                        'processing_mode': 'Parallel' if use_parallel else 'Sequential'
                    }
                    st.session_state.processing_history.append(history_entry)
                
        except Exception as e:
            st.error(f"❌ Error reading Excel file: {e}")
            
            # Provide helpful error messages based on the error type
            error_str = str(e).lower()
            if "not found" in error_str and "sheet" in error_str:
                st.info("💡 **Sheet Not Found**: The system tried to read a sheet that doesn't exist in your Excel file.")
                st.info("✅ **Solution**: Toggle 'Process all sheets' ON or select the correct sheet from the dropdown.")
            elif "permission" in error_str or "access" in error_str:
                st.info("💡 **File Access Issue**: The Excel file might be open in another program.")
                st.info("✅ **Solution**: Close the Excel file in other programs and try again.")
            elif "corrupt" in error_str or "invalid" in error_str:
                st.info("💡 **File Format Issue**: The Excel file might be corrupted or in an unsupported format.")
                st.info("✅ **Solution**: Try saving the file as a new .xlsx file and upload again.")
            else:
                st.info("💡 **General Tip**: Make sure your Excel file is a valid .xlsx format with readable data.")
            
            # Show technical details in an expander
            with st.expander("🔧 Technical Details"):
                st.exception(e)
            
            log_processing_event("ERROR", "Excel file reading failed", str(e))

with tab3:
    display_records_summary()

with tab4:
    display_processing_summary()


