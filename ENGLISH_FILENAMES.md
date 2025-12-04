# English Filenames Implementation

## Problem

Generated DOCX filenames were using **Gujarati text** (e.g., `TSR_ત્રંબો - 033_149.docx`), which:
- Causes issues with some file systems
- Is hard to read/search
- Not compatible with all applications

## Solution

Implemented **automatic translation** of Gujarati place names to English for filename generation.

---

## What Changed

### Before:
```
TSR_ત્રંબો - 033_149.docx
TSR_કચ્છ_ભુજ_ત્રંબો - 033_34.docx
```

### After:
```
TSR_Kachchh_Bhuj_Trambo_033_149.docx
TSR_Kachchh_Bhuj_Trambo_033_34.docx
```

---

## Implementation Details

### 1. **Added Reverse Translation Function**

**File:** `utils/json_translations.py`

**New Function:**
```python
def translate_to_english(gujarati_text: str, context: str = 'village') -> str:
    """
    Translate Gujarati place name to English (reverse lookup)
    
    Args:
        gujarati_text: Gujarati name
        context: Type ('district', 'taluka', 'village')
    
    Returns:
        English translation (first English name found)
    """
```

**How it works:**
1. Searches reverse lookup cache (`english_to_gujarati`)
2. If found, returns the English name
3. If not in cache, searches hierarchy directly
4. Handles village codes (e.g., "Trambo - 033" → "Trambo_033")
5. Falls back to sanitized Gujarati if no translation found

---

### 2. **Updated API Server**

**File:** `api_server.py`

**Changes:**
```python
# Import translation function
from utils.json_translations import translate_to_english
from utils.survey_utils import sanitize_filename

# In /process-record endpoint:
try:
    district_eng = translate_to_english(request.district, context='district')
    taluka_eng = translate_to_english(request.taluka, context='taluka')
    village_eng = translate_to_english(request.village, context='village')
    survey_eng = sanitize_filename(request.survey_number)
    
    output_filename = f"TSR_{district_eng}_{taluka_eng}_{village_eng}_{survey_eng}.docx"
except Exception as e:
    # Fallback to sanitized Gujarati names
    output_filename = f"TSR_{sanitize_filename(request.village)}_{sanitize_filename(request.survey_number)}.docx"
```

**Benefits:**
- ✅ English filenames for better compatibility
- ✅ Includes district, taluka, village, and survey number
- ✅ Fallback to sanitized names if translation fails
- ✅ Handles special characters and codes properly

---

## Filename Format

### Structure:
```
TSR_{District}_{Taluka}_{Village}_{SurveyNumber}.docx
```

### Examples:

| Input (Gujarati) | Output (English) |
|------------------|------------------|
| કચ્છ, ભુજ, ત્રંબો - 033, 149 | `TSR_Kachchh_Bhuj_Trambo_033_149.docx` |
| કચ્છ, અબડાસા, ત્રંબો - 033, 150/p1 | `TSR_Kachchh_Abdasa_Trambo_033_150_p1.docx` |
| કચ્છ, ભુજ, ત્રંબો - 033, 34 | `TSR_Kachchh_Bhuj_Trambo_033_34.docx` |

---

## Translation Mapping

The translation uses `anyror_hierarchy.json` which contains mappings like:

```json
{
  "કચ્છ": {
    "english_names": ["Kachchh", "Kutch"],
    "talukas": {
      "ભુજ": {
        "english_names": ["Bhuj"],
        "villages": {
          "ત્રંબો - 033": ["Trambo", "Tramboo"]
        }
      }
    }
  }
}
```

The function returns the **first English name** from the list.

---

## Error Handling

### If Translation Fails:

1. **Logs warning**: `Failed to translate filename to English: {error}`
2. **Falls back** to sanitized Gujarati:
   ```python
   output_filename = f"TSR_{sanitize_filename(request.village)}_{sanitize_filename(request.survey_number)}.docx"
   ```
3. **Sanitization** replaces:
   - Spaces → underscores
   - Slashes → underscores
   - Special characters → removed

---

## Testing

### Test the API:

```bash
curl -X POST http://localhost:8000/process-record \
  -H "Content-Type: application/json" \
  -d '{
    "district": "કચ્છ",
    "taluka": "ભુજ",
    "village": "ત્રંબો - 033",
    "survey_number": "149"
  }' \
  --output test.docx
```

**Expected filename:** `TSR_Kachchh_Bhuj_Trambo_033_149.docx`

---

### Test with test_parallel_local.py:

```bash
./venv/bin/python test_parallel_local.py
```

**Expected output:**
```
Success for 149 in 193.87s. Saved to TSR_Kachchh_Trambo_149.docx
Success for 150/p1 in 201.23s. Saved to TSR_Kachchh_Trambo_150_p1.docx
```

---

## Files Modified

1. **`utils/json_translations.py`**:
   - Added `translate_to_english()` function
   - Reverse lookup from Gujarati to English
   - Handles village codes and special characters

2. **`api_server.py`**:
   - Imported translation functions
   - Updated filename generation in `/process-record`
   - Added error handling with fallback

---

## Benefits

✅ **File System Compatibility**: Works on all operating systems  
✅ **Readability**: Easy to identify files  
✅ **Searchability**: Can search by English names  
✅ **Consistency**: Same format for all files  
✅ **Fallback**: Still works if translation fails  
✅ **Detailed**: Includes district, taluka, village, survey  

---

## Deployment

The changes are **already applied** to your local code. To deploy to Cloud Run:

```bash
cd deploy
./deploy_cloud_run.sh
```

The updated code will be deployed with English filename generation.

---

## Summary

Filenames are now generated in **English** using the translation system:
- **Before**: `TSR_ત્રંબો - 033_149.docx`
- **After**: `TSR_Kachchh_Bhuj_Trambo_033_149.docx`

This improves compatibility, readability, and usability across all platforms! 🎉
