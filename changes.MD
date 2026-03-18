# Gujarat TSR Agent — Language & Content Quality Improvement Report

*Based on comparison of 29 AI-generated vs. manually generated TSR pairs | 17 March 2026*

---

## Executive Summary

After comparing all 29 matching TSR document pairs, the AI agent produces structurally sound documents with correct legal terminology and proper formal register. However, there are **8 specific, actionable language and content improvements** that would bring AI output to parity with the manually generated versions. These fall into three categories: phrasing differences in the body text, content completeness gaps in chain-of-title entries and the observations table, and minor formatting inconsistencies.

The issues flagged previously as "critical" (reference codes, dates, letterhead, signature block) are handled outside the AI's language generation scope and are excluded from this analysis. Similarly, blank chain-of-title entries for handwritten content are by design.

---

## 1. Introduction Paragraph — Extra Phrase

**Severity:** Medium | **Affects:** All 29 files

The AI inserts the phrase "as per above subject reference" in the opening paragraph, which the manual versions do not consistently include.

| AI Version                                                                                                                       | Manual Version                                                                           |
| -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| We have been engaged**as per above subject reference** for the Title Investigation of land situated at Village- Malotra... | We have been engaged for the Title Investigation of land situated at Village- Malotra... |

**Recommendation:** Remove "as per above subject reference" from the introductory paragraph template. The Re: email reference line (handled separately) already establishes the engagement context.

---

## 2. Extra Sub-header Paragraph — "The Borrower has acquired..."

**Severity:** Medium | **Affects:** ~20 of 29 files

The AI generates an additional paragraph between the "Description, nature, and area of land" header and the property table:

| AI Version (extra paragraph)                                                                                                                                         | Manual Version                                                                                       |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| The Borrower has acquired/purchased the Immovable Properties description whereof (including the names of the Title Holders/Sellers) have been tabulated hereinbelow: | *[This paragraph does not appear. The property table follows directly after the section heading.]* |

**Recommendation:** Remove this intermediate paragraph. The section heading "Description, nature, and area of land with survey/plot numbers" is sufficient introduction to the property table.

---

## 3. Section Numbering Prefix on Headers

**Severity:** Low | **Affects:** All 29 files

The AI prefixes section headers with numbers while the manual versions use the header text alone:

| AI Version                                             | Manual Version                                     |
| ------------------------------------------------------ | -------------------------------------------------- |
| 3.  Chain of Title                                     | Chain of Title                                     |
| 4.  Findings & opinion based our title investigation:- | Findings & opinion based our title investigation:- |

**Recommendation:** Drop the numeric prefix from "Chain of Title" and "Findings & opinion" section headers. The document structure is clear without them.

---

## 4. Chain of Title Entry Language — Charge Removal Phrasing

**Severity:** HIGH | **Affects:** All files with bank charge entries

This is the most impactful language difference. When describing charge removal entries, the AI uses a condensed, informal phrasing while the manual versions use the full formal legal language:

| AI Version (condensed)                                                                                                                                   | Manual Version (full legal language)                                                                                                                                                                                                             |
| -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| That charge of State Bank, Dhanera removed on application of Patel Ukabhai Godabhai and Raymalbhai Godabhai. Ref Entry No. 1923. The Entry is certified. | That upon receiving an application from said Patel Raimal Goda and Uka Goda for removing the charge of State Bank of India, Dhanera Branch. The said exemption of burden has been recorded. The Entry is certified by C.O. Jadiya on 20/05/2004. |

Key differences in the charge removal language:

- **a)** AI says "charge of [bank] removed" → Manual says "upon receiving an application from said [person] for removing the charge of [bank]. The said exemption of burden has been recorded."
- **b)** AI omits the formal phrasing "The said exemption of burden has been recorded" which is standard legal language for charge discharge.
- **c)** AI omits the certifying officer name and certification date (e.g., "by C.O. Jadiya on 20/05/2004").

**Recommendation:** Update the chain-of-title entry template for charge removals to use: *"That upon receiving an application from said [Name] for removing the charge of [Bank/Institution], [Branch]. The said exemption of burden has been recorded. Entry No. [ref]. The Entry is [certified/rejected] by [Officer] on [date]."*

