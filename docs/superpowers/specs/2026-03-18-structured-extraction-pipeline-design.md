# Structured Extraction Pipeline Design

> **For agentic workers:** This spec describes the redesign of the TSR extraction pipeline from LLM-generated prose to structured field extraction with deterministic template rendering.

**Goal:** Make the extraction pipeline more deterministic by having the LLM extract structured fields per entry type, then assembling descriptions from templates in Python code.

**Architecture:** Two-pass LLM extraction (Pass 1: classification + land details, Pass 2: type-aware structured field extraction) followed by deterministic template rendering.

---

## 1. Problem Statement

The current pipeline sends a single prompt to Gemini that asks it to generate full English narrative descriptions for each mutation entry. This leads to:

- **Non-deterministic output** — same entry can produce different phrasing across runs
- **Missed fields** — LLM sometimes omits certification details, survey numbers, or bank names
- **Hard to debug** — when output is wrong, unclear if the issue is extraction or formatting
- **Wasted tokens** — LLM generates prose when it should just extract data

## 2. Two-Pass Extraction Architecture

### Pass 1: Classification & Land Details

**Purpose:** Lightweight call to classify every entry and extract land-level metadata.

**Input:** Full PDF text

**Output schema:**
```json
{
  "land_details": {
    "village_name": "",
    "taluka_name": "",
    "district_name": "",
    "survey_numbers": ["105", "141"],
    "old_survey_numbers": ["159"],
    "survey_number_mapping": {"159": ["105", "141"]},
    "total_area": "",
    "nature_of_land": "",
    "owners": ["name1", "name2"]
  },
  "entries": [
    {
      "entry_number": "3521",
      "date": "04/09/2013",
      "type": "LOAN",
      "certification_status": "certified",
      "certification_official": "C.O. Sami",
      "certification_date": "10/10/2013"
    }
  ]
}
```

**What this call extracts:**
- Land details including old-to-new survey number mapping (from promulgation entries)
- Every entry's number, date, type classification, and certification details
- Does NOT extract descriptions or type-specific fields

### Pass 2: Structured Field Extraction

**Purpose:** Extract type-specific structured fields using a dynamically-built prompt that includes only the schemas and few-shot examples for types found in Pass 1.

**Input:** Full PDF text + entry classifications from Pass 1

**Dynamic prompt construction:**
1. Collect unique types from Pass 1 results
2. For each type found, include its field schema and 2-3 few-shot examples from the example registry
3. List each entry number with its type, telling the LLM exactly what to extract
4. The LLM never decides the type — it was already decided in Pass 1

**Output:** Array of entry objects with type-specific fields (see Section 3 for per-type schemas).

**Token optimization:** Only type schemas present in the document are included. A PDF with no LOAN entries never sees the LOAN schema or examples.

## 3. Type-Specific Schemas

### 3.1 Ownership Transfer Types

#### SALE
```
Fields:
  sellers: [string]          — list of seller names
  buyers: [string]           — list of buyer names
  survey_numbers: [string]   — survey numbers involved
  area: string               — land measurement
  consideration_amount: string — sale price
  document_number: string    — registration document number
  document_date: string      — document date

Template:
  "That {sellers} sold land bearing Survey No. {survey_nos} measuring {area}
   to {buyers} through document no. {document_number} dated {document_date}
   in consideration of Rs. {consideration_amount}/-."
```

#### INHERITANCE
```
Fields:
  deceased: string           — name of deceased person
  heirs: [string]            — list of legal heir names
  survey_numbers: [string]
  area: string

Template:
  "That upon the demise of {deceased}, the land bearing Survey No. {survey_nos}
   measuring {area} came to be mutated in the names of legal heirs: {heirs}."
```

#### PARTITION
```
Fields:
  original_owner: string
  recipients: [string]
  survey_numbers: [string]
  area: string
  allocations: [{name: string, survey_number: string, area: string}]

Template:
  "That {original_owner} distributed the land as follows: {allocation_table}.
   The partition was recorded based on application and consent as per respective
   rights and physical possession."
```

#### RELINQUISHMENT
```
Fields:
  relinquisher: string
  beneficiaries: [string]
  survey_numbers: [string]
  area: string
  relationship: string

Template:
  "That {relinquisher} relinquished their share in land bearing Survey No.
   {survey_nos} measuring {area} in favour of {beneficiaries}."
```

