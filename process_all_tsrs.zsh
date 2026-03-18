#!/bin/zsh

# ==============================================================================
# CONFIGURATION
# Modify these variables to match the actual District, Taluka, and Village
# for your 60 Final TSRs.
# ==============================================================================
DISTRICT="Banaskantha"
TALUKA="Dhanera"
VILLAGE="Malotra"

API_URL="http://127.0.0.1:8000/process-record"

# Directories
INPUT_DIR="Final TSR Sample"
OUTPUT_DIR="Final AI TSR Sample"

TIMEOUT_SECONDS=600  # 10 minutes timeout per request
MAX_CONSECUTIVE_FAILURES=4

# ==============================================================================

# Ensure we're in the script's directory
cd "$(dirname "$0")" || exit 1

mkdir -p "$OUTPUT_DIR"

consecutive_failures=0
total_processed=0
total_failed=0

# Create/Clear log files
echo "--- Run started at $(date) ---" > process.log
echo "--- Run started at $(date) ---" > failed_requests.log

echo "Starting batch processing for .docx files in '$INPUT_DIR'..."

for file in "$INPUT_DIR"/"S.No."*.docx; do
    if [[ ! -f "$file" ]]; then
        continue
    fi

    # Extract base filename
    base_filename=$(basename "$file")
    
    # We use a reliable python regex to extract the survey number based on the pattern
    # "S.No. <Survey_No> - <Something>.docx"
    survey_no=$(python3 -c "
import re, sys
m = re.match(r'S\.No\.\s*(.*?)(?:\s*-?\s*[cC]omplete|\s*-\s*[fF]inal|\s*-[cC]omplete|\.docx)', sys.argv[1])
if m:
    print(m.group(1).strip())
" "$base_filename")

    if [[ -z "$survey_no" ]]; then
        echo "⚠️ Could not extract survey number from $base_filename. Skipping." | tee -a process.log
        continue
    fi

    echo "========================================================" | tee -a process.log
    echo "Processing Survey No: $survey_no" | tee -a process.log
    echo "File source: $base_filename" | tee -a process.log
    
    TMP_RESPONSE="temp_response_$$.zip"
    
    # JSON Payload
    PAYLOAD="{\"district\": \"$DISTRICT\", \"taluka\": \"$TALUKA\", \"village\": \"$VILLAGE\", \"survey_number\": \"$survey_no\"}"
    
    echo "Sending payload: $PAYLOAD" >> process.log

    # Perform the API request
    # -w \"%{http_code}\" captures the HTTP status code
    # --max-time enforces the timeout
    # -o saves the response body to our TMP_RESPONSE file
    # -s makes curl silent
    http_code=$(curl -s -w "%{http_code}" -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        --max-time "$TIMEOUT_SECONDS" \
        -o "$TMP_RESPONSE")

    if [[ "$http_code" == "200" ]]; then
        echo "✅ Success! HTTP 200. Extracting DOCX..." | tee -a process.log
        
        # Determine the name of the extracted docx inside the zip
        docx_file_in_zip=$(unzip -Z1 "$TMP_RESPONSE" | grep -i '\.docx$' | head -n 1)
        
        if [[ -n "$docx_file_in_zip" ]]; then
            # Extract only that docx file to the output directory
            unzip -j -q "$TMP_RESPONSE" "$docx_file_in_zip" -d "$OUTPUT_DIR"
            
            # Extract base filename of the file inside the zip
            extracted_docx_base=$(basename "$docx_file_in_zip")
            
            # Rename it to have AI_ prefix while keeping the original structure
            mv "$OUTPUT_DIR/$extracted_docx_base" "$OUTPUT_DIR/AI_$base_filename"
            
            echo "📄 Saved successfully as $OUTPUT_DIR/AI_$base_filename" | tee -a process.log
            
            # Reset consecutive failures
            consecutive_failures=0
            total_processed=$((total_processed + 1))
        else
            echo "❌ Error: ZIP response did not contain a .docx file." | tee -a process.log
            echo "$survey_no (File: $base_filename) - No DOCX in ZIP" >> failed_requests.log
            consecutive_failures=$((consecutive_failures + 1))
            total_failed=$((total_failed + 1))
        fi

    else
        # Request failed or timed out
        if [[ "$http_code" == "000" ]]; then
            echo "❌ Request timed out (>${TIMEOUT_SECONDS}s) or connection failed for Survey No: $survey_no." | tee -a process.log
            error_msg="Timeout/Connection Error"
        else
            error_body=$(cat "$TMP_RESPONSE" 2>/dev/null | cut -c 1-200) # Get preview of error
            echo "❌ API Error HTTP $http_code for Survey No: $survey_no." | tee -a process.log
            echo "Response: $error_body" >> process.log
            error_msg="HTTP $http_code"
        fi
        
        echo "$survey_no (File: $base_filename) - $error_msg" >> failed_requests.log
        
        consecutive_failures=$((consecutive_failures + 1))
        total_failed=$((total_failed + 1))
    fi
    
    # Cleanup temp file
    rm -f "$TMP_RESPONSE"

    # Check limit check
    if [[ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILURES ]]; then
        echo "🚨 ABORTING: Reached $MAX_CONSECUTIVE_FAILURES consecutive failures! Check backend logs." | tee -a process.log
        break
    fi

done

echo "========================================================" | tee -a process.log
echo "🎉 Run Complete!" | tee -a process.log
echo "Total Successfully Processed: $total_processed" | tee -a process.log
echo "Total Failed: $total_failed" | tee -a process.log

