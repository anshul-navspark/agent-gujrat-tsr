# TSR Language & Content Quality Improvement — Design Spec

*2026-03-17 | Hybrid approach: prompt + template + findings logic changes*

## Problem

Comparison of 29 AI-generated vs manually-generated TSR pairs revealed systematic language, content, and formatting differences that reduce the legal quality of AI output. This spec addresses the 6 confirmed changes (3 dropped after sample validation).

## Scope

### In Scope

1. LLM prompt improvements for richer extraction
2. RELEASE entry template refinement
3. Document formatting fixes (headers, dashes, dates, observation numbering)
4. Findings table cross-referencing of chain-of-title row numbers
5. Note row with specific entry numbers for active charges
6. Property table name list de-numbering

### Out of Scope (Dropped)

- Change 1: "as per above subject reference" — present in manual samples, keep
- Change 2: "The Borrower has acquired..." paragraph — present in manual samples, keep
- Change 8: Opinion section 4 paragraphs — miscount, manual has no separate opinion paragraphs
- Bank name dotted abbreviation (e.g., "I.C.I.C.I.") — too fragile, source PDFs inconsistent
- Survey number format changes — manual versions themselves inconsistent
- Sub-registrar jurisdiction "Dessa and Dhanera" — requires external data not in PDF

---

## Design

### Component 1: LLM Prompt Changes

**File:** `tsr_generator/extractors/unified_extractor.py`

Update the extraction prompt constants to add/modify these rules:

#### 1a. Date Format
Add to `FORMATTING_RULES`:
> "Always use 4-digit years (DD/MM/YYYY). Never use 2-digit years (DD/MM/YY)."

**Also:** Modify `_normalize_date_str()` (lines 337-359) which currently converts 4-digit years TO 2-digit. Reverse this: convert 2-digit years to 4-digit instead. Heuristic: years 00-30 map to 2000-2030, years 31-99 map to 1931-1999. This prevents a roundtrip where the LLM outputs 4-digit years but `_normalize_date_str()` strips them back to 2-digit.

#### 1b. Survey Numbers with Khata
Add to `FORMATTING_RULES`:
> "Include Khata number in parentheses after each survey number when visible in the source document, e.g., `5/2(28), 193p1(28)`. If no Khata number is visible, omit parentheses."

#### 1c. Succession/Inheritance Entry Descriptions
Update entry type rules for INHERITANCE/DEATH entries. The current `construct_description_from_fields()` in `docx_generator.py` (line 485) already uses "upon the demise of" and produces numbered heir lists. The prompt changes needed are:
- Instruct the LLM to use phrasing: "his/her share in [survey numbers with Khata] came to be mutated in the names of his/her legal heirs which are as follows:" (the template already produces similar text at line 495)
- Do NOT include death date in the `formatted_description` (template change: remove death date block at lines 507-508 of `docx_generator.py`)
- Names on separate lines, not comma-separated

**Template change (docx_generator.py):** Change heir formatting from numbered (`1. Name`) to plain line-break-separated (`Name`). Remove lines 500-501's `f"{i}. {heir.name}"` pattern, replace with just `f"{heir.name}"`. Remove death date block at lines 507-508.

#### 1d. Promulgation Entry Descriptions
Add specific instruction for PROMULGATION entries:
> "For PROMULGATION entries, extract the FULL procedural text. Include: issuing authority and court name, all order numbers with dates, public notice and objection period details, Mamlatdar preparation, Province Office verification, finalization statement, and page/survey range details. Do NOT summarize or condense. Preserve the full narrative chain."

#### 1e. Certification Structured Fields
Reinforce that `certification_official` and `certification_date` must always be extracted when visible:
> "Always extract the certifying officer designation and place (e.g., 'C.O. Jadiya', 'Mamlatdar Dhanera') into certification_official, and the certification date (DD/MM/YYYY) into certification_date. These are required fields for all certified/rejected entries."

---

### Component 2: RELEASE Entry Template Refinement

**File:** `tsr_generator/document/docx_generator.py`

The current RELEASE template (lines 459-469) already uses the formal phrasing:
> "That upon receiving an application from said {releasee_names} for removing the charge of {releasor_names}, {branch} Branch. Entry No. {ref}. The said exemption of burden has been recorded."

