# TSR Language & Content Quality Improvement — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring AI-generated TSR documents to parity with manually-generated versions across language, formatting, and content cross-referencing.

**Architecture:** Hybrid approach — LLM prompt changes improve extraction quality, deterministic template changes guarantee phrasing/formatting, and a new data-flow path threads chain-of-title row mappings into the findings table for dynamic cross-references.

**Tech Stack:** Python, python-docx, Google Gemini LLM, pytest

**Spec:** `docs/superpowers/specs/2026-03-17-tsr-language-quality-design.md`

---

### Task 1: Reverse date normalization — expand 2-digit years to 4-digit

**Files:**
- Modify: `tsr_generator/extractors/unified_extractor.py:337-359`
- Test: `tests/test_date_normalization.py` (create)

- [ ] **Step 1: Write failing tests for date normalization**

```python
# tests/test_date_normalization.py
from tsr_generator.extractors.unified_extractor import _normalize_date_str

def test_2digit_year_modern():
    assert _normalize_date_str("08/03/04") == "08/03/2004"
    assert _normalize_date_str("15/06/00") == "15/06/2000"
    assert _normalize_date_str("01/01/30") == "01/01/2030"

def test_2digit_year_old():
    assert _normalize_date_str("22/08/96") == "22/08/1996"
    assert _normalize_date_str("10/05/31") == "10/05/1931"
    assert _normalize_date_str("01/01/99") == "01/01/1999"

def test_4digit_year_preserved():
    assert _normalize_date_str("08/03/2004") == "08/03/2004"
    assert _normalize_date_str("22/08/1996") == "22/08/1996"

def test_empty_and_invalid():
    assert _normalize_date_str("") == ""
    assert _normalize_date_str("not a date") == "not a date"

def test_dash_separator():
    assert _normalize_date_str("08-03-04") == "08/03/2004"

def test_single_digit_padding():
    assert _normalize_date_str("8/3/04") == "08/03/2004"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_date_normalization.py -v`
Expected: FAIL — current `_normalize_date_str` converts 4-digit TO 2-digit, so assertions fail.

- [ ] **Step 3: Implement the reversed normalization**

In `tsr_generator/extractors/unified_extractor.py`, replace lines 337-359:

```python
def _normalize_date_str(date_str: str) -> str:
    """
    Normalize common date formats to DD/MM/YYYY.
    Accepts DD/MM/YY or DD/MM/YYYY (or with '-') and expands to 4-digit year.
    Heuristic: 00-30 -> 2000-2030, 31-99 -> 1931-1999.
    """
    if not date_str:
        return ""

    s = str(date_str).strip()
    m = re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})', s)
    if not m:
        return s

    dd, mm, yy = m.group(1), m.group(2), m.group(3)
    dd = dd.zfill(2)
    mm = mm.zfill(2)

    # Expand 2-digit year to 4-digit
    if len(yy) == 2:
        yy_int = int(yy)
        if yy_int <= 30:
            yy = f"20{yy}"
        else:
            yy = f"19{yy}"

    return f"{dd}/{mm}/{yy}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_date_normalization.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tsr_generator/extractors/unified_extractor.py tests/test_date_normalization.py
git commit -m "fix: reverse date normalization to expand 2-digit years to 4-digit"
```

---

### Task 2: Update LLM prompt constants

**Files:**
- Modify: `tsr_generator/extractors/unified_extractor.py:44-230`

- [ ] **Step 1: Update FORMATTING_RULES (lines 60-81)**

Replace the entire `FORMATTING_RULES` constant:

