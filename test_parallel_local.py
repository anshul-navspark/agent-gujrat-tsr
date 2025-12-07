import requests
import pandas as pd
import concurrent.futures
import time
import sys
import os

# Create output directory for downloaded files
OUTPUT_DIR = "test_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def process_record(record):
    url = "http://localhost:8000/process-record"
    payload = {
        "district": record['District'],
        "taluka": record['Taluka'],
        "village": record['Village'],
        "survey_number": str(record['Survey No'])
    }
    
    try:
        start_t = time.time()
        response = requests.post(url, json=payload)
        duration = time.time() - start_t
        
        if response.status_code == 200:
            # Success - API returns a ZIP file with DOCX and PDF
            content_type = response.headers.get('Content-Type', '')
            
            if 'application/zip' in content_type:
                # Save the ZIP file
                survey_number = str(record['Survey No'])
                filename = f"TSR_{record['District']}_{record['Taluka']}_{record['Village']}_{survey_number}.zip"
                filepath = os.path.join(OUTPUT_DIR, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                file_size = len(response.content)
                return {
                    "status": response.status_code,
                    "data": {"message": "Success", "file": filepath, "size_bytes": file_size},
                    "duration": duration,
                    "record": payload
                }
            else:
                # Unexpected content type - try to parse as JSON
                try:
                    data = response.json()
                except:
                    data = {"raw_response": response.text[:500]}
                return {
                    "status": response.status_code,
                    "data": data,
                    "duration": duration,
                    "record": payload
                }
        else:
            # Error response - try to get error message
            try:
                error_data = response.json()
            except:
                error_data = response.text[:500]
            return {
                "status": response.status_code,
                "data": error_data,
                "duration": duration,
                "record": payload
            }
    except Exception as e:
        error_details = str(e)
        if 'response' in locals():
            error_details += f" | Status: {response.status_code}"
        return {
            "status": "Error",
            "error": error_details,
            "record": payload
        }

def main():
    try:
        df = pd.read_excel("test.xlsx")
        # limit to 5 records as requested previously
        records = df.head(5).to_dict('records')
    except Exception as e:
        print(f"Error reading excel: {e}")
        return

    print(f"Processing {len(records)} records in parallel...")
    start_total = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_record, r) for r in records]
        
        success_count = 0
        fail_count = 0
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result['status'] == "Error":
                print(f"❌ FAILED | Survey: {result['record']['survey_number']} | Error: {result.get('error')}")
                fail_count += 1
            elif result['status'] == 200:
                data = result.get('data', {})
                if 'file' in data:
                    print(f"✅ SUCCESS | Survey: {result['record']['survey_number']} | Time: {result.get('duration', 0):.2f}s | File: {data['file']} ({data['size_bytes']/1024:.1f} KB)")
                    success_count += 1
                else:
                    print(f"⚠️ WARNING | Survey: {result['record']['survey_number']} | Time: {result.get('duration', 0):.2f}s | Response: {data}")
                    fail_count += 1
            else:
                print(f"❌ FAILED | Survey: {result['record']['survey_number']} | Status: {result['status']} | Response: {result.get('data')}")
                fail_count += 1
        
        print(f"\n{'='*60}")
        print(f"Summary: {success_count} succeeded, {fail_count} failed")
            
    print(f"Total time: {time.time() - start_total:.2f}s")

if __name__ == "__main__":
    # Wait for server to start if needed
    time.sleep(2) 
    main()
