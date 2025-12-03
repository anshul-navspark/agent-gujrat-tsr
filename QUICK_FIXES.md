# Quick Fixes for Cloud TSR Generation Issues

## Summary
The cloud-generated TSR is extracting wrong data. Based on the comparison, the cloud is likely scraping a different survey number or the wrong PDF entirely.

## Most Likely Root Causes (in order of probability)

### 1. **Survey Number Selection Failing** (90% probability)
The scraper is selecting the wrong survey number from the dropdown, possibly:
- First option in dropdown instead of "152"
- A different survey number that looks similar
- Timing issue causing selection to fail silently

### 2. **Village/Taluka Selection Failing** (70% probability)
The location selection might be failing, causing the scraper to:
- Use default/first village in the list
- Select a different village with similar name
- Fail silently and proceed with wrong location

### 3. **Environment Variables Missing** (50% probability)
Missing GEMINI_API_KEY or other env vars causing:
- Different AI extraction behavior
- Fallback to different data source
- Silent failures in translation

## Immediate Fixes to Apply

### Fix 1: Add Survey Number Verification (CRITICAL)

Add this to `anyror_refactored.py` in the `select_survey` method (around line 1051):

```python
def select_survey(self, survey_block_number):
    """Select a survey/block number from the dropdown."""
    survey_block_number = str(survey_block_number).strip()
    
    self.logger.debug(f"Selecting Survey/Block Number: {survey_block_number}")
    
    time.sleep(1)
    
    try:
        result = self.select_dropdown_option(CONFIG['SURVEY_DROPDOWN_ID'], survey_block_number, partial_match=True)
        
        # CRITICAL: Verify the selection
        dropdown = self.wait.until(
            EC.element_to_be_clickable((By.ID, CONFIG['SURVEY_DROPDOWN_ID']))
        )
        select = Select(dropdown)
        selected_option = select.first_selected_option
        selected_text = selected_option.text.strip()
        
        self.logger.info(f"VERIFICATION - Requested: '{survey_block_number}', Selected: '{selected_text}'")
        
        # Check if the selected value contains our survey number
        if survey_block_number not in selected_text:
            self.logger.error(f"SURVEY MISMATCH! Wanted '{survey_block_number}' but got '{selected_text}'")
            # Try to find exact match
            for option in select.options:
                if survey_block_number in option.text:
                    select.select_by_visible_text(option.text)
                    self.logger.info(f"Corrected selection to: {option.text}")
                    return True
            return False
        
        if result:
            self.logger.debug("Survey/Block Number selected successfully")
        else:
            self.logger.warning(f"Survey/Block Number not found matching: {survey_block_number}")
        
        return result
    except Exception as e:
        self.logger.error(f"Error selecting survey number: {str(e)}")
        return False
```

### Fix 2: Add Location Verification

Add verification after each location selection in `fetch_land_record` method:

```python
# After district selection
if not self.form_filler.select_district(district_name):
    return {'success': False, 'error': f'Failed to select district: {district_name}'}

# VERIFY DISTRICT
selected_district = self.driver.execute_script(
    'return document.getElementById(arguments[0]).selectedOptions[0].text;',
    CONFIG['DISTRICT_DROPDOWN_ID']
)
self.logger.info(f"✓ District verified: {selected_district}")

# After taluka selection
if not self.form_filler.select_taluka(taluka_name):
    return {'success': False, 'error': f'Failed to select taluka: {taluka_name}'}

# VERIFY TALUKA
selected_taluka = self.driver.execute_script(
    'return document.getElementById(arguments[0]).selectedOptions[0].text;',
    CONFIG['TALUKA_DROPDOWN_ID']
)
self.logger.info(f"✓ Taluka verified: {selected_taluka}")

# After village selection
if not self.form_filler.select_village(village_name):
    return {'success': False, 'error': f'Failed to select village: {village_name}'}

# VERIFY VILLAGE
selected_village = self.driver.execute_script(
    'return document.getElementById(arguments[0]).selectedOptions[0].text;',
    CONFIG['VILLAGE_DROPDOWN_ID']
)
self.logger.info(f"✓ Village verified: {selected_village}")
```