```python
FORMATTING_RULES = """
Formatting Rules:
1. ALL descriptions MUST start with "That" (except NOT RELATED, PROMULGATION)
2. DO NOT use honorifics like "Shri", "Smt", "Mr.", "Mrs."
3. DO NOT use "account holder", "mortgaged his total land", "of [village] village"
4. DO NOT include sentences like "This encumbrance entry was recorded based on..." or "This inheritance entry was made..."
5. Keep descriptions direct and factual. Include all legally relevant details. Do not add commentary or explanatory sentences.
6. Amounts: "Rs. X/-" or "Rs. X,XXX/-"
7. ALWAYS use "Survey No." instead of "Khata No." or "Account No."
8. Documents: "document no. X dated DD/MM/YYYY"
9. Translate "Paiki" or "Part" or "part" or "pk" as "p" in survey numbers (e.g. "150/p1")
10. IMPORTANT: Preserve "/" in survey numbers (e.g., "387/p3" NOT "387p3")
11. Use caste titles only when part of the name: Thakor, Patel, Kanbi, Choudhary, Rabari, Vadher, Solanki
12. Measurements: Use "Acre/Guntha" or "Hectare" in descriptions. For the total_area field, output ONLY the numeric format (e.g., "1-88-48") WITHOUT the word "Hectare".
13. Translate "bhen" or "ben" suffix as "ben" (e.g. "Shantiben")
14. Lists: "which are as follows:-" followed by names on separate lines
15. OMIT sentences like "This entry was made based on..." or "This inheritance entry was made...". Keep descriptions concise.
16. LOAN entries: Do NOT include agreement date. Only describe the loan, borrower, lender, amount, and land details.
17. OLD SURVEY NUMBERS: If there is a PROMULGATION entry (re-survey), use "old Survey No." for all entries BEFORE the promulgation entry. Use "Survey No." for entries AFTER promulgation. If there is NO promulgation entry, use "Survey No." (without "old").
18. Always use 4-digit years (DD/MM/YYYY). Never use 2-digit years (DD/MM/YY).
19. Include Khata number in parentheses after each survey number when visible in the source document, e.g., "5/2(28), 193p1(28)". If no Khata number is visible, omit parentheses.
20. Translate "Prant Officer" / "પ્રાંત અધિકારી" as "Province Officer". Use "Province Officer" and "Province court" consistently.
"""
```

Key changes: Rule 5 softened (was "SHORT and DIRECT - one sentence"), rule 8 dates now DD/MM/YYYY, rule 12 area format updated, rule 14 lists use separate lines not bullets, rule 18 (4-digit years) added, rule 19 (Khata numbers) added, rule 20 (Province Officer) added, borewell rule 18 removed.

- [ ] **Step 2: Update DESCRIPTION_EXAMPLES (lines 108-127)**

Replace the entire `DESCRIPTION_EXAMPLES` constant:

```python
DESCRIPTION_EXAMPLES = """
Example descriptions (follow these exact patterns):

LOAN (correct): "That Mer Deva Depa took a loan of Rs. 20,000/- on land bearing old Survey No. 373/p1, 359, 390, 389(215) from Bank of India, Modhvada Branch."
LOAN (wrong - includes agreement date): "That Mer Deva Depa took a loan of Rs. 20,000/- from Bank of India, Modhvada Branch based on an agreement dated 14/05/2005." - DO NOT include agreement date!
LOAN (wrong - too verbose): "That account holder Shri Mer Deva Depa of Keshav village mortgaged his total land of 6-21-20 Hectare of Keshav village, Khata No. 215, bearing Survey No. 390, with Bank of India, Modhwada branch, to obtain a loan of Rs. 20,000/-. This encumbrance entry was recorded based on the agreement dated 14/05/2005."

IMPORTANT for LOAN entries:
- DO NOT include "agreement dated" or "based on an agreement"
- DO NOT include total land area or hectare measurements in loan descriptions
- Just state: borrower name, loan amount, survey numbers, bank name and branch

Other patterns:
- DEATH: "That upon the demise of [Name], his share in land bearing old Survey No. X(Khata), Y(Khata) came to be mutated in the names of his legal heirs which are as follows:
[Heir1Name]
[Heir2Name]"
- SALE: "That [Seller] sold Survey No. X to [Buyer] for Rs. X/- vide document no. Y dated DD/MM/YYYY."
- PARTITION: "That Family members distributed their land among themselves as follows:-"
- RELEASE: "That upon receiving an application from [Name] for removing the charge of [Bank], [Branch]. The said exemption of burden has been recorded. Entry No. X."
- ORDER (government allotment): "That Government survey was conducted and land bearing Survey No. X was allotted to [Name]."
- ORDER (circular): "That as per Taluka Circular No. X dated Y, Survey No. Z allotted to [Name]."
- NOT RELATED: "This Entry is not related to Present Survey Number."
- PROMULGATION: Extract the FULL procedural text. Include: issuing authority, court name, all order numbers with dates, public notice and objection period, Mamlatdar preparation, Province Office verification, finalization, page/survey range. Do NOT summarize.
"""
```

