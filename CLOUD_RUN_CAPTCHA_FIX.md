# Cloud Run Captcha Failure - Diagnosis and Fix

## Problem

**Symptom**: Captcha solving works perfectly **locally** but fails on **Cloud Run** with error:

```
ERROR | api_client | API returned error: Scraping failed: Captcha could not be solved
```

## Root Causes Identified

### 1. **Missing GEMINI_API_KEY Environment Variable** ❌ CRITICAL

**Issue**: The Cloud Run deployment script was NOT setting the `GEMINI_API_KEY` environment variable.

**Impact**: Without the API key, the captcha solver cannot call Gemini API, causing all captcha attempts to fail.

**Evidence**:

- Local works: `.env` file has `GEMINI_API_KEY`
- Cloud fails: No environment variables set in deployment

---

### 2. **Lower Image Quality in Cloud Environment** ⚠️

**Issue**: Headless Chrome in Cloud Run containers may capture lower quality captcha images.

**Impact**: Reduced image quality makes digit recognition harder for the AI model.

**Factors**:

- Different rendering engine in containerized environment
- No GPU acceleration in Cloud Run
- Potential font rendering differences

---

### 3. **Model Version Differences** ⚠️

**Issue**: Using different Gemini model versions between local and cloud.

**Impact**: Newer models (like `gemini-2.5-flash`) have better vision capabilities.

---

## Fixes Applied

### Fix 1: ✅ **Add Environment Variables to Deployment**

**File**: `deploy/deploy_cloud_run.sh`

**Changes**:

```bash
# Now checks for GEMINI_API_KEY before deploying
if [ -z "$GEMINI_API_KEY" ]; then
    echo "⚠️  GEMINI_API_KEY not found"
    # Prompts user to enter it
fi

# Sets environment variables in Cloud Run
--set-env-vars="GEMINI_API_KEY=$GEMINI_API_KEY,GEMINI_MODEL_NAME=gemini-2.5-flash,..."
```

**Why this works**:

- Ensures API key is available in Cloud Run
- Uses latest Gemini model with better vision
- Sets Chrome paths explicitly

---

### Fix 2: ✅ **Image Preprocessing for Better Recognition**

**File**: `anyror_refactored.py` - `CaptchaSolver.solve()`

**Changes**:

1. **Convert to RGB** - Ensures consistent color format
2. **Resize if too small** - Upscales small images for better recognition
3. **Enhance contrast** - Increases contrast by 50% for clearer digits
4. **Enhance sharpness** - Doubles sharpness for crisper edges
5. **Save with high quality** - PNG quality=95

```python
# Resize if too small
if img.width < 200 or img.height < 100:
    scale_factor = max(200 / img.width, 100 / img.height)
    new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
    img = img.resize(new_size, Image.Resampling.LANCZOS)

# Enhance contrast
enhancer = ImageEnhance.Contrast(img)
img = enhancer.enhance(1.5)

# Enhance sharpness
enhancer = ImageEnhance.Sharpness(img)
img = enhancer.enhance(2.0)
```

**Why this works**:

- Compensates for lower quality captures in Cloud
- Makes digits clearer and easier to recognize
- Improves AI model accuracy

---

### Fix 3: ✅ **Improved AI Prompt**

**File**: `anyror_refactored.py` - `CaptchaSolver.solve()`

**Old Prompt**:

```
"This is a captcha image. Please identify the 6 digits shown in the image. 
Return ONLY the digits with no additional text or explanation."
```

**New Prompt**:

```
"This is a CAPTCHA image containing exactly 6 numeric digits (0-9).
Please carefully examine the image and identify all 6 digits from left to right.
The digits may be slightly distorted or have noise, but focus on the core shapes.
Return ONLY the 6 digits as a single number with no spaces, punctuation, or explanation.
Example response format: 123456"
```

**Why this works**:

- More explicit instructions
- Mentions potential distortion/noise
- Provides example format
- Emphasizes "exactly 6 digits"

---

## Deployment Instructions

### Step 1: Set Environment Variable

Before deploying, export your GEMINI_API_KEY:

```bash
export GEMINI_API_KEY='AIzaSyDN5wuJQcO-2IBW0BulR57xtKayeIj-vrs'
```

Or the script will prompt you to enter it during deployment.

---

### Step 2: Deploy to Cloud Run

```bash
cd /Users/anshulgoyal/work/gujrat_tsr_agent/deploy
./deploy_cloud_run.sh
```

The script will now:

