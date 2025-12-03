"""
Gujarat TSR Agent - Streamlit Cloud Version
API-based UI for PDF fetching and TSR generation via Cloud Run backend
"""

import os
import io
import tempfile
import zipfile
import pandas as pd
import streamlit as st
import logging
import sys

# Add parent directory to path to allow imports from utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Ensure GEMINI_API_KEY is set for translation utils
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

try:
    from utils.json_translations import translate_to_gujarati
    from utils.survey_utils import convert_survey_number
except ImportError:
    # Fallback if utils not found (e.g. local run issues)
    logging.warning("Could not import utils. Translation will be disabled.")
    def translate_to_gujarati(text, context='village'): return text
    def convert_survey_number(num): return num

from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# Import API client
from api_client import TSRAPIClient, APIResponse

# Page configuration
st.set_page_config(page_title="Gujarat TSR Agent", page_icon="📄", layout="centered")
st.title("Gujarat Land Record & TSR Generator")
st.caption("Fetch land records and generate Title Search Reports via Cloud API")

# Initialize session state
if 'processing_results' not in st.session_state:
    st.session_state.processing_results = []
if 'api_client' not in st.session_state:
    st.session_state.api_client = None

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)

# Sidebar - API Configuration
with st.sidebar:
    st.header("⚙️ API Configuration")
    
    # Get API URL from secrets or allow manual input
    default_api_url = st.secrets.get("API_URL", "https://gujrat-tsr-agent-5vu5tfjlga-el.a.run.app")
    api_url = st.text_input(
        "API URL",
        value=default_api_url,
        help="Cloud Run API endpoint URL"
    )
    
    # API settings
    api_timeout = st.number_input(
        "API Timeout (seconds)",
        min_value=900,
        max_value=1200,
        value=st.secrets.get("API_TIMEOUT", 900),
        help="Maximum time to wait for API response"
    )
    
    max_retries = st.number_input(
        "Max Retries",
        min_value=0,
        max_value=5,
        value=st.secrets.get("API_MAX_RETRIES", 2),
        help="Number of retry attempts for failed requests"
    )
    
    # Initialize API client
    if st.session_state.api_client is None or \
       st.session_state.api_client.api_url != api_url:
        st.session_state.api_client = TSRAPIClient(
            api_url=api_url,
            timeout=api_timeout,
            max_retries=max_retries
        )
    
    # API Health Check
    st.divider()
    st.subheader("🏥 API Health")
    if st.button("Check API Health"):
        with st.spinner("Checking API..."):
            is_healthy = st.session_state.api_client.health_check()
            if is_healthy:
                st.success("✅ API is healthy and responding")
            else:
                st.error("❌ API is not responding")
    
    # Batch Processing Settings
    st.divider()
    st.subheader("⚡ Batch Processing")
    max_workers = st.slider(
        "Concurrent API Calls",
        min_value=1,
        max_value=60,
        value=60,
        help="Number of simultaneous API requests for batch processing"
    )

# Helper functions
def save_docx_file(content: bytes, filename: str) -> str:
    """Save DOCX content to a temporary file and return path"""
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    with open(filepath, 'wb') as f:
        f.write(content)
    return filepath