Key changes: DEATH example uses "upon the demise" with "his share" and heirs on separate lines. RELEASE uses formal phrasing. PARTITION adds family distribution. ORDER adds government allotment. NOT RELATED capitalized. PROMULGATION instructs full extraction.

- [ ] **Step 3: Update CERTIFICATION_PATTERNS (lines 84-105)**

Change date format references from DD/MM/YY to DD/MM/YYYY:

In `CERTIFICATION_PATTERNS`, replace:
- `"The Entry is cancelled by [Name] on DD/MM/YY."` → `"The Entry is cancelled by [Name] on DD/MM/YYYY."`
- `"The Entry is not accepted by [Name] on DD/MM/YY."` → `"The Entry is not accepted by [Name] on DD/MM/YYYY."`
- `"The Entry is certified by [Name] on DD/MM/YY."` → `"The Entry is certified by [Name] on DD/MM/YYYY."`
- Remove line 97: `"IMPORTANT: If the document shows a 2-digit year (e.g., 30/09/05), still extract it as DD/MM/YY; it will be normalized later."`
- Replace with: `"Always output certification dates in 4-digit year format (DD/MM/YYYY)."`

- [ ] **Step 4: Reinforce certification extraction (spec 1e)**

In `CERTIFICATION_PATTERNS`, after the existing "IMPORTANT: All three certification fields MUST be extracted" block, add:

```
CERTIFICATION EXTRACTION IS REQUIRED:
- certification_official and certification_date are REQUIRED fields for all certified/rejected entries when visible in the source document.
- Always extract the certifying officer designation and place (e.g., "C.O. Jadiya", "Mamlatdar Dhanera") into certification_official.
- Always extract the certification date in DD/MM/YYYY format into certification_date.
- Do NOT output just "The Entry is certified." if officer name or date is visible in the document.
```

- [ ] **Step 5: Add feature flag and update prompt builder (lines 134-230)**

Add after line 36 (after `MODEL_NAME`):

```python
# Feature flag: classify entries about other survey numbers as NOT RELATED
CLASSIFY_NOT_RELATED_ENTRIES = True
```

In `build_unified_prompt()`, at line 200, change:
```
- date: Format as DD/MM/YY if available, else ""
```
to:
```
- date: Format as DD/MM/YYYY (4-digit year) if available, else ""
```

After line 216 (the certification examples block), add:

```python
    not_related_instruction = ""
    if CLASSIFY_NOT_RELATED_ENTRIES:
        not_related_instruction = """
NOT RELATED ENTRIES: If an entry clearly pertains to survey numbers different from the subject survey number being investigated, classify it as NOT RELATED with description: "This Entry is not related to Present Survey Number."
"""
```

Then in the prompt string, after `{CERTIFICATION_PATTERNS}` (line 220), add `{not_related_instruction}`.

- [ ] **Step 6: Remove has_borewell from JSON schema and prompt**

In the prompt JSON schema (line 167), remove `"has_borewell": false`.
In the extraction instructions (line 191), remove the `has_borewell` instruction.

- [ ] **Step 7: Run existing tests**

Run: `pytest -x`
Expected: All existing tests pass.

- [ ] **Step 8: Commit**

```bash
git add tsr_generator/extractors/unified_extractor.py
git commit -m "feat: update LLM prompt — 4-digit years, formal phrasing, Khata numbers, Province Officer, feature-flagged NOT RELATED"
```

