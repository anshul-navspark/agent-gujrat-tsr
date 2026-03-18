# Structured Extraction Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-call LLM prose generation with two-pass structured field extraction and deterministic template rendering.

**Architecture:** Pass 1 classifies entries + extracts land details. Pass 2 extracts type-specific structured fields using a dynamic prompt built from Pass 1 results. Python templates assemble descriptions from structured fields. DOCX renderer uses template output.

**Tech Stack:** Python 3, langchain_google_genai (Gemini), python-docx, pytest

**Spec:** `docs/superpowers/specs/2026-03-18-structured-extraction-pipeline-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|---|---|
| `tsr_generator/extractors/type_configs.py` | Registry of 19 type schemas, few-shot examples, field definitions |
| `tsr_generator/extractors/pass1_prompt.py` | Pass 1 prompt builder (classification + land details) |
| `tsr_generator/extractors/pass2_prompt.py` | Pass 2 dynamic prompt builder (type-aware field extraction) |
| `tsr_generator/extractors/template_renderer.py` | Deterministic description assembly from structured fields |
| `tests/test_type_configs.py` | Tests for type config registry |
| `tests/test_pass1_prompt.py` | Tests for Pass 1 prompt builder |
| `tests/test_pass2_prompt.py` | Tests for Pass 2 dynamic prompt builder |
| `tests/test_template_renderer.py` | Tests for template rendering |
| `tests/test_two_pass_integration.py` | Integration tests for the full two-pass pipeline |

### Modified Files
| File | Changes |
|---|---|
| `tsr_generator/extractors/entry_schema.py` | Add 6 new EntryType values, add new dataclasses (AllotmentEntry, etc.), update fields on existing classes |
| `tsr_generator/extractors/unified_extractor.py` | Replace single LLM call with two-pass orchestration |
| `tsr_generator/extractors/findings.py` | Update `detect_active_encumbrances()` to use structured `lender` field |
| `tsr_generator/document/docx_generator.py` | Use template-rendered descriptions, certification on new line |

---

## Task 1: Update EntryType Enum and Dataclasses

**Files:**
- Modify: `tsr_generator/extractors/entry_schema.py`
- Test: `tests/test_entry_schema.py`

- [ ] **Step 1: Write failing tests for new entry types**

```python
# tests/test_entry_schema.py
from tsr_generator.extractors.entry_schema import EntryType

def test_new_entry_types_exist():
    """All 19 canonical types must exist in the enum."""
    canonical = [
        "SALE", "INHERITANCE", "PARTITION", "RELINQUISHMENT", "EXCHANGE",
        "LIFETIME_DISTRIBUTION", "GIFT", "LOAN", "RELEASE", "SEIZURE",
        "ORDER", "ALLOTMENT", "TENURE_CHANGE", "LAND_ACQUISITION", "LEASE",
        "PROMULGATION", "CORRECTION", "NOT_RELATED", "UNAVAILABLE"
    ]
    for name in canonical:
        assert hasattr(EntryType, name), f"EntryType.{name} missing"

def test_sale_entry_has_structured_fields():
    from tsr_generator.extractors.entry_schema import SaleEntry
    e = SaleEntry(entry_number="1", date="01/01/2020")
    assert hasattr(e, 'sellers')
    assert hasattr(e, 'buyers')
    assert hasattr(e, 'consideration_amount')
    assert hasattr(e, 'document_number')
    assert hasattr(e, 'document_date')
    assert hasattr(e, 'survey_numbers')
    assert hasattr(e, 'area')
    assert isinstance(e.sellers, list)

def test_loan_entry_has_structured_fields():
    from tsr_generator.extractors.entry_schema import LoanEntry
    e = LoanEntry(entry_number="1", date="01/01/2020")
    assert hasattr(e, 'borrowers')
    assert hasattr(e, 'lender')
    assert hasattr(e, 'amount')
    assert hasattr(e, 'survey_numbers')

def test_release_entry_has_structured_fields():
    from tsr_generator.extractors.entry_schema import ReleaseEntry
    e = ReleaseEntry(entry_number="1", date="01/01/2020")
    assert hasattr(e, 'applicants')
    assert hasattr(e, 'lender')
    assert hasattr(e, 'reference_entry_number')
    assert hasattr(e, 'survey_numbers')

def test_allotment_entry_exists():
    from tsr_generator.extractors.entry_schema import AllotmentEntry
    e = AllotmentEntry(entry_number="1", date="01/01/2020")
    assert hasattr(e, 'grantee')
    assert hasattr(e, 'authority')
    assert hasattr(e, 'legal_basis')
    assert hasattr(e, 'survey_numbers')
    assert hasattr(e, 'area')