#### EXCHANGE
```
Fields:
  party_a: [string]
  party_b: [string]
  survey_a: [string]         — survey numbers party_a gives
  survey_b: [string]         — survey numbers party_b gives
  area_a: string
  area_b: string

Template:
  "That {party_a} and {party_b} exchanged their lands. {party_a} transferred
   Survey No. {survey_a} measuring {area_a} and received Survey No. {survey_b}
   measuring {area_b}."
```

#### LIFETIME_DISTRIBUTION
```
Fields:
  distributor: string
  recipients: [string]
  survey_numbers: [string]
  area: string
  allocations: [{name: string, survey_number: string, area: string}]

Template:
  "That {distributor} distributed the land during their lifetime as follows:
   {allocation_table}."
```

#### GIFT
```
Fields:
  donor: string
  recipients: [string]
  survey_numbers: [string]
  area: string
  document_number: string
  document_date: string

Template:
  "That {donor} gifted land bearing Survey No. {survey_nos} measuring {area}
   to {recipients} through document no. {document_number} dated {document_date}."
```

### 3.2 Encumbrance Types

#### LOAN
```
Fields:
  borrowers: [string]
  lender: string             — bank/institution name
  survey_numbers: [string]
  amount: string

Template:
  "That {borrowers} created a charge on land bearing Survey No. {survey_nos}
   by taking loan from {lender} for a sum of Rs. {amount}/-. Therefore a charge
   in favour of {lender} was registered in the revenue records."
```

#### RELEASE
```
Fields:
  applicants: [string]
  lender: string
  survey_numbers: [string]
  reference_entry_number: string

Template:
  "That upon receiving an application from {applicants} for exemption of burden
   of {lender} (Entry No. {reference_entry_number}), the said exemption of
   burden has been recorded."
```

#### SEIZURE
```
Fields:
  bank: string
  survey_numbers: [string]
  borrowers: [string]
  reference_entry_number: string

Template:
  "That {bank} seized the land bearing Survey No. {survey_nos} of {borrowers}
   under the charge created in Entry No. {reference_entry_number}."
```

### 3.3 Administrative Types

#### ORDER
```
Fields:
  authority: string
  order_number: string
  order_date: string
  survey_numbers: [string]
  affected_parties: [string]
  order_summary: string      — brief factual summary of what was ordered

Template:
  "That {authority} vide Order No. {order_number} dated {order_date} ordered
   {order_summary}."
```

#### ALLOTMENT
```
Fields:
  grantee: [string]
  survey_numbers: [string]
  area: string
  authority: string
  legal_basis: string        — e.g., "Section 43 (Gannotdhara) of the Bombay Tenancy Act"

Template:
  "That {grantee} was granted land bearing Survey No. {survey_nos} measuring
   {area} by {authority} under {legal_basis}."
```

#### TENURE_CHANGE
```
Fields:
  authority: string
  order_number: string
  order_date: string
  survey_numbers: [string]
  from_tenure: string        — e.g., "new tenure"
  to_tenure: string          — e.g., "old tenure"

Template:
  "That {authority} vide Order No. {order_number} dated {order_date} changed
   the condition of the land from {from_tenure} to {to_tenure}. The aforesaid
   land is free from the restrictions of {from_tenure}."
```

#### LAND_ACQUISITION
```
Fields:
  authority: string
  award_number: string
  award_date: string
  survey_numbers: [string]
  areas: [string]
  purpose: string

Template:
  "That {authority} vide Award No. {award_number} dated {award_date} acquired
   land bearing Survey No. {survey_nos} for {purpose}."
```

#### LEASE
```
Fields:
  lessor: [string]
  lessee: string
  survey_numbers: [string]
  area: string
  period: string
  purpose: string

Template:
  "That {lessor} leased land bearing Survey No. {survey_nos} measuring {area}
   to {lessee} for a period of {period} for {purpose}."
```

#### PROMULGATION
```
Fields:
  authority: string
  survey_number_mapping: {old: new}
  effective_date: string

Template:
  "That upon re-survey by {authority}, new survey numbers were assigned. Old
   Survey No. {old_surveys} became new Survey No. {new_surveys}."
```

#### CORRECTION
```
Fields:
  correction_type: string    — e.g., "name", "area", "survey number"
  original_value: string
  corrected_value: string
  reference_entry_number: string

Template:
  "That {correction_type} was corrected from '{original_value}' to
   '{corrected_value}' in Entry No. {reference_entry_number}."
```