---

### Task 3: Update RELEASE template and inheritance formatting in docx_generator

**Files:**
- Modify: `tsr_generator/document/docx_generator.py:459-510`

- [ ] **Step 1: Fix RELEASE template (lines 459-469)**

Replace lines 459-469:

```python
        if hasattr(entry, 'is_loan_release') and entry.is_loan_release:
            # For loan redemption entries — formal legal phrasing
            description = f"That upon receiving an application from {releasee_names} for removing the charge of {releasor_names}"

            if hasattr(entry, 'branch') and entry.branch:
                description += f", {entry.branch} Branch"

            description += ". The said exemption of burden has been recorded."

            if entry.reference_to_original:
                description += f" Entry No. {entry.reference_to_original}."
```

Changes: removed "said" before releasee_names, moved "The said exemption of burden" before "Entry No.", added period after Entry No.

- [ ] **Step 2: Fix inheritance formatting (lines 497-508)**

Replace lines 497-508:

```python
        # Format heirs as plain line-break-separated list (no numbering)
        if heirs:
            description += "\n"
            for i, heir in enumerate(heirs):
                description += heir.name
                if i < len(heirs) - 1:
                    description += "\n"
        else:
            description += " No heirs specified."
```

This removes the `f"{i}. {heir.name}"` numbered format and the death_date block.

- [ ] **Step 3: Run existing tests**

Run: `pytest -x`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tsr_generator/document/docx_generator.py
git commit -m "fix: RELEASE template word order, remove heir numbering and death date"
```

---

### Task 4: Remove borewell and first-column numbering from chain of title

**Files:**
- Modify: `tsr_generator/document/docx_generator.py:108-349`
- Modify: `tsr_generator/document/tsr_document.py:282-284,358-360`

- [ ] **Step 1: Remove has_borewell parameter and first-column numbering**

In `docx_generator.py`:

Line 108 — change signature:
```python
def add_chain_of_title_section(document, entries, entry_table):
```

Line 122 — remove inline "3." from header (the `add_section_heading` function applies appropriate styling; removing the inline prefix is sufficient since manual versions simply don't have visible text numbering):
```python
    add_section_heading(document, "Chain of Title", numbered=True)
```

Line 154 — replace `--` with en-dash:
```python
    header_text = "Brief history and flow of title with respect to Immovable Properties \u2013 For 30 Year Period - Based on perusal of the documents referred in S. No. 2 above."
```

Lines 200-201 — remove first column numbering (leave cell empty):
```python
            # First column: empty (manual versions leave this column empty)
```
Delete lines 201-204 (the `num_run = num_para.add_run(f"{row_index}.")` block).

Lines 325-346 — rewrite note row (remove borewell, remove first-column number):
```python
    # After the loop, add the note entry
    note_row_cells = table.add_row().cells
    # First column: empty (no numbering)

    note_para_1 = note_row_cells[1].paragraphs[0]
    note_run_1 = note_para_1.add_run("Note:- The title of the land is clear and marketable.")
    note_run_1.bold = True
    note_run_1.font.name = 'Times New Roman'
    note_run_1.font.size = Pt(12.5)
```
Remove the entire borewell block (lines 339-346).

Also need to build and return the `entry_to_row_map`. After line 184 add:
```python
    entry_to_row_map = {}
```

Inside the entry loop (after line 188 `for row_index, num in enumerate(...)`), add:
```python
            entry_to_row_map[num] = row_index
```

At end of function (before `document.add_paragraph()`), add:
```python
    return entry_to_row_map
```

For the early return when entries is empty (line 127), change to:
```python
        return {}
```

- [ ] **Step 2: Update tsr_document.py — remove has_borewell, update section headers**

In `tsr_document.py`:

Lines 282-284 — remove has_borewell extraction:
Delete these 3 lines entirely.

Line 360 — update call to remove has_borewell, capture return value:
```python
        entry_to_row_map = add_chain_of_title_section(doc, entries, entry_table)