def test_type_normalization():
    """Non-canonical types should normalize to canonical ones."""
    from tsr_generator.extractors.entry_schema import normalize_entry_type
    assert normalize_entry_type("MORTGAGE") == "LOAN"
    assert normalize_entry_type("DEATH") == "INHERITANCE"
    assert normalize_entry_type("LOAN_CLOSE") == "RELEASE"
    assert normalize_entry_type("TRANSFER") == "SALE"
    assert normalize_entry_type("SUBDIVISION") == "PARTITION"
    assert normalize_entry_type("SALE") == "SALE"  # already canonical
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_entry_schema.py -v`
Expected: FAIL (missing LoanEntry, AllotmentEntry, normalize_entry_type, etc.)

- [ ] **Step 3: Implement enum changes and new dataclasses**

In `entry_schema.py`:
1. Add to `EntryType` enum: `ALLOTMENT`, `TENURE_CHANGE`, `LAND_ACQUISITION`, `LEASE`, `SEIZURE`, `UNAVAILABLE`
2. Update `SaleEntry` fields: add `sellers: List[str]`, `buyers: List[str]`, `survey_numbers: List[str]`, `area: Optional[str]`, `consideration_amount: Optional[str]`, `document_number: Optional[str]`, `document_date: Optional[str]`
3. Rename `MortgageEntry` to `LoanEntry` (keep `MortgageEntry` as alias). Add `borrowers: List[str]`, `lender: Optional[str]`, `survey_numbers: List[str]`, `amount: Optional[str]`
4. Update `ReleaseEntry`: add `applicants: List[str]`, `lender: Optional[str]`, `survey_numbers: List[str]`, `reference_entry_number: Optional[str]`
5. Update `InheritanceEntry`: add `survey_numbers: List[str]`, `area: Optional[str]`
6. Update `PartitionEntry`: add `survey_numbers: List[str]`, `area: Optional[str]`, `allocations: List[Dict]`
7. Add new dataclasses: `AllotmentEntry`, `TenureChangeEntry`, `LandAcquisitionEntry`, `LeaseEntry`, `SeizureEntry`, `ExchangeEntry`, `LifetimeDistributionEntry`, `GiftEntry`, `UnavailableEntry`, `NotRelatedEntry`
8. Add `normalize_entry_type(type_str: str) -> str` function with the normalization table from the spec
9. Update `create_entry_from_dict()` to use `normalize_entry_type()` and create the new entry types

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_entry_schema.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest --tb=short -q`
Expected: All previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add tsr_generator/extractors/entry_schema.py tests/test_entry_schema.py
git commit -m "feat: add 19 canonical entry types with structured fields and type normalization"
```

---

## Task 2: Type Config Registry

**Files:**
- Create: `tsr_generator/extractors/type_configs.py`
- Test: `tests/test_type_configs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_type_configs.py
from tsr_generator.extractors.type_configs import TYPE_CONFIGS, get_config_for_types

def test_all_19_types_have_configs():
    canonical = [
        "SALE", "INHERITANCE", "PARTITION", "RELINQUISHMENT", "EXCHANGE",
        "LIFETIME_DISTRIBUTION", "GIFT", "LOAN", "RELEASE", "SEIZURE",
        "ORDER", "ALLOTMENT", "TENURE_CHANGE", "LAND_ACQUISITION", "LEASE",
        "PROMULGATION", "CORRECTION", "NOT_RELATED", "UNAVAILABLE"
    ]
    for t in canonical:
        assert t in TYPE_CONFIGS, f"Missing config for {t}"

def test_each_config_has_required_keys():
    for type_name, config in TYPE_CONFIGS.items():
        assert "fields" in config, f"{type_name} missing 'fields'"
        assert "template" in config, f"{type_name} missing 'template'"
        assert "examples" in config, f"{type_name} missing 'examples'"

def test_fixed_text_types_have_no_fields():
    assert TYPE_CONFIGS["NOT_RELATED"]["fields"] == {}
    assert TYPE_CONFIGS["UNAVAILABLE"]["fields"] == {}

def test_get_config_for_types_filters():
    configs = get_config_for_types(["SALE", "LOAN"])
    assert "SALE" in configs
    assert "LOAN" in configs
    assert "INHERITANCE" not in configs

def test_sale_config_has_expected_fields():
    sale = TYPE_CONFIGS["SALE"]
    assert "sellers" in sale["fields"]
    assert "buyers" in sale["fields"]
    assert "consideration_amount" in sale["fields"]

def test_each_non_fixed_type_has_examples():
    fixed = {"NOT_RELATED", "UNAVAILABLE"}
    for type_name, config in TYPE_CONFIGS.items():
        if type_name not in fixed:
            assert len(config["examples"]) >= 1, f"{type_name} needs at least 1 example"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_type_configs.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement type_configs.py**

