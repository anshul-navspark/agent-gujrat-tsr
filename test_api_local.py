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
    taluka = "abadsa"
    village = "trambo"
    survey = "51"
    
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
            logger.info("Success! Saving TSR...")
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