```

Line 290 — fix section 2 header for final_sample_v1 (already doesn't have numbering), update the else branch to remove "2." prefix:
The current code at line 290 already handles `final_sample_v1` without numbering. For the else branch, change:
```python
"2.  Details/Description of document scrutinized"
```
to:
```python
"Details/Description of document scrutinized"
```

Line 164 — same for section 1, update else branch to remove "1." prefix.

- [ ] **Step 3: Write test for entry_to_row_map return value**

```python
# tests/test_entry_row_map.py
from docx import Document
from tsr_generator.document.docx_generator import add_chain_of_title_section
from tsr_generator.extractors.entry_schema import GenericEntry

def test_entry_to_row_map_returns_correct_mapping():
    doc = Document()
    entries = [
        GenericEntry(entry_number="100", date="01/01/2000", type="SALE",
                     formatted_description="Test sale entry", entry_status="certified"),
        GenericEntry(entry_number="200", date="02/02/2001", type="LOAN",
                     formatted_description="Test loan entry", entry_status="certified"),
    ]
    entry_table = ["100", "200"]
    result = add_chain_of_title_section(doc, entries, entry_table)
    assert isinstance(result, dict)
    assert result["100"] == 1
    assert result["200"] == 2

def test_entry_to_row_map_empty_entries():
    doc = Document()
    result = add_chain_of_title_section(doc, [], [])
    assert result == {}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_entry_row_map.py tests/test_date_normalization.py -v && pytest -x`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add tsr_generator/document/docx_generator.py tsr_generator/document/tsr_document.py tests/test_entry_row_map.py
git commit -m "fix: remove borewell note, first-column numbering, inline section number prefixes, use en-dash, return entry_to_row_map"
```

---

### Task 5: Update findings table — cross-references, SN periods, Note row

**Files:**
- Modify: `tsr_generator/extractors/findings.py:152-327`
- Test: `tests/test_findings_crossref.py` (create)

- [ ] **Step 1: Write failing test for cross-referencing**

```python
# tests/test_findings_crossref.py
from tsr_generator.extractors.findings import generate_findings_table

def test_cross_reference_with_map():
    entries = [
        {"entry_number": "4477", "type": "LOAN", "entry_status": "certified"},
        {"entry_number": "4736", "type": "RELEASE", "entry_status": "certified",
         "description": "Entry No. 4477"},
        {"entry_number": "5647", "type": "LOAN", "entry_status": "certified"},
    ]
    land_details = {"taluka_name": "Dhanera", "tsr_profile": "final_sample_v1"}
    entry_to_row_map = {"4477": 20, "4736": 21, "5647": 33}

    findings = generate_findings_table("", entries, land_details, entry_to_row_map)

    # Row 5 (index 8) should cross-reference point 33
    row5 = findings[8]
    assert "point 33 in table no. 3 above" in row5['observation']

    # Row 18 (index 21) should also cross-reference
    row18 = findings[21]
    assert "point 33 in table no. 3 above" in row18['observation']

def test_cross_reference_without_map_fallback():
    entries = [
        {"entry_number": "100", "type": "LOAN", "entry_status": "certified"},
    ]
    land_details = {"taluka_name": "Dhanera", "tsr_profile": "final_sample_v1"}

    findings = generate_findings_table("", entries, land_details)
    row5 = findings[8]
    # Without map, should fall back to generic text
    assert "clear and marketable" in row5['observation']

def test_no_encumbrances():
    entries = [
        {"entry_number": "100", "type": "SALE", "entry_status": "certified"},
    ]
    land_details = {"taluka_name": "Dhanera", "tsr_profile": "final_sample_v1"}

    findings = generate_findings_table("", entries, land_details, {})
    row5 = findings[8]
    assert row5['observation'] == "The title of the land is clear and marketable."

def test_sn_has_periods():
    entries = []
    land_details = {"taluka_name": "Dhanera"}
    findings = generate_findings_table("", entries, land_details)
    # Check that non-empty SN values have periods
    for f in findings:
        if f['sn']:
            assert f['sn'].endswith('.'), f"SN '{f['sn']}' missing period"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_findings_crossref.py -v`
