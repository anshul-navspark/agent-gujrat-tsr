# Cloud vs Local TSR Generation Issues - Debugging Guide

## Problem Summary
The cloud-generated TSR contains completely different data than the locally generated TSR for the same input parameters (Kutch, Abdasa, Trambo, 152).

### Observed Differences:
- **Local**: Correct data with Trambo village, Pradip Pathai Bhanushali as title holder
- **Cloud**: Wrong data with "Not Available" village, Thakor Kalubhai as title holder

## Root Causes Analysis

### 1. **Environment Variables Missing in Cloud**
**Issue**: The `.env` file is not deployed to Cloud Run, so environment variables like `GEMINI_API_KEY` might not be set.

**Solution**:
```bash
# Check if environment variables are set in Cloud Run
gcloud run services describe gujrat-tsr-agent --region=asia-south1 --format="value(spec.template.spec.containers[0].env)"

# Set environment variables in Cloud Run
gcloud run services update gujrat-tsr-agent \
  --region=asia-south1 \
  --set-env-vars GEMINI_API_KEY="your-api-key-here"
```

### 2. **Input Translation Issues**
**Issue**: The cloud might not be translating English inputs to Gujarati correctly, or using different translation logic.

**Verification**:
- Check the logs to see what exact parameters are being passed to the scraper
- Compare the Gujarati text being used in local vs cloud

**Solution**:
- Ensure `anyror_hierarchy.json` is deployed to cloud
- Verify translation functions are working correctly
- Add logging to show translated values

### 3. **Scraping Wrong Survey Number**
**Issue**: The scraper might be selecting the wrong survey number from the dropdown, possibly due to:
- Timing issues (page not fully loaded)
- Different survey numbers with similar names
- Dropdown selection failing silently

**Solution**:
```python
# In anyror_refactored.py, add verification after survey selection
def select_survey(self, survey_block_number):
    # ... existing code ...
    
    # Add verification
    selected_value = self.driver.execute_script(
        'return document.getElementById(arguments[0]).value;',
        CONFIG['SURVEY_DROPDOWN_ID']
    )
    self.logger.info(f"Selected survey value: {selected_value}")
    
    # Verify it matches what we wanted
    if survey_block_number not in selected_value:
        self.logger.warning(f"Survey mismatch! Wanted: {survey_block_number}, Got: {selected_value}")
```

### 4. **PDF Content Verification**
**Issue**: The scraped PDF might be different in cloud vs local due to:
- Caching issues
- Different page states
- Network timing differences

**Solution**:
- Save the scraped PDF temporarily and log its hash
- Compare PDF content between local and cloud
- Add PDF text extraction logging

## Immediate Action Items

### Step 1: Enable Cloud Logging
```bash
# View Cloud Run logs in real-time
gcloud run services logs tail gujrat-tsr-agent --region=asia-south1

# Or view in Cloud Console
# https://console.cloud.google.com/run/detail/asia-south1/gujrat-tsr-agent/logs
```

### Step 2: Add PDF Verification
Add this to `api_server.py` after PDF scraping:

```python
# After successful PDF scraping
import hashlib

# Calculate PDF hash for verification
with open(pdf_path, 'rb') as f:
    pdf_hash = hashlib.md5(f.read()).hexdigest()
logger.info(f"PDF MD5 Hash: {pdf_hash}")

# Extract first 500 chars of PDF text for verification
from PyPDF2 import PdfReader
reader = PdfReader(pdf_path)
first_page_text = reader.pages[0].extract_text()[:500]
logger.info(f"PDF First Page Preview: {first_page_text}")
```

### Step 3: Compare Input Parameters
Create a test script to verify translation:

```python
# test_translation_cloud.py
from utils.json_translations import translate_to_gujarati
from utils.survey_utils import convert_survey_number

district = "Kutch"
taluka = "abadsa"
village = "Trambo"
survey = "152"

print(f"District: {translate_to_gujarati(district, context='district')}")
print(f"Taluka: {translate_to_gujarati(taluka, context='taluka')}")
print(f"Village: {translate_to_gujarati(village, context='village')}")
print(f"Survey: {convert_survey_number(survey)}")
```

### Step 4: Add Scraper Verification
Modify `anyror_refactored.py` to log selected values:

