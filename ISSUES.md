# Known Issues

## 1. Scraper silently selects wrong survey number on partial match failure — RESOLVED

**Status:** RESOLVED (repo cleanup, Phase 2). `anyror/form_filler.py` has been deleted along with the rest of the Selenium stack, so the offending `select.select_by_index(1)` fallback no longer exists.

**File (deleted):** `anyror/form_filler.py` (lines 510-517)

**Problem:** When the scraper could not find a survey number by partial match in the AnyRoR dropdown, it silently fell back to selecting the first option (`select.select_by_index(1)`). This could result in fetching a completely wrong land record — different owner, different area, different chain of title.

**Observed:** For Laiyaree survey 82/1 (District: Kutch, Taluka: Abdasa), the scraper picked up the Thakkar Nenshibhai Hemrajbhai record (1.80 hectares) instead of the Deva Mamubhai Rabari record (3.38 hectares). The same survey number has multiple khata entries on AnyRoR.

**Why it is gone:** the only fetch path is now `anyror/http_fetch.py`, which resolves the survey through `_survey_candidate_texts()` + exact option-text matching and returns an explicit failure when nothing matches — it never guesses. `tests/test_http_fetch.py::TestSurveyCandidates::test_exact_match_not_substring` pins that behaviour.

## 2. Translation service race condition on concurrent requests

**File:** `utils/json_translations.py`

**Problem:** When multiple concurrent requests translate the same new village name (e.g., "palkhada"), the first request fuzzy-matches and calls `_add_spelling_variation()` which modifies the dictionary. Concurrent requests iterating the same dictionary crash with `dictionary changed size during iteration`.

**Observed:** Three parallel requests for Palkhada/Porbandar — first succeeded, other two returned HTTP 400.

**Fix Ideas:**
- Use a threading lock around dictionary mutations in `_add_spelling_variation`.
- Or use `copy()` before iterating in `_fuzzy_match`.