Expected: FAIL

- [ ] **Step 3: Implement findings changes**

In `tsr_generator/extractors/findings.py`:

Update signature (line 152):
```python
def generate_findings_table(pdf_text: str, entries: Optional[List[Dict]] = None, land_details: Optional[Dict[str, str]] = None, entry_to_row_map: Optional[Dict[str, int]] = None) -> List[Dict[str, str]]:
```

Replace the title conclusion logic (lines 194-210):

```python
    # Generate conditional title conclusion with dynamic cross-references
    if has_encumbrances and entry_to_row_map:
        # Resolve active encumbrance entry numbers to their chain-of-title row numbers
        row_numbers = []
        for entry_num in active_entry_nums:
            if entry_num in entry_to_row_map:
                row_numbers.append(str(entry_to_row_map[entry_num]))

        if row_numbers:
            if len(row_numbers) == 1:
                point_ref = f"point {row_numbers[0]} in table no. 3 above"
            else:
                point_ref = f"point {' and '.join(row_numbers)} in table no. 3 above"
            title_conclusion = f"The title of the land is clear and marketable subject to {point_ref}."
            final_conclusion_row_18 = title_conclusion
        else:
            title_conclusion = "The title of the land is clear and marketable Subject to bank charge."
            final_conclusion_row_18 = title_conclusion
    elif has_encumbrances:
        # Fallback when no entry_to_row_map provided
        title_conclusion = "The title of the land is clear and marketable Subject to bank charge."
        final_conclusion_row_18 = title_conclusion
    else:
        title_conclusion = "The title of the land is clear and marketable."
        final_conclusion_row_18 = title_conclusion
```

Add periods to all SN values in the findings list. Change every `'sn': '1'` to `'sn': '1.'`, `'sn': '2'` to `'sn': '2.'`, etc. through all 18 numbered items (leave `'sn': ''` unchanged for sub-items).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_findings_crossref.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -x`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add tsr_generator/extractors/findings.py tests/test_findings_crossref.py
git commit -m "feat: dynamic cross-references in findings rows 5/18, add SN periods"
```

---

### Task 6: Update Note row with entry numbers and bank names

**Files:**
- Modify: `tsr_generator/document/docx_generator.py:325-349`

This depends on Task 4 (entry_to_row_map) and Task 5 (encumbrance detection).

- [ ] **Step 1: Update add_chain_of_title_section to accept entries for Note row**

The function already receives `entries`. We need to use the encumbrance detection to build the Note row text. Add this import at the top of `docx_generator.py`:

```python
from tsr_generator.extractors.findings import detect_active_encumbrances
```

- [ ] **Step 2: Replace the Note row text generation**

Replace the note row content block (after "add the note entry" comment):

```python
    # Detect active encumbrances for note row
    entry_dicts = []
    for entry in entries:
        entry_dict = {
            'entry_number': str(getattr(entry, 'entry_number', '')),
            'type': getattr(entry, 'type', ''),
            'entry_status': getattr(entry, 'entry_status', ''),
            'description': getattr(entry, 'formatted_description', ''),
        }
        if hasattr(entry.type, 'value'):
            entry_dict['type'] = entry.type.value
        entry_dicts.append(entry_dict)

    active_encumbrances, active_entry_nums = detect_active_encumbrances(entry_dicts)

    note_row_cells = table.add_row().cells
    # First column: empty

    note_para_1 = note_row_cells[1].paragraphs[0]

    if active_entry_nums:
        # Format entry numbers with bank names when available
        entry_refs = ", ".join(active_entry_nums)
        note_text = f"Note:- The title of the land is clear and marketable subject to bank charge. (Entry No. {entry_refs})"
    else:
        note_text = "Note:- The title of the land is clear and marketable."

    note_run_1 = note_para_1.add_run(note_text)
    note_run_1.bold = True
    note_run_1.font.name = 'Times New Roman'
    note_run_1.font.size = Pt(12.5)
```