Create `tsr_generator/extractors/type_configs.py` with:
1. `TYPE_CONFIGS` dict — one key per canonical type, each containing:
   - `"fields"`: dict of field_name -> field_type_description (e.g. `{"sellers": "[string]", "buyers": "[string]", ...}`)
   - `"template"`: the description template string from the spec
   - `"examples"`: list of `{"input": "raw entry text", "output": {structured JSON}}` dicts
   - For NOT_RELATED and UNAVAILABLE: `"fields": {}`, `"examples": []`
2. `get_config_for_types(types: List[str]) -> Dict` — returns subset of TYPE_CONFIGS for only the requested types
3. Pull 2-3 real examples per type from `sampleentry.md` content (hardcoded in the file as string constants)

**Note:** For GIFT and ORDER where sampleentry.md has few examples, include what's available. User will provide additional examples later.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_type_configs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tsr_generator/extractors/type_configs.py tests/test_type_configs.py
git commit -m "feat: add type config registry with schemas, templates, and few-shot examples"
```

---

## Task 3: Template Renderer

**Files:**
- Create: `tsr_generator/extractors/template_renderer.py`
- Test: `tests/test_template_renderer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_template_renderer.py
from tsr_generator.extractors.template_renderer import render_entry_description

def test_render_sale_all_fields():
    fields = {
        "sellers": ["Thakor Chaturji Gelaji", "Thakor Amartji Gelaji"],
        "buyers": ["Bharwad Nagjibhai Motibhai"],
        "survey_numbers": ["105"],
        "area": "0-80-94 Hectare",
        "consideration_amount": "2,50,000",
        "document_number": "484/2022",
        "document_date": "16/06/2022"
    }
    result = render_entry_description("SALE", fields)
    assert "Thakor Chaturji Gelaji" in result
    assert "Bharwad Nagjibhai Motibhai" in result
    assert "Rs. 2,50,000/-" in result
    assert "document no. 484/2022" in result
    assert result.startswith("That ")

def test_render_sale_missing_document():
    fields = {
        "sellers": ["Name A"],
        "buyers": ["Name B"],
        "survey_numbers": ["100"],
        "area": "1-00-00 Hectare",
        "consideration_amount": "1,00,000",
    }
    result = render_entry_description("SALE", fields)
    assert "Name A" in result
    assert "document no." not in result  # clause omitted

def test_render_loan():
    fields = {
        "borrowers": ["Thakor Chaturji Gelaji"],
        "lender": "Bank of Baroda",
        "survey_numbers": ["105", "141"],
        "amount": "1,50,000"
    }
    result = render_entry_description("LOAN", fields)
    assert "Bank of Baroda" in result
    assert "Rs. 1,50,000/-" in result
    assert "Survey No. 105, 141" in result

def test_render_release():
    fields = {
        "applicants": ["Thakor Chaturji Gelaji"],
        "lender": "Bank of Baroda",
        "reference_entry_number": "3521"
    }
    result = render_entry_description("RELEASE", fields)
    assert "exemption of burden" in result
    assert "Entry No. 3521" in result

def test_render_inheritance():
    fields = {
        "deceased": "Bharwad Motibhai Sagarambhai",
        "heirs": ["Bharwad Zabiben Motibhai", "Bharwad Bhikhabhai Motibhai"],
        "survey_numbers": ["103", "104"],
        "area": "5-00-00 Hectare"
    }
    result = render_entry_description("INHERITANCE", fields)
    assert "demise of Bharwad Motibhai" in result
    assert "Bharwad Zabiben Motibhai" in result

def test_render_not_related():
    result = render_entry_description("NOT_RELATED", {})
    assert result == "This entry is not related to the present survey number(s)."

def test_render_unavailable():
    result = render_entry_description("UNAVAILABLE", {})
    assert result == "The data for this entry is not available."

def test_render_empty_fields_returns_empty():
    result = render_entry_description("SALE", {})
    assert result == ""

def test_render_partition_with_allocations():
    fields = {
        "original_owner": "Vadher Sankarbhai Ramabhai",
        "allocations": [
            {"name": "Vadher Hamirbhai Shankarbhai", "survey_number": "122", "area": "3-12"},
            {"name": "Vadher Nanubhai Shankarbhai", "survey_number": "213", "area": "4-28"},
        ]
    }
    result = render_entry_description("PARTITION", fields)
    assert "Vadher Sankarbhai" in result
    assert "Vadher Hamirbhai" in result
    assert "122" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_template_renderer.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement template_renderer.py**

Create `tsr_generator/extractors/template_renderer.py` with:

