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

## 3. `_options` misses any `<option>` whose `value` is not the first attribute — LATENT

**Found:** 2026-08-28, while building `gujtsr/garvi.py` against a captured Garvi page. Not
observed failing on AnyRoR; logged because the trigger is ordinary ASP.NET behaviour, not an
exotic edge case.

**File:** `anyror/http_fetch.py::_options`

```python
re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', m.group(0))
```

**Problem:** the pattern requires `value` to be the **first** attribute inside `<option>`.
ASP.NET WebForms does not guarantee that — it emits the *currently selected* option as
`<option selected="selected" value="12">`. Any such option is skipped silently: no error, no
warning, one fewer entry in the list.

**Why that is dangerous rather than merely untidy:** the option most likely to carry
`selected` is the one the server currently has selected, i.e. after any postback. Code that
reads the list back to confirm a selection would find it absent and could conclude the value
is unavailable — or, worse, fall back to another one. That is the same failure family as
issue #1, which fetched a different owner's record.

**Confirmed on the captured Garvi page:** `cmbDistrict`'s placeholder is
`<option selected="selected" value="0">---Select District---</option>` — this regex drops it.
Dropping *that* one is harmless by luck, since a placeholder should be dropped anyway. It is
luck, not correctness.

**Second, smaller defect in the same line:** the label group is `([^<]*)`, so an option whose
text contains any nested markup is missed too.

**Fix idea:** match the tag first, then pull attributes out of it, rather than assuming order
— `gujtsr/garvi.py::_attr` does this, and also handles single-quoted and bare attribute
values, which this form genuinely uses (`<input name=... type=text size=5 maxlength=5>`).
`tests/test_garvi.py::TestOptions::test_placeholder_is_dropped_even_when_the_value_attribute_comes_last`
pins the behaviour on the Garvi side.