---

## 5. Chain of Title — Succession/Mutation Entry Language

**Severity:** HIGH | **Affects:** All files with succession entries

For succession and mutation entries, the AI summarizes content while the manual versions provide the full legal detail including survey numbers with Khata references:

| AI Version                                                                                                                                                       | Manual Version                                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Entry No. 3227 Dated 13/01/11 That upon demise of Patel Ukabhai Godabhai on 28/11/2010, his name is removed from land bearing old Survey No. 34/1, 72/2, 191/p3. | Entry No. 3227 Dated 13/01/2011 That upon the demise of Patel Ukabhai Godabhai, his respective share in land bearing old Survey No. 34/1(430), 72/2(430), 191p3(430) to his brother i.e. Patel Raimalbhai Godabhai. The Entry is certified by Mamlatdar Dhanera on 03/03/2011. |

Key differences:

- **a)** AI omits Khata numbers in parentheses after survey numbers — e.g., "34/1" vs "34/1(430)".
- **b)** AI says "his name is removed" (passive) vs manual "his respective share... to his brother i.e. [Name]" (specifies the transferee).
- **c)** AI uses 2-digit years ("13/01/11") vs manual 4-digit years ("13/01/2011").
- **d)** AI omits who certified and when ("by Mamlatdar Dhanera on 03/03/2011").

**Recommendation:** For succession entries, include: (1) Khata numbers in parentheses after survey numbers, (2) the full name of the person(s) inheriting, (3) 4-digit year format, and (4) certifying officer and date.

---

## 6. Chain of Title — Re-Survey Entry (4672) Over-Summarized

**Severity:** Medium | **Affects:** All 29 files (this entry appears in every TSR)

Entry 4672 documents the village-wide re-survey promulgation. The AI provides a brief summary while the manual version includes the full procedural history:

| AI Version (~30 words)                                                                                                                                                                                                                  | Manual Version (~120 words)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Entry No. 4672 Dated 18/01/17 That Re-survey promulgation of Malotra village is finalized as per order no. Jamin/Re-survey/Promulgation/Malotra/Vashi.163 to 170/17 dated 16/01/2017 of Prant Officer, Dhanera. The Entry is certified. | Entry No. 4672 dated 18.01.2017 Vide Order of Province Officer and Province court, Dhanera, Banaskantha order no. Land/RSV/7/12/Promul/Dhanera/2016-17 vashi 7392 to 7402 Dated 06/09/2016 – A public notice was issued calling for any objection within 30 days of notice, regarding re-survey. The record was sent as per the objection applications submitted during the aforesaid period, after that new records were prepared by Mamlatdar and were verified by Province office, Dhanera vide order no. Land/Resurvey/Promulgation/Malotra/Vashi.163 to 170/17 dated 16/01/2017. The promulgation of records has been finalised. According to which old – new survey numbers, Area, Shape, All the details of the occupiers are also included. Along with this, the notice of promulgation of total 1294 pages from survey number 0 to survey number 9008 of Malotra village are recorded. The entry is certified. |

**Recommendation:** Since Entry 4672 is identical across all Malotra village TSRs, hard-code the full manual version as a template constant for this specific entry. The procedural chain (public notice → objection period → Mamlatdar preparation → Province Office verification → finalization) is legally significant.

---

## 7. Observations Table (Table 4) — Content Differences

**Severity:** HIGH | **Affects:** Multiple files

The Observations table has several systematic content differences:

| Row  | Field                                         | AI Says                                                | Manual Says                                                                                                                         |
| ---- | --------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| 2a   | Sub-registrar jurisdiction                    | Dhanera                                                | **Dessa and Dhanera**                                                                                                         |
| 3    | Encumbrance certificate period                | 13 years                                               | **30 years**                                                                                                                  |
| 5    | Additional suggestions for PFC                | Clear and marketable Subject to bank charge.           | **Clear and marketable subject to point 17 of Table No. 3 above.**                                                            |
| 18   | Findings on absolute, clear, marketable title | Clear and marketable Subject to bank charge.           | **Clear and marketable subject to point 17 of Table No. 3 above.**                                                            |
| Note | Chain of Title concluding note                | Clear and marketable. There is a Borewell on the land. | **Clear and marketable subject to bank charge. (Entry refs) / A correction order from DILR is required as area was reduced.** |

