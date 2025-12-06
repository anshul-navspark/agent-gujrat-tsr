import pandas as pd
import requests
import concurrent.futures
import time
import os
import sys
import logging

# Add current directory to path to import utils
sys.path.append(os.getcwd())

from utils.json_translations import translate_to_gujarati
from utils.survey_utils import convert_survey_number, sanitize_filename

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(message)s')
logger = logging.getLogger(__name__)

def process_row(row):
    district = row['District']
    taluka = row['Tehsil']
    village = row['Village']
    survey = str(row['Survey Nos']).strip()
    
    # Skip if any required field is missing or invalid
    if pd.isna(district) or pd.isna(taluka) or pd.isna(village) or pd.isna(survey) or survey.lower() == 'new':
        logger.warning(f"Skipping invalid row: {district}, {taluka}, {village}, {survey}")
        return

    logger.info(f"Processing: {district}, {taluka}, {village}, {survey}")
    
    try:
        guj_district = translate_to_gujarati(district, context='district')
        guj_taluka = translate_to_gujarati(taluka, context='taluka')
        guj_village = translate_to_gujarati(village, context='village')
        guj_survey = convert_survey_number(survey)
    except Exception as e:
        logger.error(f"Translation failed for {survey}: {e}")
        return

    url = "http://localhost:8000/process-record"
    payload = {
        "district": guj_district,
        "taluka": guj_taluka,
        "village": guj_village,
        "survey_number": guj_survey
    }
    
    start_time = time.time()
    try:
        # Increased timeout to 10 minutes as scraping can be slow, especially with retries
        response = requests.post(url, json=payload, timeout=600)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            safe_survey = sanitize_filename(survey)
            output_filename = f"TSR_{district}_{village}_{safe_survey}.docx"
            with open(output_filename, "wb") as f:
                f.write(response.content)
            logger.info(f"Success for {survey} in {duration:.2f}s. Saved to {output_filename}")
        else:
            logger.error(f"Failed for {survey} with status {response.status_code}: {response.text}")
            
    except Exception as e:
        logger.error(f"Request failed for {survey}: {e}")

def main():
    try:
        df = pd.read_excel('Bhuj Solar Land Survey List.xlsx')
        
        # Filter valid rows
        # Ensure columns exist
        required_columns = ['District', 'Tehsil', 'Village', 'Survey Nos']
        if not all(col in df.columns for col in required_columns):
            logger.error(f"Missing columns. Found: {df.columns.tolist()}")
            return

        # Drop rows with NaN in required columns
        df_clean = df.dropna(subset=required_columns)
        
        rows = [row for _, row in df_clean.iterrows()]
        
        # Max workers for 8GB M1 Mac - now safe at 2 with port conflict fix
        # Each Chrome instance takes ~300-500MB. 2 instances = ~600MB-1GB.
        # Port conflicts are now prevented by random port allocation.
        max_workers = 4
        logger.info(f"Starting parallel processing of {len(rows)} records with {max_workers} workers")
        start_total = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(process_row, rows)
            
        total_duration = time.time() - start_total
        logger.info(f"All done in {total_duration:.2f}s")
    except Exception as e:
        logger.error(f"Main execution failed: {e}")

if __name__ == "__main__":
    main()