- [ ] **Step 3: Run existing tests**

Run: `pytest -x`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tsr_generator/document/docx_generator.py
git commit -m "feat: Note row shows specific active charge entry numbers"
```

---

### Task 7: Property table — area format and name de-numbering

**Files:**
- Modify: `tsr_generator/document/tsr_document.py:218-264`

- [ ] **Step 1: Update area format (lines 218-229)**

Replace lines 218-229:

```python
        # Format area display as "X-XX-XX - i.e. (XXXXX Sq. Mts)"
        area = sanitize_text(land_details.get('total_area'))
        # Strip "Hectare" if the LLM included it
        area = re.sub(r'\s*Hectare\s*', ' ', area).strip()
        # Check if area already has the format we want
        if ' i.e.' not in area and not re.search(r'\(\d+ Sq\. Mts\)', area):
            # Try to extract numeric values if in format like "2-55-98"
            area_match = re.search(r'(\d+)-(\d+)-(\d+)', area)
            if area_match:
                hectares, acres, guntha = map(int, area_match.groups())
                sq_meters = int((hectares * 10000) + (acres * 100) + guntha)
                area = f"{area} - i.e. ({sq_meters} Sq. Mts)"
        row[2].text = area
```

Changes: strips "Hectare", uses `- i.e.` with dash separator and space before parenthesis.

- [ ] **Step 2: Remove owner name numbering (lines 250-256)**

Replace lines 250-256:

```python
        if ',' in owner:  # Multiple owners separated by commas
            owners = [name.strip() for name in owner.split(',')]

            owner_text = ""
            for name in owners:
                if name and name.strip():
                    owner_text += f"{name}\n"
        else:
```

Change: removed `f"{i}. {name}\n"` pattern, now just `f"{name}\n"`.

- [ ] **Step 3: Run existing tests**

Run: `pytest -x`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tsr_generator/document/tsr_document.py
git commit -m "fix: area format matches manual (remove Hectare, add dash), remove owner name numbering"
```

---

### Task 8: Thread entry_to_row_map through orchestration

**Files:**
- Modify: `tsr_generator/document/tsr_document.py:358-363`
- Modify: `tsr_generator/api/tsr_generator_optimized.py:132-144`

- [ ] **Step 1: Update tsr_document.py to pass map to findings**

In `tsr_document.py`, the `create_tsr_document` function currently calls `add_findings_table(doc, findings)` at line 363. The findings are pre-generated before document creation. The threading needs to happen at the orchestration level.

In `tsr_generator_optimized.py`, lines 132-144, the current flow is:
1. `findings = generate_findings_table(pdf_text, entries, land_details)` (line 134)
2. `create_tsr_document(entry_table, entries, land_details, findings, output_path)` (line 144)

The problem: `entry_to_row_map` is only available after `add_chain_of_title_section` runs inside `create_tsr_document`. So we need to restructure: generate findings INSIDE `create_tsr_document` after the chain of title section is built.

Update `create_tsr_document` signature in `tsr_document.py` to accept raw entry data:

At line 360 (after chain of title):
```python
        entry_to_row_map = add_chain_of_title_section(doc, entries, entry_table)

        # Re-generate findings with cross-references now that we have the row map
        if hasattr(self, '_pdf_text') or pdf_text:
            from tsr_generator.extractors.findings import generate_findings_table
            # Convert entries back to dicts for findings
            entry_dicts = []
            for entry in entries:
                entry_dict = {
                    'entry_number': str(getattr(entry, 'entry_number', '')),
                    'type': getattr(entry, 'type', '').value if hasattr(getattr(entry, 'type', ''), 'value') else str(getattr(entry, 'type', '')),
                    'entry_status': getattr(entry, 'entry_status', ''),
                    'description': getattr(entry, 'formatted_description', ''),
                }
                entry_dicts.append(entry_dict)
            findings = generate_findings_table("", entry_dicts, land_details, entry_to_row_map)
```

