# Known Issues

## 1. Scraper silently selects wrong survey number on partial match failure

**File:** `anyror/form_filler.py` (lines 510-517)

**Problem:** When the scraper cannot find a survey number by partial match in the AnyRoR dropdown, it silently falls back to selecting the first option (`select.select_by_index(1)`). This can result in fetching a completely wrong land record — different owner, different area, different chain of title.

**Observed:** For Laiyaree survey 82/1 (District: Kutch, Taluka: Abdasa), the scraper picked up the Thakkar Nenshibhai Hemrajbhai record (1.80 hectares) instead of the Deva Mamubhai Rabari record (3.38 hectares). The same survey number has multiple khata entries on AnyRoR.

**Root Cause:**
- AnyRoR dropdown may list entries by khata, not just by survey number.
- A single survey number can have multiple khata entries (different owners on different portions).
- The partial match `"82/1" in option_text` failed (possibly due to Gujarati formatting or khata-prefixed entries).
- The fallback silently picks the first dropdown option without warning the caller.

**Impact:** Generated TSR has completely wrong ownership chain, area, and title holders.

**Fix Ideas:**
- Remove the silent fallback — raise an error or return failure instead of picking the first option.
- Investigate AnyRoR dropdown format to fix partial matching.
- Support khata-based selection when multiple entries exist for the same survey number.
- Log all available dropdown options when a match fails for debugging.

## 2. Translation service race condition on concurrent requests

**File:** `utils/json_translations.py`

**Problem:** When multiple concurrent requests translate the same new village name (e.g., "palkhada"), the first request fuzzy-matches and calls `_add_spelling_variation()` which modifies the dictionary. Concurrent requests iterating the same dictionary crash with `dictionary changed size during iteration`.

**Observed:** Three parallel requests for Palkhada/Porbandar — first succeeded, other two returned HTTP 400.

**Fix Ideas:**
- Use a threading lock around dictionary mutations in `_add_spelling_variation`.
- Or use `copy()` before iterating in `_fuzzy_match`.
