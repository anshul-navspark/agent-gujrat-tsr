import os
import io
import shutil
import tempfile
import zipfile
import pandas as pd
import streamlit as st
import sys
from pathlib import Path

# Ensure project root is on sys.path for package imports when running via Streamlit
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.processing_service import LandRecordProcessor
from tsr_generator.utils.text_utils import translate_gujarati_text


st.set_page_config(page_title="Gujarat Land Record & TSR", page_icon="📄", layout="centered")
st.title("Gujarat Land Record & TSR")
st.caption("Fetch land records (PDF) and generate Title Search Reports (DOCX) without coding.")

with st.sidebar:
    st.header("Settings")
    output_dir = st.text_input("Output directory", value="output")
    headless = st.toggle("Run headless (recommended)", value=True)
    regenerate_pdf = st.toggle("Re-fetch PDFs even if they exist", value=False)
    generate_tsr = st.toggle("Generate TSR after fetching PDF", value=True)

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
        # Trambo mapping example used in data
        'Trambo - 033': 'ત્રંબો - 033',
        'Trambo': 'ત્રંબો - 033',
    }

    def to_guj(name: str) -> str:
        name = (name or '').strip()
        return reverse.get(name, name)

    # Survey is often already in Gujarati form upstream, keep as is
    return to_guj(district_en), to_guj(taluka_en), to_guj(village_en), (survey_raw or '').strip()

tab1, tab2 = st.tabs(["Single Record", "Batch (Excel)"])

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
                result = processor.fetch_pdf_and_tsr(
                    district_guj=district,
                    taluka_guj=taluka,
                    village_guj=village,
                    survey_number_guj=survey,
                    regenerate_pdf=regenerate_pdf,
                    generate_tsr=generate_tsr,
                )
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
        df = pd.read_excel(file)
        st.dataframe(df.head())

        cols = list(df.columns)
        c1, c2 = st.columns(2)
        with c1:
            col_district = st.selectbox("District column", options=cols)
            col_taluka = st.selectbox("Taluka column", options=cols)
        with c2:
            col_village = st.selectbox("Village column", options=cols)
            col_survey = st.selectbox("Survey column", options=cols)

        if st.button("Process Excel", type="primary"):
            with st.spinner("Processing all rows..."):
                results = processor.process_dataframe(
                    df,
                    col_map={
                        "district": col_district,
                        "taluka": col_taluka,
                        "village": col_village,
                        "survey": col_survey,
                    },
                    regenerate_pdf=regenerate_pdf,
                    generate_tsr=generate_tsr,
                )
            success_count = sum(1 for r in results if r.success)
            fail_count = len(results) - success_count
            st.success(f"Completed. Success: {success_count}, Failed: {fail_count}")
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