```python
"""Deterministic description assembly from structured entry fields."""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def render_entry_description(entry_type: str, fields: Dict[str, Any]) -> str:
    """
    Render a description string for an entry using its type template and structured fields.

    Args:
        entry_type: Canonical type string (e.g., "SALE", "LOAN")
        fields: Dict of extracted structured fields

    Returns:
        Assembled description string. Empty string if no fields populated.
    """
    renderer = RENDERERS.get(entry_type)
    if renderer is None:
        logger.warning(f"No renderer for type {entry_type}")
        return ""

    result = renderer(fields)
    logger.debug(f"Render: Entry ({entry_type}) -> {len(result)} chars")
    return result
```

Then implement a `_render_<type>(fields) -> str` function for each of the 19 types. Each function:
1. Checks which fields are present and non-empty
2. Builds the description by including only clauses for present fields
3. Returns empty string if no type-specific fields are populated
4. For list fields, joins with ", " (last item with " and " for names)
5. For amounts, wraps with "Rs. " prefix and "/-" suffix
6. For survey numbers, joins with ", " and prefixes with "Survey No. "

Register all renderers in a `RENDERERS` dict mapping type string to function.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_template_renderer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tsr_generator/extractors/template_renderer.py tests/test_template_renderer.py
git commit -m "feat: add deterministic template renderer for all 19 entry types"
```

---

## Task 4: Pass 1 Prompt Builder

**Files:**
- Create: `tsr_generator/extractors/pass1_prompt.py`
- Test: `tests/test_pass1_prompt.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pass1_prompt.py
from tsr_generator.extractors.pass1_prompt import build_pass1_prompt, parse_pass1_response

def test_build_pass1_prompt_contains_key_sections():
    prompt = build_pass1_prompt("sample pdf text here")
    assert "land_details" in prompt
    assert "entries" in prompt
    assert "certification_status" in prompt
    assert "certification_official" in prompt
    assert "type" in prompt
    # Should NOT contain description extraction instructions
    assert "description" not in prompt.lower() or "do not extract descriptions" in prompt.lower()

def test_build_pass1_prompt_includes_type_list():
    prompt = build_pass1_prompt("sample text")
    assert "SALE" in prompt
    assert "LOAN" in prompt
    assert "INHERITANCE" in prompt
    assert "UNAVAILABLE" in prompt

def test_parse_pass1_response_valid_json():
    response = '{"land_details": {"village_name": "Test"}, "entries": [{"entry_number": "100", "date": "01/01/2020", "type": "SALE", "certification_status": "certified", "certification_official": "C.O. Test", "certification_date": "01/01/2020"}]}'
    result = parse_pass1_response(response)
    assert result["land_details"]["village_name"] == "Test"
    assert len(result["entries"]) == 1
    assert result["entries"][0]["type"] == "SALE"

def test_parse_pass1_normalizes_types():
    response = '{"land_details": {}, "entries": [{"entry_number": "1", "date": "", "type": "MORTGAGE", "certification_status": "", "certification_official": "", "certification_date": ""}]}'
    result = parse_pass1_response(response)
    assert result["entries"][0]["type"] == "LOAN"

def test_parse_pass1_normalizes_dates():
    response = '{"land_details": {}, "entries": [{"entry_number": "1", "date": "01/01/20", "type": "SALE", "certification_status": "certified", "certification_official": "", "certification_date": "15/06/22"}]}'
    result = parse_pass1_response(response)
    assert result["entries"][0]["date"] == "01/01/2020"
    assert result["entries"][0]["certification_date"] == "15/06/2022"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_pass1_prompt.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pass1_prompt.py**

Create `tsr_generator/extractors/pass1_prompt.py` with:

1. `build_pass1_prompt(pdf_text: str, entry_numbers_hint: List[str] = None) -> str` — builds the classification prompt. Includes:
   - JSON schema for output (land_details + entries array with entry_number, date, type, certification fields)
   - List of 19 canonical types with brief classification rules
   - Gujarati certification status translation table
   - Instructions to classify entries and extract land details, NOT descriptions
   - The PDF text

2. `parse_pass1_response(response: str) -> Dict` — parses and normalizes:
   - Extracts JSON from response (reuse `_parse_json_response` pattern from unified_extractor)
   - Normalizes types using `normalize_entry_type()`
   - Normalizes dates using `_normalize_date_str()`
   - Normalizes land details (Gujarati numerals, etc.)

- [ ] **Step 4: Run tests**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_pass1_prompt.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tsr_generator/extractors/pass1_prompt.py tests/test_pass1_prompt.py
git commit -m "feat: add Pass 1 prompt builder for entry classification and land details"
```

---

## Task 5: Pass 2 Dynamic Prompt Builder

**Files:**
- Create: `tsr_generator/extractors/pass2_prompt.py`
- Test: `tests/test_pass2_prompt.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pass2_prompt.py
from tsr_generator.extractors.pass2_prompt import build_pass2_prompt, parse_pass2_response