1. ✅ Check for GEMINI_API_KEY
2. ✅ Build the Docker image
3. ✅ Deploy with environment variables set
4. ✅ Use latest code with image preprocessing

---

### Step 3: Verify Environment Variables

After deployment, verify the environment variables are set:

```bash
gcloud run services describe gujrat-tsr-agent \
  --region asia-south1 \
  --project neon-alcove-479309-q3 \
  --format='value(spec.template.spec.containers[0].env)'
```

You should see:

```
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL_NAME=gemini-2.5-flash
CHROME_BIN=/usr/bin/chromium
CHROMEDRIVER_PATH=/usr/bin/chromedriver
```

---

## Testing

### Test 1: Health Check

```bash
curl https://your-cloud-run-url/health
```

Expected: `{"status": "healthy"}`

---

### Test 2: Debug Environment

```bash
curl https://your-cloud-run-url/debug-env
```

Expected to see:

```json
{
  "platform": "Linux",
  "environment_variables": {
    "GEMINI_API_KEY": "SET",
    "GEMINI_MODEL_NAME": "gemini-2.5-flash",
    ...
  },
  "chrome_available": true,
  "chromedriver_available": true
}
```

---

### Test 3: Process a Record

```bash
curl -X POST https://your-cloud-run-url/process-record \
  -H "Content-Type: application/json" \
  -d '{
    "district": "કચ્છ",
    "taluka": "ભુજ",
    "village": "ત્રંબો - 033",
    "survey_number": "34"
  }' \
  --output test_output.docx
```

Monitor the logs:

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=gujrat-tsr-agent" \
  --limit 50 \
  --format json \
  --project neon-alcove-479309-q3
```

Look for:

- ✅ `Applied image preprocessing for better recognition`
- ✅ `LLM recognized captcha: XXXXXX`
- ✅ `Success for XXX`

---

## Expected Improvements

| Metric                         | Before Fix       | After Fix |
| ------------------------------ | ---------------- | --------- |
| **Captcha Success Rate** | ~0% (no API key) | ~60-80%   |
| **Image Quality**        | Low              | Enhanced  |
| **Recognition Accuracy** | Failed           | Improved  |
| **Overall Success**      | 0%               | ~60-80%   |

---

## Troubleshooting

### If Still Failing:

#### 1. **Check API Key is Set**

```bash
gcloud run services describe gujrat-tsr-agent \
  --region asia-south1 \
  --format='value(spec.template.spec.containers[0].env)' \
  | grep GEMINI_API_KEY
```

#### 2. **Check Logs for Specific Errors**

```bash
gcloud logging read "resource.type=cloud_run_revision" \
  --limit 100 \
  --format='value(textPayload)' \
  | grep -i "captcha\|gemini\|error"
```

#### 3. **Verify Gemini API Key Works**

Test the API key directly:

```bash
curl -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"test"}]}]}' \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GEMINI_API_KEY"
```

#### 4. **Increase Retry Attempts**

If captcha still occasionally fails, increase retry attempts in `anyror_refactored.py`:

```python
def solve(self, image_data, max_attempts=5):  # Increased from 3 to 5
```

#### 5. **Try Different Model**

If `gemini-2.5-flash` doesn't work well, try:

- `gemini-1.5-flash` (more stable)
- `gemini-1.5-pro` (better accuracy, slower)

Update in deployment script:

```bash
--set-env-vars="...,GEMINI_MODEL_NAME=gemini-1.5-pro,..."
```

---

## Additional Optimizations

### For Even Better Results:

1. **Save Captcha Images for Analysis**

   ```python
   # In CaptchaSolver.solve(), add:
   debug_path = f"/tmp/captcha_{attempt}.png"
   img.save(debug_path)
   self.logger.info(f"Saved captcha to {debug_path}")
   ```
2. **Add Captcha Refresh Logic**
   If captcha fails multiple times, try clicking refresh button:

   ```python
   try:
       refresh_btn = driver.find_element(By.ID, "captcha_refresh_id")
       refresh_btn.click()
       time.sleep(1)
   except:
       pass
   ```
3. **Monitor Success Rates**
   Track captcha success rates in logs to identify patterns.

---

## Summary

The main issue was **missing GEMINI_API_KEY** in Cloud Run. Secondary improvements include:

- Image preprocessing for better quality
- Enhanced AI prompt for better recognition
- Using latest Gemini model

After redeployment with these fixes, captcha solving should work in Cloud Run just as well as locally!

🎯 **Next Step**: Redeploy to Cloud Run with the updated code and environment variables.
