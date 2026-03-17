# TSR Language & Content Quality Improvement — Design Spec

*2026-03-17 | Hybrid approach: prompt + template + findings logic changes*

## Problem

Comparison of 29 AI-generated vs manually-generated TSR pairs revealed systematic language, content, and formatting differences that reduce the legal quality of AI output. This spec addresses the 6 confirmed changes (3 dropped after sample validation).

## Scope

### In Scope

1. LLM prompt improvements for richer extraction
2. Deterministic template for RELEASE entry formal phrasing
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

#### 1b. Survey Numbers with Khata
Add to `FORMATTING_RULES`:
> "Include Khata number in parentheses after each survey number when visible in the source document, e.g., `5/2(28), 193p1(28)`. If no Khata number is visible, omit parentheses."

#### 1c. Succession/Inheritance Entry Descriptions
Update entry type rules for INHERITANCE/DEATH entries:
- Use "upon **the** demise of [name]" (with "the")
- Use phrasing: "his/her share in [survey numbers with Khata] came to be mutated in the names of his/her legal heirs which are as follows:" followed by names on separate lines
- Name all transferees (legal heirs) explicitly
- Do NOT include death date in the description text

#### 1d. Promulgation Entry Descriptions
Add specific instruction for PROMULGATION entries:
> "For PROMULGATION entries, extract the FULL procedural text. Include: issuing authority and court name, all order numbers with dates, public notice and objection period details, Mamlatdar preparation, Province Office verification, finalization statement, and page/survey range details. Do NOT summarize or condense. Preserve the full narrative chain."

#### 1e. Certification Structured Fields
Reinforce that `certification_official` and `certification_date` must always be extracted when visible:
> "Always extract the certifying officer designation and place (e.g., 'C.O. Jadiya', 'Mamlatdar Dhanera') into certification_official, and the certification date (DD/MM/YYYY) into certification_date. These are required fields for all certified/rejected entries."

---

### Component 2: RELEASE Entry Template

**File:** `tsr_generator/document/docx_generator.py`

Modify `construct_description_from_fields()` for RELEASE/LOAN_CLOSE entry type.

**Current template output:**
> "That charge of [bank] removed on application of [person]. Entry No. [ref]. The exemption has been recorded."

**New template output:**
> "That upon receiving an application from [releasee] for removing the charge of [releasor], [branch]. The said exemption of burden has been recorded. Entry No. [ref]."

Built deterministically from existing structured fields: `releasee`, `releasor`, `branch`, `ref_entry`. No new extraction needed.

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
Change serial number column from `1, 2, 3` to `1., 2., 3.` (with trailing period).

#### 3d. 4-Digit Year Post-Processing
When formatting certification dates in chain-of-title entry rows, post-process any 2-digit years to 4-digit. Heuristic: years 00-30 map to 2000-2030, years 31-99 map to 1931-1999.

#### 3e. Heir Name Formatting
In inheritance entry descriptions, format heir names one per line (line break separated) rather than comma-separated on a single line.

#### 3f. Property Table Name List
Remove numbering from title holder names in the property table. Currently: `1. Name\n2. Name`. Change to: `Name\nName`.

---

### Component 4: Findings Cross-Referencing

**Files:** `tsr_generator/extractors/findings.py`, `tsr_generator/document/docx_generator.py`, `tsr_generator/document/tsr_document.py` (or `tsr_generator/api/tsr_generator_optimized.py`)

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

**Current (when encumbrances detected):**
> "The title of the land is clear and marketable Subject to bank charge."

**New:**
> "The title of the land is clear and marketable subject to point {N} in table no. 3 above."

Where `{N}` is the row number of the active charge entry in the chain of title table. If multiple active charges, list all: "subject to point {N1} and {N2} in table no. 3 above."

#### Note Row (End of Chain of Title)

**Current:**
> "Note:- The title of the land is clear and marketable." + optional borewell line

**New (when encumbrances detected):**
> "Note:- The title of the land is clear and marketable subject to bank charge. (Entry No. {numbers})"

Where `{numbers}` lists the specific active charge entry numbers. When bank names are available from the entry data, include them: `(528 JVB & 6342 ICICI)`.

When no encumbrances: keep current "clear and marketable" text. Borewell note remains as a separate line when applicable.

#### Interface Change

`add_chain_of_title_section()` signature changes:
- **Current:** returns `None`
- **New:** returns `dict[str, int]` mapping entry numbers to row indices

`generate_findings_table()` signature changes:
- **Current:** `generate_findings_table(entries, taluka_name, has_borewell)`
- **New:** `generate_findings_table(entries, taluka_name, has_borewell, entry_to_row_map)`

The orchestrator (`create_tsr_document` or equivalent) threads the mapping between the two calls.

---

## Files Modified

| File | Changes |
|------|---------|
| `tsr_generator/extractors/unified_extractor.py` | Prompt constants: date format, Khata numbers, succession phrasing, promulgation detail, certification fields |
| `tsr_generator/document/docx_generator.py` | RELEASE template, section headers, en-dashes, heir name formatting, entry-to-row mapping return, certification date post-processing |
| `tsr_generator/document/tsr_document.py` | Section header style, property table name de-numbering, thread entry-to-row mapping |
| `tsr_generator/extractors/findings.py` | Cross-reference rows 5/18 with row numbers, Note row with entry numbers, accept entry_to_row_map param |
| `tsr_generator/api/tsr_generator_optimized.py` | Thread entry_to_row_map through orchestration (if needed) |

## Testing

- Run existing tests to ensure no regressions
- Process S.No. 980 PDF through the pipeline and compare output against manual S.No. 980 sample
- Verify: RELEASE entries use formal phrasing, section headers have no inline numbers, observations cross-reference correct row numbers, Note row lists entry numbers, dates are 4-digit, heir names are line-separated