### Fix 3: Set Environment Variables in Cloud Run

```bash
# Get your GEMINI_API_KEY from .env
export GEMINI_API_KEY=$(grep GEMINI_API_KEY .env | cut -d'=' -f2 | tr -d '"' | tr -d "'")

# Update Cloud Run service
gcloud run services update gujrat-tsr-agent \
  --region=asia-south1 \
  --set-env-vars GEMINI_API_KEY="$GEMINI_API_KEY"

# Verify it was set
gcloud run services describe gujrat-tsr-agent \
  --region=asia-south1 \
  --format="value(spec.template.spec.containers[0].env)"
```

### Fix 4: Increase Timeouts for Cloud Environment

Add to `anyror_refactored.py` at the top:

```python
# Adjust timeouts for cloud environment
if os.getenv('K_SERVICE'):  # Cloud Run sets this env var
    CONFIG['PAGE_LOAD_WAIT'] = 10  # Increase from 5
    CONFIG['DROPDOWN_WAIT_TIMEOUT'] = 15  # Increase from 10
    CONFIG['CAPTCHA_WAIT_TIMEOUT'] = 10  # Increase from 5
```

## Testing the Fixes

### Step 1: Apply the fixes locally first
```bash
# Test locally to ensure fixes don't break anything
python test_api_local.py
```

### Step 2: Deploy to Cloud Run
```bash
# Commit changes
git add .
git commit -m "Add verification and logging for cloud TSR generation"

# Deploy
cd deploy
./deploy_cloud_run.sh
```

### Step 3: Test Cloud with diagnostic script
```bash
# Run diagnostic
python diagnose_cloud_issue.py
```

### Step 4: Check logs
```bash
# View logs to see verification messages
gcloud run services logs read gujrat-tsr-agent \
  --region=asia-south1 \
  --limit=100 \
  | grep -E "(VERIFICATION|Selected|Requested)"
```

## Expected Log Output (After Fixes)

You should see logs like:
```
INFO: District: કચ્છ
INFO: Taluka: આબડાસા
INFO: Village: ટ્રામ્બો
INFO: Survey Number: 152
INFO: ✓ District verified: કચ્છ
INFO: ✓ Taluka verified: આબડાસા
INFO: ✓ Village verified: ટ્રામ્બો
INFO: VERIFICATION - Requested: '152', Selected: '152'
INFO: PDF file size: 245678 bytes
```

## If Fixes Don't Work

### Debug with PDF Comparison
Save the scraped PDF from cloud and compare with local:

```python
# Add to api_server.py before TSR generation
import shutil
debug_pdf = f"/tmp/debug_cloud_{unique_id}.pdf"
shutil.copy(pdf_path, debug_pdf)
logger.info(f"Debug PDF saved to: {debug_pdf}")

# Then download and compare
# gcloud run services logs read ... to get the path
# Download from cloud storage or add upload to GCS
```

### Check for Caching Issues
The website might be caching results. Try:
1. Clear browser cache in selenium
2. Add random delay between requests
3. Use different user agent

### Manual Verification
1. Run the scraper locally with same parameters
2. Save screenshots at each step
3. Compare with cloud execution screenshots

## Contact Points

If none of these fixes work:
1. Check if the AnyRoR website has changed
2. Verify the website is accessible from Cloud Run IPs
3. Check if there are rate limits or IP blocks
4. Consider using a proxy or VPN for Cloud Run

## Success Criteria

The fix is successful when:
- ✅ Cloud TSR shows "Trambo" as village
- ✅ Cloud TSR shows "Pradip Pathai Bhanushali" as title holder
- ✅ Cloud TSR has same entry numbers as local (60, 650, 684, 695, 707, 713, 847)
- ✅ File sizes are within 1KB of each other
- ✅ Logs show correct verification messages