def process_single_record_api(
    client: TSRAPIClient,
    district: str,
    taluka: str,
    village: str,
    survey: str,
    row_idx: int = None
) -> Dict[str, Any]:
    """Process a single record via API"""
    try:
        response = client.process_record(
            district=district,
            taluka=taluka,
            village=village,
            survey_number=survey
        )
        
        docx_path = None
        if response.success and response.docx_content:
            # Save DOCX file
            filename = f"{district}_{taluka}_{village}_{survey}_TSR.docx"
            filename = filename.replace(" ", "_").replace("/", "_")
            docx_path = save_docx_file(response.docx_content, filename)
        
        return {
            'row_idx': row_idx,
            'district': district,
            'taluka': taluka,
            'village': village,
            'survey': survey,
            'success': response.success,
            'docx_path': docx_path,
            'docx_content': response.docx_content if response.success else None,
            'error': response.error,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'row_idx': row_idx,
            'district': district,
            'taluka': taluka,
            'village': village,
            'survey': survey,
            'success': False,
            'docx_path': None,
            'docx_content': None,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

# Main UI - Tabs
tab1, tab2, tab3 = st.tabs(["📄 Single Record", "📊 Batch (Excel)", "📋 Results"])

# Tab 1: Single Record Processing
with tab1:
    st.subheader("Process Single Land Record")
    
    col1, col2 = st.columns(2)
    with col1:
        district = st.text_input(
            "District (Gujarati)",
            placeholder="કચ્છ",
            key="single_district"
        )
        taluka = st.text_input(
            "Taluka (Gujarati)",
            placeholder="ભુજ",
            key="single_taluka"
        )
    with col2:
        village = st.text_input(
            "Village (Gujarati)",
            placeholder="ત્રંબો - 061",
            key="single_village"
        )
        survey = st.text_input(
            "Survey Number",
            placeholder="32",
            key="single_survey"
        )
    
    if st.button("🚀 Generate TSR", type="primary"):
        if not all([district, taluka, village, survey]):
            st.error("⚠️ Please fill in all fields")
        else:
            with st.spinner(f"Processing via API... (this may take up to {api_timeout} seconds)"):
                # Translate inputs
                try:
                    with st.status("Translating inputs...", expanded=True) as status:
                        st.write(f"Translating: {district}, {taluka}, {village}...")
                        guj_district = translate_to_gujarati(district, context='district')
                        guj_taluka = translate_to_gujarati(taluka, context='taluka')
                        guj_village = translate_to_gujarati(village, context='village')
                        guj_survey = convert_survey_number(survey)
                        status.update(label="Translation complete!", state="complete", expanded=False)
                    
                    st.info(f"Translated: {guj_district}, {guj_taluka}, {guj_village}, {guj_survey}")
                except Exception as e:
                    st.error(f"Translation failed: {e}")
                    st.stop()

                result = process_single_record_api(
                    st.session_state.api_client,
                    guj_district, guj_taluka, guj_village, guj_survey
                )
                
                # Add to results
                st.session_state.processing_results.append(result)
                
                if result['success']:
                    st.success("✅ TSR generated successfully!")
                    
                    # Download button
                    if result['docx_content']:
                        st.download_button(
                            "📥 Download TSR (DOCX)",
                            data=result['docx_content'],
                            file_name=f"{district}_{taluka}_{village}_{survey}_TSR.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                else:
                    st.error(f"❌ Failed: {result['error']}")

# Tab 2: Batch Excel Processing
with tab2:
    st.subheader("Batch Processing via Excel")
    st.markdown("Upload an Excel file with columns: `District`, `Taluka`, `Village`, `Survey`")
    
    uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    
    if uploaded_file:
        try:
            # Read Excel
            df = pd.read_excel(uploaded_file, dtype=str).fillna("")
            st.success(f"📊 Loaded {len(df)} rows")
            st.dataframe(df.head(), use_container_width=True)
            
            # Column mapping
            st.subheader("📋 Column Mapping")
            cols = list(df.columns)
            
            col1, col2 = st.columns(2)
            with col1:
                col_district = st.selectbox("District column", options=cols, index=0)
                col_taluka = st.selectbox("Taluka column", options=cols, index=min(1, len(cols)-1))
            with col2:
                col_village = st.selectbox("Village column", options=cols, index=min(2, len(cols)-1))
                col_survey = st.selectbox("Survey column", options=cols, index=min(3, len(cols)-1))
            
            if st.button("🚀 Process All Records", type="primary"):
                # Clear previous results
                st.session_state.processing_results = []
                
                # Prepare records
                records_to_process = []
                for idx, row in df.iterrows():
                    d = row.get(col_district, "").strip()
                    t = row.get(col_taluka, "").strip()
                    v = row.get(col_village, "").strip()
                    s = row.get(col_survey, "").strip()
                    
                    if all([d, t, v, s]):
                        # Translate inputs
                        try:
                            # We'll do translation inside the thread pool if possible, but for now let's do it here
                            # or better, just pass raw values and let process_single_record_api handle it?
                            # No, process_single_record_api is just a wrapper around client.
                            # Doing translation sequentially here might be slow.
                            # But for now let's do it here to be safe and simple.
                            # Actually, for batch, let's use the original values if translation fails?
                            # Or we can move translation into the worker function?
                            # Let's keep it simple: translate here.
                            
                            guj_d = translate_to_gujarati(d, context='district')
                            guj_t = translate_to_gujarati(t, context='taluka')
                            guj_v = translate_to_gujarati(v, context='village')
                            guj_s = convert_survey_number(s)
                        except Exception as e:
                            # If translation fails, use original (might fail on API but at least we try)
                            guj_d, guj_t, guj_v, guj_s = d, t, v, s
                            
                        records_to_process.append({
                            'row_idx': idx,
                            'district': guj_d,
                            'taluka': guj_t,
                            'village': guj_v,
                            'survey': guj_s,
                            'original_district': d,
                            'original_taluka': t,
                            'original_village': v,
                            'original_survey': s
                        })
                
                if not records_to_process:
                    st.error("❌ No valid records found")
                else:
                    st.info(f"📝 Processing {len(records_to_process)} records with {max_workers} concurrent API calls...")
                    
                    # Progress tracking
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    results = []
                    completed = 0
                    
                    # Process in parallel
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        # Submit all tasks
                        future_to_record = {
                            executor.submit(
                                process_single_record_api,
                                st.session_state.api_client,
                                rec['district'],
                                rec['taluka'],
                                rec['village'],
                                rec['survey'],
                                rec['row_idx']
                            ): rec
                            for rec in records_to_process
                        }
                        
                        # Process completed tasks
                        for future in as_completed(future_to_record):
                            result = future.result()
                            results.append(result)
                            completed += 1
                            
                            # Update progress
                            progress = completed / len(records_to_process)
                            progress_bar.progress(progress)
                            status_text.text(f"Processed {completed}/{len(records_to_process)} records")
                    
                    # Store results
                    st.session_state.processing_results = results
                    
                    # Summary
                    success_count = sum(1 for r in results if r['success'])
                    fail_count = len(results) - success_count
                    
                    st.success(f"✅ Completed! Success: {success_count}, Failed: {fail_count}")
                    
                    # Create ZIP of all DOCX files
                    if success_count > 0:
                        # Create ZIP in memory to avoid temp directory cleanup issues
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                            for result in results:
                                if result['success'] and result['docx_content']:
                                    filename = f"{result['district']}_{result['taluka']}_{result['village']}_{result['survey']}_TSR.docx"
                                    filename = filename.replace(" ", "_").replace("/", "_")
                                    zf.writestr(filename, result['docx_content'])
                        
                        # Get the ZIP data before buffer goes out of scope
                        zip_buffer.seek(0)
                        zip_data = zip_buffer.getvalue()
                        
                        st.download_button(
                            "📥 Download All TSR Documents (ZIP)",
                            data=zip_data,
                            file_name="tsr_documents.zip",
                            mime="application/zip"
                        )
        
        except Exception as e:
            st.error(f"❌ Error reading Excel: {e}")

# Tab 3: Results
with tab3:
    st.subheader("📋 Processing Results")
    
    if not st.session_state.processing_results:
        st.info("No results yet. Process some records to see results here.")
    else:
        # Summary metrics
        total = len(st.session_state.processing_results)
        successful = sum(1 for r in st.session_state.processing_results if r['success'])
        failed = total - successful
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Processed", total)
        with col2:
            st.metric("✅ Successful", successful)
        with col3:
            st.metric("❌ Failed", failed)
        
        # Results table
        st.divider()
        results_df = pd.DataFrame(st.session_state.processing_results)
        
        # Format for display
        display_df = results_df[[
            'district', 'taluka', 'village', 'survey', 'success', 'error'
        ]].copy()
        display_df['status'] = display_df['success'].map({True: '✅ Success', False: '❌ Failed'})
        display_df = display_df.drop(columns=['success'])
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # Export results
        if st.button("📥 Export Results (CSV)"):
            csv = results_df.to_csv(index=False)
            st.download_button(
                "Download Results CSV",
                data=csv,
                file_name=f"tsr_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        # Individual downloads
        st.divider()
        st.subheader("📄 Individual Downloads")
        for idx, result in enumerate(st.session_state.processing_results):
            if result['success'] and result['docx_content']:
                with st.expander(f"Row {result.get('row_idx', idx)}: {result['district']}, {result['taluka']}, {result['village']}, {result['survey']}"):
                    st.download_button(
                        "Download TSR",
                        data=result['docx_content'],
                        file_name=f"{result['district']}_{result['taluka']}_{result['village']}_{result['survey']}_TSR.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"download_{idx}"
                    )