Minor refinements needed:
1. Remove the word "said" before releasee names (manual versions don't include it)
2. Swap sentence order: "The said exemption of burden has been recorded" should come BEFORE "Entry No. {ref}" to match manual phrasing:
> "That upon receiving an application from {releasee_names} for removing the charge of {releasor_names}, {branch} Branch. The said exemption of burden has been recorded. Entry No. {ref}."

---

### Component 3: Document Formatting

**Files:** `tsr_generator/document/tsr_document.py`, `tsr_generator/document/docx_generator.py`

#### 3a. Section Headers
Remove inline "3." and "4." prefixes from Chain of Title and Findings headers. Use Word List Paragraph style for numbering (matching manual versions).

**Current:** `"3.  Chain of Title"`, `"4.  Findings & opinion based our title investigation:-"`
**New:** `"Chain of Title"`, `"Findings & opinion based our title investigation:-"` with List Paragraph style applied.

#### 3b. En-Dashes
Replace all `--` (double hyphen) with `–` (en-dash U+2013) in:
- Chain of title header: "Immovable Properties – For 30 Year Period"
- Any other hardcoded double-hyphens in templates

#### 3c. Observation Row SN Format
Change serial number column from `1, 2, 3` to `1., 2., 3.` (with trailing period). Apply this in `tsr_generator/extractors/findings.py` where SN values are generated (e.g., `'sn': '1'` becomes `'sn': '1.'`).

#### 3d. 4-Digit Year Post-Processing
When formatting certification dates in chain-of-title entry rows (`docx_generator.py`), post-process any remaining 2-digit years to 4-digit as a safety net. Use the same heuristic as Component 1a: years 00-30 → 2000-2030, years 31-99 → 1931-1999. This catches cases where the LLM ignores the prompt instruction.

#### 3e. Heir Name Formatting
Already addressed in Component 1c — change numbered list to plain line-break-separated in `construct_description_from_fields()`.

#### 3f. Property Table Name List
Remove numbering from title holder names in the property table (`tsr_document.py`). Currently: `1. Name\n2. Name`. Change to: `Name\nName`.

---

### Component 4: Findings Cross-Referencing

**Files:** `tsr_generator/extractors/findings.py`, `tsr_generator/document/docx_generator.py`, `tsr_generator/document/tsr_document.py`, `tsr_generator/api/tsr_generator_optimized.py`

This is the most architecturally significant change. It requires threading data between the chain-of-title table builder and the findings table builder.

#### Data Flow

```
1. Build chain of title table (docx_generator.add_chain_of_title_section)
   → Produces: entry_to_row_map = {entry_number: row_index}
   → Returns this mapping

2. Pass mapping to generate_findings_table()
   → Uses mapping to resolve cross-references

3. Findings rows 5 and 18 use specific row numbers
```

#### Observations Rows 5 and 18

**Current (when encumbrances detected, `final_sample_v1` profile):**
- Row 5: `"The title of the land is clear and marketable Subject to bank charge."`
- Row 18: `"The title of the land is clear and marketable subject to point 17 of Table No. 3 above."` (hardcoded "17")

**New (dynamic for all profiles including `final_sample_v1`):**
> "The title of the land is clear and marketable subject to point {N} in table no. 3 above."

Where `{N}` is the row number of the active charge entry in the chain of title table, resolved dynamically from `entry_to_row_map`. If multiple active charges, list all: "subject to point {N1} and {N2} in table no. 3 above."

The `final_sample_v1` profile branch (lines 201-204 of `findings.py`) should be updated to use dynamic cross-references instead of the hardcoded "point 17". Both profile paths should produce the same cross-referenced output.

#### Note Row (End of Chain of Title)

**Current:**
> "Note:- The title of the land is clear and marketable." + optional borewell line

**New (when encumbrances detected):**
> "Note:- The title of the land is clear and marketable subject to bank charge. (Entry No. {numbers})"

Where `{numbers}` lists the specific active charge entry numbers. When bank names are available from the entry data, include them: `(528 JVB & 6342 ICICI)`.

When no encumbrances: keep current "clear and marketable" text. Borewell note remains as a separate line when applicable.

#### Interface Changes

`add_chain_of_title_section()` signature changes:
- **Current:** returns `None`
- **New:** returns `dict[str, int]` mapping entry numbers to row indices

`generate_findings_table()` signature changes:
- **Current:** `generate_findings_table(pdf_text: str, entries=None, land_details=None)`
- **New:** `generate_findings_table(pdf_text: str, entries=None, land_details=None, entry_to_row_map=None)`

The new `entry_to_row_map` parameter defaults to `None` for backward compatibility with callers in `services/ai_batch_service.py` (line 174) and `tsr_generator/api/tsr_generator.py` (line 72). When `None`, falls back to current generic phrasing.

The orchestrator (`create_tsr_document` or the optimized generator) threads the mapping between the two calls.

---

## Files Modified

| File | Changes |
|------|---------|
| `tsr_generator/extractors/unified_extractor.py` | Prompt constants: date format, Khata numbers, succession phrasing, promulgation detail, certification fields. Modify `_normalize_date_str()` to preserve/expand to 4-digit years. |
| `tsr_generator/document/docx_generator.py` | RELEASE template word order, remove "said", section headers, en-dashes, heir name formatting (remove numbering, remove death date), entry-to-row mapping return, certification date post-processing |
| `tsr_generator/document/tsr_document.py` | Section header style, property table name de-numbering, thread entry-to-row mapping |
| `tsr_generator/extractors/findings.py` | Cross-reference rows 5/18 with dynamic row numbers (replace hardcoded "point 17"), Note row with entry numbers, accept `entry_to_row_map` param, add period to SN values |
| `tsr_generator/api/tsr_generator_optimized.py` | Thread entry_to_row_map through orchestration |
| `tsr_generator/api/tsr_generator.py` | Backward-compatible: no changes needed (new param defaults to None) |
| `services/ai_batch_service.py` | Backward-compatible: no changes needed (new param defaults to None) |

## Testing

- Run existing test suite (`pytest`) to ensure no regressions
- **Unit tests for date normalization:** Verify `_normalize_date_str()` correctly expands 2-digit years (00→2000, 30→2030, 31→1931, 99→1999) and preserves 4-digit years
- **Unit test for entry-to-row mapping:** Verify `add_chain_of_title_section()` returns correct mapping of entry numbers to row indices
- **Unit test for findings cross-referencing:** Verify rows 5 and 18 produce "subject to point N in table no. 3 above" with correct N when `entry_to_row_map` is provided, and fall back to generic text when `None`
- **Integration test:** Process S.No. 980 PDF through the pipeline and compare output against manual S.No. 980 sample
- **Regression test:** Process 2-3 additional PDFs (e.g., S.No. 979, 1099) to verify prompt changes don't degrade extraction quality
- Verify: RELEASE entries use formal phrasing, section headers have no inline numbers, observations cross-reference correct row numbers, Note row lists entry numbers, dates are 4-digit, heir names are line-separated, property table names are unnumbered
