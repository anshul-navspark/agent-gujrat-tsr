#!/usr/bin/env python3
"""
Quick diagnostic script to compare local vs cloud TSR generation
and identify where the discrepancy occurs.
"""

import requests
import json
import os
import sys
import hashlib
from PyPDF2 import PdfReader

# Add current directory to path
sys.path.append(os.getcwd())

from utils.json_translations import translate_to_gujarati
from utils.survey_utils import convert_survey_number

def calculate_pdf_hash(pdf_path):
    """Calculate MD5 hash of PDF file"""
    with open(pdf_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def extract_pdf_preview(pdf_path, max_chars=500):
    """Extract first page text preview from PDF"""
    try:
        reader = PdfReader(pdf_path)
        if len(reader.pages) > 0:
            return reader.pages[0].extract_text()[:max_chars]
    except Exception as e:
        return f"Error extracting PDF: {e}"
    return "No pages found"

def test_translation():
    """Test translation functions"""
    print("\n" + "="*80)
    print("TESTING TRANSLATION")
    print("="*80)
    
    test_cases = [
        ("Kutch", "district"),
        ("abadsa", "taluka"),
        ("Trambo", "village"),
        ("36", None)  # Survey number
    ]
    
    for value, context in test_cases:
        if context:
            translated = translate_to_gujarati(value, context=context)
            print(f"{context.capitalize()}: '{value}' -> '{translated}'")
        else:
            converted = convert_survey_number(value)
            print(f"Survey: '{value}' -> '{converted}'")

def test_local_api():
    """Test local API endpoint"""
    print("\n" + "="*80)
    print("TESTING LOCAL API")
    print("="*80)
    
    # Translate inputs
    guj_district = translate_to_gujarati("Kutch", context='district')
    guj_taluka = translate_to_gujarati("abadsa", context='taluka')
    guj_village = translate_to_gujarati("Trambo", context='village')
    guj_survey = convert_survey_number("36")
    
    url = "http://localhost:8000/process-record"
    payload = {
        "district": guj_district,
        "taluka": guj_taluka,
        "village": guj_village,
        "survey_number": guj_survey
    }
    
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=payload, timeout=300)
        
        if response.status_code == 200:
            output_file = "TSR_Local_Debug.docx"
            with open(output_file, "wb") as f:
                f.write(response.content)
            
            print(f"✅ Success! Saved to {output_file}")
            print(f"File size: {len(response.content)} bytes")
            return output_file
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed. Is the local server running?")
        print("   Start it with: uvicorn api_server:app --host 0.0.0.0 --port 8000")
        return None
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None

def test_cloud_api():
    """Test cloud API endpoint"""
    print("\n" + "="*80)
    print("TESTING CLOUD API")
    print("="*80)
    
    # Translate inputs
    guj_district = translate_to_gujarati("Kutch", context='district')
    guj_taluka = translate_to_gujarati("abadsa", context='taluka')
    guj_village = translate_to_gujarati("Trambo", context='village')
    guj_survey = convert_survey_number("36")
    
    url = "https://gujrat-tsr-agent-642363716512.asia-south1.run.app/process-record"
    payload = {
        "district": guj_district,
        "taluka": guj_taluka,
        "village": guj_village,
        "survey_number": guj_survey
    }
    
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=payload, timeout=900)
        
        if response.status_code == 200:
            output_file = "TSR_Cloud_Debug.docx"
            with open(output_file, "wb") as f:
                f.write(response.content)
            
            print(f"✅ Success! Saved to {output_file}")
            print(f"File size: {len(response.content)} bytes")
            return output_file
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out after 900 seconds")
        return None
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None

def compare_results(local_file, cloud_file):
    """Compare local and cloud results"""
    print("\n" + "="*80)
    print("COMPARING RESULTS")
    print("="*80)
    
    if not local_file or not cloud_file:
        print("⚠️  Cannot compare - one or both files missing")
        return
    
    if not os.path.exists(local_file):
        print(f"⚠️  Local file not found: {local_file}")
        return
    
    if not os.path.exists(cloud_file):
        print(f"⚠️  Cloud file not found: {cloud_file}")
        return
    
    # Compare file sizes
    local_size = os.path.getsize(local_file)
    cloud_size = os.path.getsize(cloud_file)
    
    print(f"Local file size:  {local_size} bytes")
    print(f"Cloud file size:  {cloud_size} bytes")
    print(f"Size difference:  {abs(local_size - cloud_size)} bytes")
    
    # Compare using compare_docx.py if available
    if os.path.exists("compare_docx.py"):
        print("\nRunning detailed comparison...")
        os.system(f"python compare_docx.py '{local_file}' '{cloud_file}'")
    else:
        print("\n⚠️  compare_docx.py not found, skipping detailed comparison")

def check_cloud_logs():
    """Check recent Cloud Run logs"""
    print("\n" + "="*80)
    print("CHECKING CLOUD LOGS")
    print("="*80)
    
    print("To view Cloud Run logs, run:")
    print("  gcloud run services logs read gujrat-tsr-agent --region=asia-south1 --limit=50")
    print("\nOr view in browser:")
    print("  https://console.cloud.google.com/run/detail/asia-south1/gujrat-tsr-agent/logs")

def main():
    """Main diagnostic function"""
    print("="*80)
    print("CLOUD VS LOCAL TSR DIAGNOSTIC TOOL")
    print("="*80)
    
    # Step 1: Test translation
    test_translation()
    
    # Step 2: Test local API
    local_file = test_local_api()
    
    # Step 3: Test cloud API
    cloud_file = test_cloud_api()
    
    # Step 4: Compare results
    compare_results(local_file, cloud_file)
    
    # Step 5: Show how to check logs
    check_cloud_logs()
    
    print("\n" + "="*80)
    print("DIAGNOSTIC COMPLETE")
    print("="*80)
    print("\nNext steps:")
    print("1. Review the comparison output above")
    print("2. Check Cloud Run logs for detailed execution trace")
    print("3. Refer to CLOUD_DEBUG_GUIDE.md for troubleshooting steps")

if __name__ == "__main__":
    main()