### 3.4 Fixed-Text Types

#### NOT_RELATED
```
Fields: (none — only entry_number and date from Pass 1)

Template:
  "This entry is not related to the present survey number(s)."
```

#### UNAVAILABLE
```
Fields: (none — only entry_number and date from Pass 1)

Template:
  "The data for this entry is not available."
```

## 4. Type System Migration

### Canonical Types (19)

The new pipeline uses exactly these 19 type strings. Pass 1 outputs one of these for each entry:

`SALE`, `INHERITANCE`, `PARTITION`, `RELINQUISHMENT`, `EXCHANGE`, `LIFETIME_DISTRIBUTION`, `GIFT`, `LOAN`, `RELEASE`, `SEIZURE`, `ORDER`, `ALLOTMENT`, `TENURE_CHANGE`, `LAND_ACQUISITION`, `LEASE`, `PROMULGATION`, `CORRECTION`, `NOT_RELATED`, `UNAVAILABLE`

### EntryType Enum Changes

**Add:** `ALLOTMENT`, `TENURE_CHANGE`, `LAND_ACQUISITION`, `LEASE`, `SEIZURE`, `UNAVAILABLE`

**Remove/Deprecate:** `DEATH` (use INHERITANCE), `MUTATION` (use appropriate specific type), `LOAN_CLOSE` (use RELEASE), `REDEMPTION` (use RELEASE), `MORTGAGE` (use LOAN), `PERSONS_ADD` (use INHERITANCE or CORRECTION), `TRANSFER` (use SALE), `UNKNOWN` (use UNAVAILABLE)

### Pass 1 Type Normalization

If the LLM outputs a non-canonical type, normalize in code before Pass 2:

| LLM Output | Normalized To |
|---|---|
| MORTGAGE | LOAN |
| DEATH | INHERITANCE |
| LOAN_CLOSE | RELEASE |
| REDEMPTION | RELEASE |
| CHARGE_REMOVED | RELEASE |
| TRANSFER | SALE |
| MUTATION | INHERITANCE |
| PERSONS_ADD | INHERITANCE |
| SUBDIVISION, DIVISION | PARTITION |

The existing Gujarati-to-English type mapping (e.g., `વેચાણ` → `SALE`, `મૃત્યુ` → `INHERITANCE`) moves into `pass1_prompt.py` as part of the classification instructions so the LLM handles translation. The code-side `type_mapping` dict in `entry_schema.py` is retained as a safety net for any non-canonical outputs.

### Person Dataclass Deprecation

The `Person` dataclass is deprecated. All name fields become `List[str]` (flat strings). The `Person` class remains in code for backward compatibility but is no longer instantiated in the new pipeline. Any code that accesses `Person.name` or `Person.role` should be updated to work with plain strings.

## 5. Few-Shot Examples


Each type config includes 2-3 real examples from `sampleentry.md` showing:
1. The raw entry text (what the LLM sees in the PDF)
2. The expected structured JSON output

Examples are stored in the type config registry (`type_configs.py`) alongside schemas and templates.

**Coverage from sampleentry.md:**

| Type | Examples Available | Status |
|---|---|---|
| SALE | 10 | Covered |
| INHERITANCE | 20 | Covered |
| PARTITION | 13 | Covered |
| RELINQUISHMENT | 3 | Covered |
| EXCHANGE | 2 | Covered |
| LIFETIME_DISTRIBUTION | 5 | Covered |
| GIFT | 0 | User will provide |
| LOAN | 78 | Covered |
| RELEASE | 18 | Covered |
| SEIZURE | 2 | Covered |
| ORDER | 1 | User will provide more |
| ALLOTMENT | 7 | Covered |
| TENURE_CHANGE | 4 | Covered |
| LAND_ACQUISITION | 3 | Covered |
| LEASE | 3 | Covered |
| PROMULGATION | 2 | Covered |
| CORRECTION | 5 | Covered |
| NOT_RELATED | 6 | N/A (fixed text) |
| UNAVAILABLE | 5 | N/A (fixed text) |

## 5. Post-Processing

After Pass 2 returns structured fields:

1. **Date normalization** — `_normalize_date_str()` applied to all date fields (2-digit years expanded to 4-digit: 00-30 → 2000s, 31-99 → 1900s)
2. **Survey number normalization** — "Part" → "p", preserve "/" characters
3. **Amount formatting** — Ensure "Rs. X,XX,XXX/-" format
4. **Create typed entry objects** — Map Pass 1 classification + Pass 2 fields into dataclass instances
5. **Active encumbrance detection** — Uses structured `lender` field directly from LOAN/RELEASE entries instead of regex-parsing from prose

### Missing Field Handling

If a field is missing from the LLM response, the corresponding clause is omitted from the template. No filler text or generic messages. Blank entries stay blank.

### Active Encumbrance Detection (Updated)

`detect_active_encumbrances()` signature changes to accept typed entry objects (dataclass instances) instead of raw dicts. It reads:
- `entry.type` — to identify LOAN, RELEASE, and SEIZURE entries
- `entry.lender` (on LOAN entries) — structured bank name, no regex needed
- `entry.lender` (on RELEASE entries) — to match against loans
- `entry.reference_entry_number` (on RELEASE entries) — explicit entry reference

**SEIZURE entries** are NOT treated as separate active encumbrances. A seizure is an enforcement action on an existing loan — the underlying LOAN entry is already tracked. Seizure entries are rendered in the chain of title but do not create additional encumbrance flags.

### Error Handling

**Pass 1 failure:** Retry up to 3 times with exponential backoff (using existing `retry_with_backoff`). If all retries fail, raise an exception — no fallback to old pipeline.

**Pass 2 failure:** Same retry policy. If Pass 2 fails after retries, the entries from Pass 1 are still available with entry_number, date, type, and certification. Template rendering proceeds with only those fields — most clauses will be omitted but the entry headers and certification lines will still render.

**Partial Pass 2 results:** If Pass 2 returns data for some entries but not others, the missing entries proceed with Pass 1 data only (entry header + certification, no description body).

### Amount Field Convention

Amount fields (e.g., `consideration_amount`, `amount`) store the numeric value only (e.g., `"2,50,000"`). The template hardcodes the "Rs." prefix and "/-" suffix. Post-processing ensures Indian comma formatting.

### Survey Number Mapping Direction

All survey number mappings use **old → new** direction: `{"159": "105"}` means old Survey No. 159 became new Survey No. 105. This convention is consistent across Pass 1 `land_details.survey_number_mapping` and the PROMULGATION type schema.

## 6. DOCX Rendering

### Chain of Title Entry Format

Each entry in the chain of title table cell renders as:

```
Line 1 (bold): "Entry No. {entry_number} Dated {date}"
Line 2+: {description assembled from template + structured fields}
Next line (no gap): "The Entry is {status} by {official} on {date}."
```

**Certification is on a new line immediately after the description, with no empty line between them.** The description paragraph ends, certification starts on the next line in the same cell.

### Template Rendering

Each type has a `render(entry) -> str` function that:
1. Checks which optional fields are present
2. Builds the description string, omitting clauses for missing fields
3. Returns the description text

For PARTITION and LIFETIME_DISTRIBUTION entries with allocation tables, the renderer builds a numbered list within the cell:
```
1. Vadher Hamirbhai Shankarbhai - Survey No. 122 - 3-12 Acre-Guntha
2. Vadher Nanubhai Shankarbhai - Survey No. 213 - 4-28 Acre-Guntha
3. Vadher Vajjubhai Shankarbhai - Survey No. 38/1 - 11-06 Acre-Guntha, Survey No. 379 - 6-13 Acre-Guntha
```

NOT_RELATED and UNAVAILABLE return their fixed strings with no field lookup.

### LLM Fallback Mechanism

For entries where the type is recognized but the template cannot produce a meaningful description (e.g., all type-specific fields are missing from Pass 2), the entry renders with only the header line ("Entry No. X Dated DD/MM/YYYY") and certification. No fallback to LLM-generated prose — the structured pipeline is the only path.

The "~80% templated" estimate refers to field coverage: most entries will have all fields populated, but some will have partial fields, resulting in shorter descriptions with omitted clauses. This is acceptable — a shorter factual description is better than fabricated prose.

## 7. Logging Strategy

### Pass 1 Logging
- `DEBUG`: Full prompt sent to Gemini
- `DEBUG`: Raw Gemini response
- `INFO`: Number of entries found, type distribution
- `DEBUG`: Per-entry classification: `"Pass 1: Entry {num} -> {type}"`
- `INFO`: Land details extracted