def test_build_pass2_includes_only_relevant_types():
    entries = [
        {"entry_number": "100", "type": "SALE"},
        {"entry_number": "200", "type": "LOAN"},
    ]
    prompt = build_pass2_prompt("pdf text", entries)
    assert "SALE" in prompt
    assert "LOAN" in prompt
    assert "sellers" in prompt
    assert "borrowers" in prompt
    # Types NOT in the document should NOT be in prompt
    assert "SEIZURE" not in prompt or "seizure" not in prompt.lower()

def test_build_pass2_includes_few_shot_examples():
    entries = [{"entry_number": "100", "type": "SALE"}]
    prompt = build_pass2_prompt("pdf text", entries)
    assert "Example" in prompt or "example" in prompt

def test_build_pass2_lists_entry_numbers():
    entries = [
        {"entry_number": "100", "type": "SALE"},
        {"entry_number": "200", "type": "SALE"},
    ]
    prompt = build_pass2_prompt("pdf text", entries)
    assert "100" in prompt
    assert "200" in prompt

def test_build_pass2_skips_fixed_text_types():
    entries = [
        {"entry_number": "100", "type": "NOT_RELATED"},
        {"entry_number": "200", "type": "UNAVAILABLE"},
        {"entry_number": "300", "type": "SALE"},
    ]
    prompt = build_pass2_prompt("pdf text", entries)
    # Fixed types don't need Pass 2 extraction
    assert "300" in prompt
    # NOT_RELATED and UNAVAILABLE entries should not be requested for extraction

