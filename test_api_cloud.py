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

def test_cloud_api():
    # Test parameters
    district = "Kutch"
    taluka = "abadsa"
    village = "Trambo"
    survey = "51"
    
    logger.info(f"Testing Cloud Run API with: {district}, {taluka}, {village}, {survey}")
    
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

    # Cloud Run API endpoint
    url = "https://gujrat-tsr-agent-642363716512.asia-south1.run.app/process-record"
    
    payload = {
        "district": guj_district,
        "taluka": guj_taluka,
        "village": guj_village,
        "survey_number": guj_survey
    }
    
    logger.info(f"Sending request to Cloud Run: {url}")
    logger.info(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    
    try:
        # Increased timeout for Cloud Run (cold start + processing)
        response = requests.post(url, json=payload, timeout=900)
        
        if response.status_code == 200:
            logger.info("✅ Success! Saving TSR from Cloud Run...")
            output_filename = f"TSR_Cloud_{district}_{village}_{survey.replace('/', '_')}.docx"
            with open(output_filename, "wb") as f:
                f.write(response.content)
            logger.info(f"✅ Saved to {output_filename}")
            logger.info(f"File size: {len(response.content)} bytes")
        else:
            logger.error(f"❌ Failed with status {response.status_code}")
            logger.error(f"Response: {response.text}")
            
    except requests.exceptions.Timeout:
        logger.error("❌ Request timed out after 900 seconds")
    except Exception as e:
        logger.error(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_cloud_api()