### Pass 2 Logging
- `INFO`: Which type schemas included in prompt
- `DEBUG`: Full dynamic prompt sent to Gemini
- `DEBUG`: Raw Gemini response
- `DEBUG`: Per-entry fields populated vs missing
- `WARNING`: Entries with incomplete extraction: `"Pass 2: Entry {num} ({type}) missing fields: {fields}"`

### Template Rendering Logging
- `DEBUG`: Per-entry: `"Render: Entry {num} ({type}) -> {len} chars"`
- `DEBUG`: Omitted clauses: `"Render: Entry {num} field '{field}' missing, clause omitted"`

### Post-Processing Logging
- `DEBUG`: Date normalizations applied
- `DEBUG`: Survey number mappings used
- `INFO`: Active encumbrances detected with lender names

### Summary Log (INFO, always visible)
```
"Extraction complete: {n} entries, Pass 1: {t1}ms, Pass 2: {t2}ms,
 Types: {type_counts}, Incomplete: {n_incomplete}"
```

## 8. File Structure

### New Files
- `tsr_generator/extractors/type_configs.py` — Registry of all type schemas, few-shot examples, and description templates. One dict per type.
- `tsr_generator/extractors/pass1_prompt.py` — Pass 1 prompt builder (classification + land details)
- `tsr_generator/extractors/pass2_prompt.py` — Pass 2 dynamic prompt builder (type-aware field extraction)
- `tsr_generator/extractors/template_renderer.py` — Assembles description strings from templates + structured fields

### Modified Files
- `tsr_generator/extractors/unified_extractor.py` — Replace single LLM call with two-pass orchestration. `extract_all_unified()` becomes coordinator.
- `tsr_generator/extractors/entry_schema.py` — Update dataclasses with actual type-specific fields. Add new types: ALLOTMENT, TENURE_CHANGE, LAND_ACQUISITION, LEASE, SEIZURE, UNAVAILABLE.
- `tsr_generator/document/docx_generator.py` — Use template-rendered descriptions. Certification on new line, no gap.
- `tsr_generator/extractors/findings.py` — Simplify `detect_active_encumbrances()` to use structured `lender` field directly.

### Unchanged Files
- `tsr_generator/document/tsr_document.py` — Orchestration unchanged
- `tsr_generator/api/tsr_generator_optimized.py` — Still calls `extract_all_unified()`, interface unchanged

## 9. Data Flow Summary

```
PDF text
  -> pass1_prompt.py builds classification prompt
  -> Gemini call #1 -> land_details + entry classifications + certification
  -> pass2_prompt.py builds dynamic extraction prompt
     (only includes schemas + examples for types found in Pass 1)
  -> Gemini call #2 -> structured fields per entry
  -> entry_schema.py creates typed entry objects
  -> template_renderer.py assembles descriptions from templates
  -> docx_generator.py renders into DOCX (certification on new line)
```

## 11. Design Decisions Summary

1. **Two-pass extraction** — Pass 1 classifies, Pass 2 extracts with type-aware prompts
2. **19 first-class types** — All types get their own schemas and templates
3. **No LLM fallback** — Template-only rendering; missing fields produce shorter descriptions, not LLM prose
4. **Flat string names** — `Person` dataclass deprecated; roles defined by field position in type-specific schema
5. **Old-to-new survey number mapping** — Extracted in Pass 1 from promulgation entries, consistent `{old: [new]}` direction
6. **Certification on new line, no gap** — Separate line immediately after description
7. **NOT_RELATED / UNAVAILABLE** — Fixed text, no extraction needed
8. **Missing fields omit clauses** — No filler text, blank entries stay blank
9. **Few-shot examples from sampleentry.md** — 2-3 per type (user providing gaps for GIFT, ORDER)
10. **Comprehensive logging** — DEBUG/INFO/WARNING at every pipeline step
11. **Dynamic prompt construction** — Only relevant type schemas included per document
12. **Type normalization** — Non-canonical LLM outputs (MORTGAGE, DEATH, etc.) normalized to canonical types in code
13. **SEIZURE not a separate encumbrance** — Seizure is enforcement on existing loan, not a new encumbrance
14. **Amount fields store numbers only** — Templates add "Rs." and "/-"
15. **Error handling** — 3 retries with backoff per pass; Pass 2 failure degrades to header+certification only