def test_parse_pass2_response():
    response = '[{"entry_number": "100", "sellers": ["A"], "buyers": ["B"], "survey_numbers": ["10"], "consideration_amount": "1,00,000"}]'
    result = parse_pass2_response(response)
    assert len(result) == 1
    assert result[0]["sellers"] == ["A"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_pass2_prompt.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pass2_prompt.py**

Create `tsr_generator/extractors/pass2_prompt.py` with:

1. `build_pass2_prompt(pdf_text: str, classified_entries: List[Dict]) -> str` — dynamically builds the extraction prompt:
   - Collects unique types from classified entries (excluding NOT_RELATED, UNAVAILABLE)
   - For each type found, includes from `TYPE_CONFIGS`: field schema + few-shot examples
   - Lists each entry with its number and type for the LLM
   - Instructs LLM to extract ONLY structured fields, no prose
   - Appends the PDF text

2. `parse_pass2_response(response: str) -> List[Dict]` — parses the response:
   - Extracts JSON array from response
   - Returns list of dicts with entry_number + type-specific fields

- [ ] **Step 4: Run tests**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_pass2_prompt.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tsr_generator/extractors/pass2_prompt.py tests/test_pass2_prompt.py
git commit -m "feat: add Pass 2 dynamic prompt builder with type-aware field extraction"
```

---

## Task 6: Two-Pass Orchestration in unified_extractor.py

**Files:**
- Modify: `tsr_generator/extractors/unified_extractor.py`
- Test: `tests/test_two_pass_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_two_pass_integration.py
"""Integration tests for the two-pass extraction pipeline.
These tests mock the LLM calls but test the full orchestration."""
import json
from unittest.mock import patch, MagicMock
from tsr_generator.extractors.unified_extractor import extract_all_unified, UnifiedExtractionResult

def _mock_pass1_response():
    return json.dumps({
        "land_details": {
            "village_name": "Sami", "taluka_name": "Sami",
            "district_name": "Patan", "survey_numbers": ["105"],
            "old_survey_numbers": [], "survey_number_mapping": {},
            "total_area": "0-80-94", "nature_of_land": "Agricultural",
            "owners": ["Thakor Chaturji Gelaji"]
        },
        "entries": [
            {"entry_number": "3521", "date": "04/09/2013", "type": "LOAN",
             "certification_status": "certified", "certification_official": "C.O. Sami",
             "certification_date": "10/10/2013"},
            {"entry_number": "4531", "date": "07/05/2022", "type": "RELEASE",
             "certification_status": "certified", "certification_official": "C.O. Sami",
             "certification_date": "07/06/2022"},
            {"entry_number": "903", "date": "", "type": "NOT_RELATED",
             "certification_status": "", "certification_official": "",
             "certification_date": ""},
        ]
    })

def _mock_pass2_response():
    return json.dumps([
        {"entry_number": "3521", "borrowers": ["Thakor Chaturji Gelaji"],
         "lender": "Bank of Baroda", "survey_numbers": ["105"],
         "amount": "1,50,000"},
        {"entry_number": "4531", "applicants": ["Thakor Chaturji Gelaji"],
         "lender": "Bank of Baroda", "survey_numbers": ["105"],
         "reference_entry_number": "3521"},
    ])

@patch('tsr_generator.extractors.unified_extractor._invoke_with_retry')
def test_two_pass_produces_structured_entries(mock_invoke):
    """Full pipeline: Pass 1 -> Pass 2 -> structured entries."""
    # Mock returns Pass 1 response first, then Pass 2
    mock_resp1 = MagicMock()
    mock_resp1.content = _mock_pass1_response()
    mock_resp2 = MagicMock()
    mock_resp2.content = _mock_pass2_response()
    mock_invoke.side_effect = [mock_resp1, mock_resp2]

    result = extract_all_unified("fake pdf text")
    assert result.success
    assert len(result.mutation_entries) == 3
    # LOAN entry should have structured lender field
    loan = [e for e in result.mutation_entries if e.get('type') == 'LOAN'][0]
    assert loan['lender'] == 'Bank of Baroda'
    # NOT_RELATED should pass through with no extra fields
    nr = [e for e in result.mutation_entries if e.get('type') == 'NOT_RELATED'][0]
    assert nr['entry_number'] == '903'

@patch('tsr_generator.extractors.unified_extractor._invoke_with_retry')
def test_pass2_failure_degrades_gracefully(mock_invoke):
    """If Pass 2 fails, entries should still have Pass 1 data."""
    mock_resp1 = MagicMock()
    mock_resp1.content = _mock_pass1_response()
    mock_invoke.side_effect = [mock_resp1, Exception("API error")]

    result = extract_all_unified("fake pdf text")
    assert result.success  # Still succeeds with degraded data
    assert len(result.mutation_entries) == 3
    # Entries have Pass 1 data (type, date, certification) but no type-specific fields
    loan = [e for e in result.mutation_entries if e.get('type') == 'LOAN'][0]
    assert loan['entry_number'] == '3521'
    assert loan['certification_official'] == 'C.O. Sami'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_two_pass_integration.py -v`
Expected: FAIL (current extract_all_unified doesn't do two passes)

- [ ] **Step 3: Rewrite extract_all_unified()**

Modify `tsr_generator/extractors/unified_extractor.py`:

1. Keep `UnifiedExtractionResult` class, `_normalize_date_str()`, `_parse_json_response()`, `_invoke_with_retry()`, `_identify_entry_numbers_fast()`, `_extract_relevant_sections()`
2. Remove: `build_unified_prompt()`, `ENTRY_TYPE_RULES`, `FORMATTING_RULES`, `DESCRIPTION_EXAMPLES`, `CERTIFICATION_PATTERNS` (these are replaced by pass1/pass2 prompts)
3. Rewrite `extract_all_unified(pdf_text: str)`:
   ```python
   def extract_all_unified(pdf_text: str) -> UnifiedExtractionResult:
       result = UnifiedExtractionResult()
       import time

       try:
           document_text = _extract_relevant_sections(pdf_text)
           entry_numbers_hint = _identify_entry_numbers_fast(pdf_text)

           # Initialize LLM
           load_dotenv()
           from langchain_google_genai import ChatGoogleGenerativeAI
           llm = ChatGoogleGenerativeAI(
               model=MODEL_NAME,
               google_api_key=os.getenv('GEMINI_API_KEY', ''),
               temperature=0.0,
               convert_system_message_to_human=True,
           )

           # === PASS 1: Classification + Land Details ===
           t1_start = time.time()
           from .pass1_prompt import build_pass1_prompt, parse_pass1_response
           pass1_prompt = build_pass1_prompt(document_text, entry_numbers_hint)
           logger.debug(f"Pass 1 prompt: {len(pass1_prompt)} chars")

           response1 = _invoke_with_retry(llm, pass1_prompt, max_retries=3)
           content1 = response1.content if hasattr(response1, 'content') else str(response1)
           logger.debug(f"Pass 1 raw response: {content1[:500]}...")

           pass1_data = parse_pass1_response(content1)
           t1_ms = int((time.time() - t1_start) * 1000)

           result.land_details = pass1_data.get('land_details', {})
           classified_entries = pass1_data.get('entries', [])
           result.entry_numbers = [e['entry_number'] for e in classified_entries]

           type_counts = {}
           for e in classified_entries:
               t = e.get('type', 'UNKNOWN')
               type_counts[t] = type_counts.get(t, 0) + 1
           logger.info(f"Pass 1 complete ({t1_ms}ms): {len(classified_entries)} entries, types: {type_counts}")

           # === PASS 2: Structured Field Extraction ===
           t2_start = time.time()
           pass2_fields = {}
           try:
               from .pass2_prompt import build_pass2_prompt, parse_pass2_response
               pass2_prompt = build_pass2_prompt(document_text, classified_entries)

               if pass2_prompt:  # None if all entries are fixed-text types
                   logger.debug(f"Pass 2 prompt: {len(pass2_prompt)} chars")
                   response2 = _invoke_with_retry(llm, pass2_prompt, max_retries=3)
                   content2 = response2.content if hasattr(response2, 'content') else str(response2)
                   logger.debug(f"Pass 2 raw response: {content2[:500]}...")

                   pass2_entries = parse_pass2_response(content2)
                   for entry_fields in pass2_entries:
                       en = entry_fields.get('entry_number', '')
                       pass2_fields[en] = entry_fields
           except Exception as e:
               logger.warning(f"Pass 2 failed, degrading to Pass 1 data only: {e}")

           t2_ms = int((time.time() - t2_start) * 1000)
           n_incomplete = len(classified_entries) - len(pass2_fields)

           # === MERGE Pass 1 + Pass 2 ===
           result.mutation_entries = []
           for entry in classified_entries:
               merged = dict(entry)  # Start with Pass 1 data
               en = entry.get('entry_number', '')
               if en in pass2_fields:
                   merged.update(pass2_fields[en])  # Add Pass 2 fields
               result.mutation_entries.append(merged)

           result.success = True
           logger.info(f"Extraction complete: {len(classified_entries)} entries, "
                       f"Pass 1: {t1_ms}ms, Pass 2: {t2_ms}ms, "
                       f"Types: {type_counts}, Incomplete: {n_incomplete}")

       except Exception as e:
           result.error = str(e)
           logger.error(f"Extraction error: {e}")
           logger.error(traceback.format_exc())

       return result
   ```

- [ ] **Step 4: Run integration tests**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_two_pass_integration.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest --tb=short -q`
Expected: All tests pass (some pre-existing failures may remain)

- [ ] **Step 6: Commit**

```bash
git add tsr_generator/extractors/unified_extractor.py tests/test_two_pass_integration.py
git commit -m "feat: replace single LLM call with two-pass structured extraction"
```

---

## Task 7: Update findings.py for Structured Fields

**Files:**
- Modify: `tsr_generator/extractors/findings.py`
- Test: `tests/test_findings_structured.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_findings_structured.py
from tsr_generator.extractors.findings import detect_active_encumbrances

def test_detects_active_loan_from_structured_fields():
    entries = [
        {"entry_number": "100", "type": "LOAN", "lender": "Bank of Baroda",
         "description": ""},
    ]
    active, nums = detect_active_encumbrances(entries)
    assert "100" in nums

def test_release_clears_loan_by_lender():
    entries = [
        {"entry_number": "100", "type": "LOAN", "lender": "Bank of Baroda",
         "description": ""},
        {"entry_number": "200", "type": "RELEASE", "lender": "Bank of Baroda",
         "reference_entry_number": "100", "description": ""},
    ]
    active, nums = detect_active_encumbrances(entries)
    assert len(nums) == 0

def test_release_clears_loan_by_reference():
    entries = [
        {"entry_number": "100", "type": "LOAN", "lender": "SBI",
         "description": ""},
        {"entry_number": "200", "type": "RELEASE", "lender": "",
         "reference_entry_number": "100", "description": ""},
    ]
    active, nums = detect_active_encumbrances(entries)
    assert len(nums) == 0

def test_seizure_not_counted_as_encumbrance():
    entries = [
        {"entry_number": "100", "type": "LOAN", "lender": "SBI",
         "description": ""},
        {"entry_number": "200", "type": "SEIZURE", "bank": "SBI",
         "reference_entry_number": "100", "description": ""},
    ]
    active, nums = detect_active_encumbrances(entries)
    # Loan is still active (seizure doesn't clear it), but seizure itself is not a separate encumbrance
    assert "100" in nums
    assert "200" not in nums
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_findings_structured.py -v`
Expected: FAIL

- [ ] **Step 3: Update detect_active_encumbrances()**

Modify `tsr_generator/extractors/findings.py`:

Update `detect_active_encumbrances()` to:
1. Read `entry.get('lender')` directly for LOAN and RELEASE entries (no regex needed)
2. Read `entry.get('reference_entry_number')` for RELEASE entries (explicit entry reference)
3. Keep the existing matching logic as fallback (regex on description) for backward compatibility
4. Ignore SEIZURE entries in encumbrance counting
5. Log which matching strategy was used (structured vs regex fallback)

- [ ] **Step 4: Run tests**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_findings_structured.py tests/test_findings_crossref.py -v`
Expected: PASS (both new and existing tests)

- [ ] **Step 5: Commit**

```bash
git add tsr_generator/extractors/findings.py tests/test_findings_structured.py
git commit -m "feat: update encumbrance detection to use structured lender fields"
```

---

## Task 8: Update DOCX Generator for Template Rendering + Certification on New Line

**Files:**
- Modify: `tsr_generator/document/docx_generator.py`
- Test: `tests/test_docx_certification.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_docx_certification.py
"""Test that certification renders on a new line, not inline."""
from unittest.mock import MagicMock, patch
from docx import Document
from tsr_generator.document.docx_generator import add_chain_of_title_section
from tsr_generator.extractors.entry_schema import LoanEntry, EntryType

def test_certification_on_new_line():
    """Certification should be in a separate paragraph/line, not inline with description."""
    doc = Document()
    entry = LoanEntry(
        entry_number="100", date="01/01/2020", type=EntryType.LOAN,
        raw_description="test", formatted_description="That test description.",
        certification="The Entry is certified by C.O. Test on 01/01/2020.",
        entry_status="certified",
        certification_official="C.O. Test",
        certification_date="01/01/2020"
    )
    # Mock template renderer to return a known description
    with patch('tsr_generator.document.docx_generator.render_entry_description',
               return_value="That test description."):
        result = add_chain_of_title_section(doc, [entry], [100])

    # Check the table cell content
    table = doc.tables[0]
    cell = table.rows[1].cells[1]
    # Should have at least 2 paragraphs (description + certification)
    # or use line breaks within same paragraph
    full_text = cell.text
    assert "That test description." in full_text
    assert "The Entry is certified" in full_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_docx_certification.py -v`
Expected: FAIL

- [ ] **Step 3: Update docx_generator.py**

Modify `tsr_generator/document/docx_generator.py` `add_chain_of_title_section()`:

1. Import `render_entry_description` from `template_renderer.py`
2. For each entry, call `render_entry_description(entry_type, structured_fields)` to get the description
3. If the renderer returns non-empty text, use it. Otherwise fall back to `entry.formatted_description`
4. Change certification rendering: instead of appending to same paragraph with `" " + certification_text`, add a line break (`OxmlElement` `<w:br/>`) before certification text so it appears on a new line with no gap

Key change for certification (replace line ~312):
```python
# OLD: cert_run = entry_para.add_run(" " + certification_text)
# NEW: Add line break then certification
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
br = OxmlElement('w:br')
entry_para._p.append(br)
cert_run = entry_para.add_run(certification_text)
cert_run.font.name = 'Times New Roman'
cert_run.font.size = Pt(12.5)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest tests/test_docx_certification.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add tsr_generator/document/docx_generator.py tests/test_docx_certification.py
git commit -m "feat: use template renderer for descriptions, certification on new line"
```

---

## Task 9: Update tsr_generator_optimized.py for New Pipeline

**Files:**
- Modify: `tsr_generator/api/tsr_generator_optimized.py`

- [ ] **Step 1: Update the orchestration**

The key change is that `extract_all_unified()` now returns mutation entries with structured fields. The `process_entry_details()` call in `tsr_generator_optimized.py` (line 123-126) needs to work with the new structured entries.

Update `tsr_generator_optimized.py`:
1. After `extract_all_unified()`, the `result.mutation_entries` now contain structured fields
2. `process_entry_details()` should still work (it calls `create_entry_from_dict()` which now creates the right typed entry objects)
3. The `render_entry_description()` call happens inside `docx_generator.py`, so no changes needed here for rendering
4. Verify the flow still works end-to-end

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest --tb=short -q`
Expected: PASS

- [ ] **Step 3: Commit if any changes were needed**

```bash
git add tsr_generator/api/tsr_generator_optimized.py
git commit -m "fix: update optimized generator for two-pass extraction pipeline"
```

---

## Task 10: End-to-End Smoke Test

**Files:**
- No new files

- [ ] **Step 1: Start the API server**

```bash
cd /Users/anshulgoyal/work/gujrat_tsr_agent && ./venv/bin/python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Process a test PDF through the API**

Pick one of the existing PDFs and process it:
```bash
curl -X POST http://127.0.0.1:8000/process-record \
  -H "Content-Type: application/json" \
  -d '{"district": "...", "taluka": "...", "village": "...", "survey_number": "..."}'
```

- [ ] **Step 3: Compare output DOCX with manually-typed version**

Open the generated DOCX and verify:
- Entry descriptions are assembled from templates (not LLM prose)
- Certification appears on new line with no gap
- Active encumbrances detected correctly
- All entry types render correctly
- No regressions from previous output quality

- [ ] **Step 4: Check logs for two-pass execution**

Verify logs show:
```
Pass 1 complete (XXms): N entries, types: {...}
...
Extraction complete: N entries, Pass 1: XXms, Pass 2: XXms, Types: {...}, Incomplete: N
```

- [ ] **Step 5: Run full test suite one final time**

Run: `cd /Users/anshulgoyal/work/gujrat_tsr_agent && python -m pytest --tb=short -q`
Expected: All tests pass
