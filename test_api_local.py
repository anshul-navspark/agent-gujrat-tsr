import requests
import json
import os
import sys
import logging

# Add current directory to path to import utils
sys.path.append(os.getcwd())

from utils.json_translations import translate_to_gujarati
from utils.survey_utils import convert_survey_number

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_api():
    district = "Kutch"
    taluka = "bhuj"
    village = "trambo"
    survey = "32"
    
    logger.info(f"Testing with: {district}, {taluka}, {village}, {survey}")
    
    # Translate to Gujarati
    try:
        guj_district = translate_to_gujarati(district, context='district')
        guj_taluka = translate_to_gujarati(taluka, context='taluka')
        guj_village = translate_to_gujarati(village, context='village')
        guj_survey = convert_survey_number(survey)
        
        logger.info(f"Translated: {guj_district}, {guj_taluka}, {guj_village}, {guj_survey}")
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return

    url = "http://localhost:8000/process-record"
    payload = {
        "district": guj_district,
        "taluka": guj_taluka,
        "village": guj_village,
        "survey_number": guj_survey
    }
    
    logger.info(f"Sending request to {url}")
    try:
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            logger.info("Success! Processing response...")
            
            # Check if response is a ZIP file
            content_type = response.headers.get('Content-Type', '')
            if 'application/zip' in content_type:
                import io
                import zipfile
                
                try:
                    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                        for filename in zf.namelist():
                            if filename.endswith('.docx') and not filename.startswith('~'):
                                docx_content = zf.read(filename)
                                output_filename = f"TSR_{district}_{village}_{survey}.docx"
                                with open(output_filename, "wb") as f:
                                    f.write(docx_content)
                                logger.info(f"Extracted and saved TSR to {output_filename}")
                            elif filename.endswith('.pdf'):
                                pdf_content = zf.read(filename)
                                pdf_filename = f"Original_{district}_{village}_{survey}.pdf"
                                with open(pdf_filename, "wb") as f:
                                    f.write(pdf_content)
                                logger.info(f"Extracted and saved PDF to {pdf_filename}")
                except Exception as e:
                    logger.error(f"Failed to process ZIP response: {e}")
            else:
                output_filename = f"TSR_{district}_{village}_{survey}.docx"
                with open(output_filename, "wb") as f:
                    f.write(response.content)
                logger.info(f"Saved to {output_filename}")
        else:
            logger.error(f"Failed with status {response.status_code}: {response.text}")
            
    except Exception as e:
        logger.error(f"Request failed: {e}")

if __name__ == "__main__":
    test_api()