These are substantive legal content differences, not just stylistic:

- **a)** Jurisdiction: The AI misses "Dessa" as a secondary sub-registrar office. This should be extracted from the source data.
- **b)** Encumbrance period: "13 years" vs "30 years" is a significant factual difference that affects the scope of the title search.
- **c)** The AI uses a generic "Subject to bank charge" while the manual cross-references specific table rows ("subject to point 17 of Table No. 3 above") or specific entry numbers. This cross-referencing is important for legal traceability.
- **d)** The concluding Note in the chain of title should reference specific entry numbers when charges are subsisting, and flag correction orders where applicable.

**Recommendation:** These fields require the AI to: (1) look up jurisdiction from source data rather than defaulting to "Dhanera"; (2) use the correct encumbrance period from source; (3) cross-reference specific table rows/entry numbers in conclusions rather than using generic phrasing; (4) include all qualifying notes (borewell presence, correction orders, penalty confirmations) from the chain of title analysis.

---

## 8. Opinion Section — Truncated (2 vs 4 Paragraphs)

**Severity:** HIGH | **Affects:** All 29 files

The AI consistently generates only 2 opinion paragraphs where the manual versions have 4. The "Findings & opinion" section is the most legally significant part of the TSR, and the missing content likely includes extended analysis, qualifications, or conditions on the title opinion.

**Recommendation:** Review the opinion section template to ensure all 4 standard paragraphs are generated. The missing paragraphs likely contain: (1) qualifications or conditions attached to the title opinion, (2) specific recommendations or requirements before mortgage creation, and/or (3) cross-references to observations noted elsewhere in the report.

---

## Minor Formatting Differences

These are cosmetic and low-priority but worth noting for completeness:

| Item                     | AI                                      | Manual                                |
| ------------------------ | --------------------------------------- | ------------------------------------- |
| Dash character           | Double hyphen:`--`                    | Em dash:`–`                        |
| Survey number format     | `191/p3` (slash + lowercase)          | `191 P3` (space + uppercase)        |
| Area format              | `1-59-02 Hectare i.e.(15902 Sq. Mts)` | `1-91-18 - i.e.  (19118) Sq. Mts)`  |
| Name list numbering      | `1. Name` / `2. Name` (numbered)    | `Name` / `Name` (no numbers)      |
| Date format in entries   | `08/03/04` (2-digit year)             | `08/03/2004` (4-digit year)         |
| Observations row numbers | `1, 2, 3` (no period)                 | `1., 2., 3.` (with period)          |
| Bank name style          | `ICICI Bank, Ahmedabad`               | `I.C.I.C.I. Bank, Ahmedabad Branch` |

---

## Priority Summary

Ranked by impact on legal quality and polish:

| # | Priority         | Issue                                  | Key Action                                                                                         |
| - | ---------------- | -------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 1 | **HIGH**   | Charge removal entry language          | Use full formal phrasing: "upon receiving an application... exemption of burden has been recorded" |
| 2 | **HIGH**   | Opinion section truncated              | Generate all 4 opinion paragraphs, not just 2                                                      |
| 3 | **HIGH**   | Observations table content             | Fix jurisdiction, encumbrance period, and use cross-references instead of generic conclusions      |
| 4 | **HIGH**   | Succession entry detail                | Include Khata numbers, transferee names, certifying officer, 4-digit dates                         |
| 5 | **MEDIUM** | Re-survey entry (4672) summarized      | Hard-code full procedural text as a template constant                                              |
| 6 | **MEDIUM** | Extra intro phrases                    | Remove "as per above subject reference" and "The Borrower has acquired..." paragraph               |
| 7 | **LOW**    | Section number prefixes                | Drop "3." and "4." from section headers                                                            |
| 8 | **LOW**    | Minor formatting (dashes, dates, etc.) | Use em dashes, 4-digit years, uppercase survey format, periods after row numbers                   |