Actually, the simpler approach: pass `mutation_entries` (the raw dicts) into `create_tsr_document` so it can regenerate findings with the map.

Update `create_tsr_document` function signature to add `mutation_entries=None`:

```python
def create_tsr_document(entry_table, entries, land_details, findings, output_path, mutation_entries=None):
```

Then after `add_chain_of_title_section` returns `entry_to_row_map`, regenerate findings if we have the raw data:

```python
        entry_to_row_map = add_chain_of_title_section(doc, entries, entry_table)

        # Regenerate findings with cross-references if mutation data available
        if mutation_entries is not None and entry_to_row_map:
            findings = generate_findings_table("", mutation_entries, land_details, entry_to_row_map)
```

- [ ] **Step 2: Update optimized generator — skip first findings call, pass mutation_entries**

In `tsr_generator_optimized.py`, replace lines 132-134:

```python
        # Generate initial findings (will be regenerated with cross-references inside create_tsr_document)
        logger.debug("Generating initial findings")
        findings = generate_findings_table(pdf_text, unified_result.mutation_entries, land_details)
```

with:

```python
        # Generate placeholder findings — will be regenerated with cross-references
        # inside create_tsr_document after chain of title table is built
        findings = generate_findings_table("", unified_result.mutation_entries, land_details)
```

At line 144, pass `mutation_entries`:

```python
        output_file = create_tsr_document(entry_table, entries, land_details, findings, output_path, mutation_entries=unified_result.mutation_entries)
```

- [ ] **Step 3: Update section 4 header**

In `tsr_document.py`, find where the findings section header is set. Search for `"4.  Findings"` and remove the "4." prefix, matching the same approach as other headers.

- [ ] **Step 4: Run full test suite**

Run: `pytest -x`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add tsr_generator/document/tsr_document.py tsr_generator/api/tsr_generator_optimized.py
git commit -m "feat: thread entry_to_row_map through orchestration for dynamic cross-references"
```

---

### Task 9: Add 4-digit year post-processing in certification rendering

**Files:**
- Modify: `tsr_generator/document/docx_generator.py:260-310`

- [ ] **Step 1: Import `_normalize_date_str` for date expansion**

At the top of `docx_generator.py`, add:

```python
from tsr_generator.extractors.unified_extractor import _normalize_date_str
```

This reuses the same function updated in Task 1 (which now expands 2-digit to 4-digit years), avoiding code duplication.

- [ ] **Step 2: Apply to certification date rendering**

At line 264, after `cert_date = getattr(entry, 'certification_date', '') or ""`, add:
```python
                        cert_date = _normalize_date_str(cert_date)
```

At line 284, after the regex date match, apply expansion:
```python
                        if date_match:
                            expanded_date = _normalize_date_str(date_match.group(1))
                            certification_text = f"The Entry is {status_word} by {official_name} on {expanded_date}."
```

- [ ] **Step 3: Run existing tests**

Run: `pytest -x`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tsr_generator/document/docx_generator.py
git commit -m "fix: post-process certification dates to 4-digit years as safety net"
```

---

### Task 10: Run integration test against sample TSR

**Files:**
- No new files — manual verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: All tests pass including new tests from Tasks 1 and 5.

- [ ] **Step 2: Process a sample PDF (if available)**

If a source PDF for S.No. 980 is available in the project, run:
```bash
python -m tsr_generator <path_to_980_pdf> --output /tmp/test_980.docx
```

Then manually compare `/tmp/test_980.docx` against `Final TSR Sample/S.No. 980 - Final.docx` for:
- RELEASE entries use "upon receiving an application... exemption of burden"
- Dates are 4-digit
- Section headers have no inline numbers
- Observations rows 5, 18 cross-reference specific points
- Note row lists entry numbers
- No borewell line
- Area format: no "Hectare", dash separator
- First column empty
- Heir names not numbered
- Property table owner names not numbered

- [ ] **Step 3: Final commit**

```bash
git commit --allow-empty -m "chore: verified integration against sample TSR S.No. 980"
```