```python
def fetch_land_record(self, district_name, taluka_name, village_name, survey_block_number, output_path):
    # ... existing code ...
    
    # After each selection, verify
    self.logger.info(f"Selected District: {district_name}")
    self.logger.info(f"Selected Taluka: {taluka_name}")
    self.logger.info(f"Selected Village: {village_name}")
    self.logger.info(f"Selected Survey: {survey_block_number}")
    
    # Log the actual selected values from dropdowns
    selected_district = self.driver.execute_script(
        'return document.getElementById(arguments[0]).selectedOptions[0].text;',
        CONFIG['DISTRICT_DROPDOWN_ID']
    )
    self.logger.info(f"Actual selected district from dropdown: {selected_district}")
```

## Testing Strategy

### 1. Test Locally First
```bash
# Test the API locally
python test_api_local.py
```

### 2. Test Cloud with Same Parameters
```bash
# Test the cloud API
python test_api_cloud.py
```

### 3. Compare Results
```bash
# Compare the generated documents
python compare_docx.py TSR_Kutch_trambo_152.docx TSR_Cloud_Kutch_Trambo_152.docx
```

### 4. Check Cloud Logs
```bash
# View logs to see what's different
gcloud run services logs read gujrat-tsr-agent --region=asia-south1 --limit=100
```

## Common Issues and Solutions

### Issue 1: Environment Variables Not Set
**Symptom**: GEMINI_API_KEY errors in logs
**Solution**: 
```bash
gcloud run services update gujrat-tsr-agent \
  --region=asia-south1 \
  --set-env-vars GEMINI_API_KEY="$(cat .env | grep GEMINI_API_KEY | cut -d'=' -f2)"
```

### Issue 2: Translation File Not Found
**Symptom**: "anyror_hierarchy.json not found" errors
**Solution**: Ensure the file is included in the Docker image
```dockerfile
# In Dockerfile
COPY anyror_hierarchy.json /app/
```

### Issue 3: Selenium Timeout in Cloud
**Symptom**: Timeouts during page load or element selection
**Solution**: Increase timeouts in cloud environment
```python
# In anyror_refactored.py
if os.getenv('CLOUD_RUN_ENV'):  # Set this env var in Cloud Run
    CONFIG['PAGE_LOAD_WAIT'] = 10  # Increase from 5
    CONFIG['DROPDOWN_WAIT_TIMEOUT'] = 15  # Increase from 10
```

### Issue 4: Wrong Survey Number Selected
**Symptom**: Different survey data in TSR
**Solution**: Add explicit verification and retry logic
```python
def select_survey(self, survey_block_number):
    max_retries = 3
    for attempt in range(max_retries):
        result = self.select_dropdown_option(...)
        
        # Verify selection
        selected = self.get_selected_survey()
        if survey_block_number in selected:
            return True
        
        self.logger.warning(f"Survey selection verification failed, retry {attempt+1}")
        time.sleep(2)
    
    return False
```

## Monitoring and Debugging

### Enable Detailed Logging
Set logging level to DEBUG in Cloud Run:
```bash
gcloud run services update gujrat-tsr-agent \
  --region=asia-south1 \
  --set-env-vars LOG_LEVEL="DEBUG"
```

### Save Intermediate Files
Modify the code to save PDFs to Cloud Storage for inspection:
```python
# In api_server.py
from google.cloud import storage

# After PDF scraping
if os.getenv('CLOUD_RUN_ENV'):
    # Upload to Cloud Storage for debugging
    storage_client = storage.Client()
    bucket = storage_client.bucket('your-debug-bucket')
    blob = bucket.blob(f'debug-pdfs/{unique_id}.pdf')
    blob.upload_from_filename(pdf_path)
    logger.info(f"Debug PDF uploaded to gs://your-debug-bucket/debug-pdfs/{unique_id}.pdf")
```

## Next Steps

1. **Deploy the enhanced logging version** to Cloud Run
2. **Run a test request** and capture logs
3. **Compare logs** between local and cloud execution
4. **Identify the exact point** where the behavior diverges
5. **Apply targeted fix** based on findings

## Quick Diagnostic Commands

```bash
# Check Cloud Run environment variables
gcloud run services describe gujrat-tsr-agent --region=asia-south1 --format=yaml | grep -A 20 "env:"

# Check recent logs
gcloud run services logs read gujrat-tsr-agent --region=asia-south1 --limit=50

# Check service configuration
gcloud run services describe gujrat-tsr-agent --region=asia-south1

# Test the health endpoint
curl https://gujrat-tsr-agent-642363716512.asia-south1.run.app/health

# Test with verbose logging
curl -X POST https://gujrat-tsr-agent-642363716512.asia-south1.run.app/process-record \
  -H "Content-Type: application/json" \
  -d '{"district":"કચ્છ","taluka":"આબડાસા","village":"ટ્રામ્બો","survey_number":"152"}' \
  --output test_cloud_debug.docx -v
```
