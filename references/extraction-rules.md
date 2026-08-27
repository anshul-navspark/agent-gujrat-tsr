# TSR extraction rules

**These rules and the Python constants in
`tsr_generator/extractors/unified_extractor.py` must stay identical.**

The rules below are lifted verbatim from `ENTRY_TYPE_RULES`, `FORMATTING_RULES`,
`DESCRIPTION_EXAMPLES` and `CERTIFICATION_PATTERNS` in that module. Do not edit
one copy alone: change the Python constant and re-copy it here, or change it
here and copy it back. `tests/test_render_seam.py` fails the build if the two
drift apart.

## Why this file exists

The pipeline is four steps, and only one of them needs a model:

| step | what it does | needs a model? |
|---|---|---|
| fetch | village + survey -> land-record PDF | no |
| text | PDF -> plain text | no |
| **extract** | **text -> JSON** | **yes** |
| render | JSON -> TSR .docx | no |

Only extraction needs a model. It can run through the CLI path
(`extract_all_unified`, which sends the constants below as one prompt) or
inside an agent that reads the record itself. Both must produce the same
document, so both must follow the same drafting conventions — the ones the
lawyer has corrected over successive reviews (the transliteration of ઘ, the
"Borewell-1" convention, the omitted release-certificate date, and the rest).

An agent doing the extraction reads this file. The CLI reads the Python
constants. They are the same text.

## The JSON contract

Extraction produces exactly this object — the shape `build_unified_prompt()`
asks for, and the only shape `gujtsr.render.render_tsr` /
`render_tsr_from_extraction` accept. Do not invent fields.

```json
{
  "land_details": {
    "village_name": "",
    "taluka_name": "",
    "district_name": "",
    "survey_number": "",
    "old_survey_number": "",
    "total_area": "",
    "nature_of_land": "",
    "owner": ""
  },
  "entry_numbers": [],
  "mutation_entries": [
    {
      "entry_number": "",
      "date": "",
      "type": "",
      "description": "",
      "entry_status": "",
      "certification_status": "",
      "certification_official": "",
      "certification_date": ""
    }
  ]
}
```

Field notes:

- `land_details` (**required**, object). Everything translated to English.
  `nature_of_land` carries BOTH tenure (Old/New) and use (Agricultural/
  Non-Agri), comma-separated. `survey_number` renders "Paiki"/"Part"/"pk" as
  `p` and keeps the slash — `150/p1`, never `150p1`. `total_area` is the bare
  numeric form (`1-88-48`), without the word "Hectare". `old_survey_number` is
  just the number when a promulgation entry maps old to new, else `""`.
- `entry_numbers` (list of strings). Every entry number in the "Entry Details"
  index, asterisks and trailing Gujarati stripped. Khata/survey/form numbers
  are NOT entry numbers. Numbers listed here with no detail row still belong
  here — the renderer emits a placeholder chain row for them.
- `mutation_entries` (**required**, list of objects). One per entry.
  - `entry_number` — required on every entry; the renderer keys the chain-of-
    title bookmarks and the findings cross-references off it.
  - `date` — `DD/MM/YYYY`, 4-digit year, or `""`.
  - `type` — one of: LOAN, DEATH, RELEASE, LOAN CLOSE, SALE, PARTITION,
    PERSONS ADD, TO TRANSFER, EXCHANGE, LIFETIME DISTRIBUTION, NOT RELATED,
    ORDER, RELINQUISHMENT, PROMULGATION.
  - `description` — English, drafted to the rules below.
  - `entry_status` / `certification_status` — `certified`, `rejected`,
    `not_accepted`, or `""`.
  - `certification_official` — the POST/DESIGNATION and PLACE, not a personal
    name ("C.O. Porbandar", "Deputy Mamlatdar Super, Porbandar").
  - `certification_date` — `DD/MM/YYYY`.

An entry with an empty `description` is dropped from the chain of title, so
never emit an empty description for an entry that exists — use the standard
index-only wording in the rules below instead.

Render it with:

```
python -m gujtsr render extraction.json --output TSR.docx [--client <id>]
python -m gujtsr render - --output TSR.docx   # JSON on stdin
```

Bad input comes back as `{"success": false, "error": "..."}` naming the
offending field. `--client` takes an id from `clients.json`; omitting it uses
that file's `default_client_id`.


## Entry type classification

Verbatim from `unified_extractor.ENTRY_TYPE_RULES`.

```text
Entry Type Classification:
- LOAN: "took a loan" or "loan of Rs."
- RELEASE/LOAN CLOSE: "removing the charge" or "exemption of burden"
- SALE: "sold" and "consideration of Rs."
- INHERITANCE/DEATH: "upon the demise" or "came to be mutated in his legal heirs"
- PARTITION: "distribution took place" or "distributed his land"
- EXCHANGE: "exchanged their respective lands"
- RELINQUISHMENT: "relinquished their respective share"
- ORDER: "Taluka Circular" or "was allotted"
- LIFETIME DISTRIBUTION: "life time distribution"
- NOT RELATED: "not related to present survey"
- PROMULGATION: "re-survey" or "promulgation"
```

## Formatting rules

Verbatim from `unified_extractor.FORMATTING_RULES`.

```text
Formatting Rules:
1. ALL descriptions MUST start with "That" (except NOT RELATED, PROMULGATION)
2. DO NOT use honorifics like "Shri", "Smt", "Mr.", "Mrs."
3. DO NOT use "account holder", "mortgaged his total land", "of [village] village"
4. For LOAN/RELEASE entries, DO NOT include "based on the agreement dated..." commentary. (For INHERITANCE/DEATH and PARTITION/LIFETIME DISTRIBUTION entries you MUST include a closing sentence listing the documents the mutation was based on — see the description examples.)
5. Keep descriptions direct and factual. Include all legally relevant details. Do not add commentary or explanatory sentences.
6. Amounts: "Rs. X/-" or "Rs. X,XXX/-"
7. ALWAYS use "Survey No." instead of "Khata No." or "Account No."
8. Documents: "document no. X dated DD/MM/YYYY"
9. Translate "Paiki" or "Part" or "part" or "pk" as "p" in survey numbers (e.g. "150/p1")
10. IMPORTANT: Preserve "/" in survey numbers (e.g., "387/p3" NOT "387p3")
11. Use caste titles only when part of the name: Thakor, Patel, Kanbi, Choudhary, Rabari, Vadher, Solanki
12. Measurements: Use "Acre/Guntha" or "Hectare" in descriptions. For the total_area field, output ONLY the numeric format (e.g., "1-88-48") WITHOUT the word "Hectare".
13. Translate "bhen" or "ben" suffix as "ben" (e.g. "Shantiben")
13a. TRANSLITERATION - do not confuse these three letters:
   ઘ = "Gh"  (ઘોહાભાઈ = Ghohabhai, NOT Dhohabhai; ઘુના = Ghuna)
   ધ = "Dh"  (ધીરાણ = dhiran, ધોહાભાઈ = Dhohabhai)
   દ = "D"   (દેહુરભાઈ = Dehurbhai)
   Rendering ઘ as "Dh" misspells the title holder's name - corrected by the
   lawyer on 2026-07-28 (Bhagubhai Ghohabhai, survey 57p1).
   When the SAME person's name is spelled inconsistently across the record
   (AnyRoR does this), use the spelling that appears most often rather than
   whichever the Ownership Details row happens to use.
14. Lists: "which are as follows:-" followed by names on separate lines
15. OMIT vague filler like "This entry was made based on the above." Keep descriptions concise — but DO retain the concrete supporting-documents clause for INHERITANCE/DEATH and PARTITION/LIFETIME DISTRIBUTION entries (application/Arji, death certificate, genealogy/Pedhinamu, affidavits/Sogandnama) when the source states them.
16. LOAN entries: Do NOT include agreement date. Only describe the loan, borrower, lender, amount, and land details.
17. OLD SURVEY NUMBERS: If there is a PROMULGATION entry (re-survey), use "old Survey No." for all entries BEFORE the promulgation entry. Use "Survey No." for entries AFTER promulgation. If there is NO promulgation entry, use "Survey No." (without "old").
18. Always use 4-digit years (DD/MM/YYYY). Never use 2-digit years (DD/MM/YY).
19. Include Khata number in parentheses after each survey number when visible in the source document, e.g., "5/2(28), 193p1(28)". If no Khata number is visible, omit parentheses.
20. Translate "Prant Officer" / "પ્રાંત અધિકારી" as "Province Officer". Use "Province Officer" and "Province court" consistently.
21. BOREWELL NAMING: Always use the full word "Borewell" with hyphenated number — "Borewell-1", "Borewell-2". NEVER write "Bore-1", "bore-1", "pucca bore-1", "1 pucca borewell", "pucca borewell-1". The Gujarati "પાકાે બાેર - ૧" / "પાકાે બાેર" / "બાેર ૧" all map to "Borewell-1" (drop "pucca"; that adjective is implicit).
```

## Description examples

Verbatim from `unified_extractor.DESCRIPTION_EXAMPLES`.

```text
Example descriptions (follow these exact patterns):

AREA INCLUSION RULE:
- For every entry type EXCEPT LOAN and RELEASE (a.k.a. LOAN CLOSE / charge removal), when the source entry mentions a land area (e.g. "હે. ૬-૨૧-૨૦", "Hectare 1-88-48", "3 Acre 23 Guntha", "આ. હે. ચો.મી.", "જમીન હે ..."), you MUST include it in the English description as "measuring <area> Hectare" (or "Acre/Guntha" if the source uses those units), immediately after the Survey No. clause.
- Convert Gujarati numerals to English digits. Preserve the dash-separated format (e.g. "6-21-20").
- For LOAN and RELEASE entries: do NOT include any area / hectare / acre measurement — even if the source mentions one. The encumbrance is recorded against the surveys themselves; area is intentionally omitted to keep loan/release descriptions tight.
- For all other types (SALE, DEATH/INHERITANCE, PARTITION, GIFT, ALLOTMENT, RELINQUISHMENT, LIFETIME_DISTRIBUTION, EXCHANGE, ORDER allotment/circular, TENURE_CHANGE, LAND_ACQUISITION, LEASE, SEIZURE, PROMULGATION, CORRECTION): include area whenever the source states one.

LOAN (correct, no area): "That Mer Deva Depa took a loan of Rs. 20,000/- on land bearing old Survey No. 373/p1, 359, 390, 389(215) from Bank of India, Modhvada Branch."
LOAN (wrong - includes area): "That Mer Deva Depa took a loan of Rs. 20,000/- on land bearing old Survey No. 373/p1, 359, 390, 389(215) measuring 6-21-20 Hectare from Bank of India, Modhvada Branch." - DO NOT include area in loan descriptions, even when the source shows it.
LOAN (wrong - includes agreement date): "That Mer Deva Depa took a loan of Rs. 20,000/- from Bank of India, Modhvada Branch based on an agreement dated 14/05/2005." - DO NOT include agreement date!
LOAN (wrong - too verbose, mortgaging language): "That account holder Shri Mer Deva Depa of Keshav village mortgaged his total land of 6-21-20 Hectare of Keshav village, Khata No. 215, bearing Survey No. 390, with Bank of India, Modhwada branch, to obtain a loan of Rs. 20,000/-. This encumbrance entry was recorded based on the agreement dated 14/05/2005." - drop the village-name padding, "account holder", "mortgaged his total land", trailing commentary, AND the area.

IMPORTANT for LOAN entries:
- DO NOT include "agreement dated" or "based on an agreement"
- DO NOT include total land area or hectare measurements in loan descriptions.
- State: borrower name, loan amount, survey numbers (with khata in parentheses), bank name and branch.
- INCLUDE ALL survey numbers listed in the entry's "Other Rights" / બોજા / બીજા હક્ક column, NOT only the subject survey number. A single loan entry frequently encumbers many surveys belonging to the same khata (e.g. "421(608), 422(608), 423(608), 500(608), 501(608), 568(608), 574(715), 602(608), 603(608), 608(608), 609(608)") — output the COMPLETE list exactly as it appears in the source, in the same order, with the khata number in parentheses after each. Do NOT filter, deduplicate, or drop survey numbers just because they differ from the subject survey. The same rule applies to RELEASE / LOAN CLOSE entries that reference the same multi-survey charge.

Other patterns (include "measuring <area>" whenever the source states one — NOT for LOAN / RELEASE):
- DEATH/INHERITANCE: Include the death date. For EACH heir include their relationship (the heir table has columns સંબંધ = relationship and ઉં.વ. = age; પત્નિ/પત્ની=wife, પુત્ર=son, પુત્રી=daughter, વિધવા=widow, માતા=mother). End with a sentence listing the documents the mutation was based on when shown (application/Arji, death certificate, genealogy/Pedhinamu, affidavits/Sogandnama). Format:
"That upon the demise of [Name] on DD/MM/YYYY, his/her share in land bearing old Survey No. X(Khata), Y(Khata) measuring <area> Hectare came to be mutated in the names of his/her legal heirs which are as follows:-
[Heir1Name] - [relationship]
[Heir2Name] - [relationship]

"
  DO NOT output the closing supporting-documents sentence for INHERITANCE ("This inheritance was recorded based on the application, death certificate, genealogy (Pedhinamu) and affidavits."). The lawyer deletes it from every inheritance entry (2026-07-28 review of entries 607 and 1142). End the entry after the heir list, then the certification sentence. NOTE this applies to INHERITANCE ONLY — PARTITION keeps its closing sentence.
  DO NOT output heir AGES ("- age 50") or the death-certificate number ("(death certificate no. 3)") — per lawyer review 2026-07-28 these are stripped from the final report. Keep the exact death DATE.
  CRITICAL — when the source says the deceased died નિસંતાન / childless / issueless, you MUST carry that through as "(Childless)" immediately after that person's name. It is not descriptive detail: it is the legal reason the share devolves on a sibling's heirs rather than the deceased's own line. Example: "upon the demise of Lakhabhai Kathadbhai and Gilabhai Kanthadbhai (Childless), ...".
  Drop any segment the source does not provide — omit the closing supporting-documents sentence if no such documents are listed. NEVER invent a date, relationship, or document.
- SALE: "That [Seller] sold Survey No. X measuring <area> Hectare to [Buyer] for a consideration of Rs. [consideration]/- (market value Rs. [market value]/-) vide document no. Y dated DD/MM/YYYY."
  The Gujarati source for a sale typically states TWO amounts — માર્કેટ વેલ્યુ / market value (the jantri/assessed value, e.g. "માર્કેટ વેલ્યુ રૂ. 295020/-") AND અવેજ / અવેજની રકમ / consideration (the price actually paid, e.g. "અવેજની રકમ રૂ. 200000/-"). Capture BOTH whenever present: render the consideration as the primary "for a consideration of Rs." amount and append the market value in parentheses as "(market value Rs. .../-)". Omit the "(market value Rs. ...)" segment only when the source states no market value. NEVER invent, drop, or swap the two amounts — the consideration and the market value are distinct figures.
- PARTITION: When the source lists who received what, you MUST emit the full allocation list (one row per recipient) between the lead-in and the closing sentence, separated by blank lines. Do NOT collapse the lead-in straight into the closing sentence. Do NOT prefix rows with "1.", "2." — emit bare rows; numbering is applied automatically downstream. Format:
"That the said [OriginalOwner(s)] distributed their land bearing Survey No. X measuring <area> Hectare among themselves as follows:-
[Recipient1] - Survey No. [X] - [area]
[Recipient2] - Survey No. [Y] - [area]
[Recipient3] - Survey No. [Z] - [area]

The distribution/Partition of the shares as mentioned above was recorded based on their application, deed of partition and affidavits before the Notary as per their respective rights and physical possession."
  The closing sentence MUST name the documents the SOURCE actually cites. When the source says નોટરી રૂબરૂના સોગંદનામા (affidavit sworn before the Notary), write "affidavits before the Notary" — do NOT soften it to "their consent", which is wrong and was corrected by the lawyer on 2026-07-28. Likewise render વહેચણી અંગેનો લેખ as "deed of partition".
  Each allocation row goes on its own line. If the source omits area or survey for a recipient, leave that segment off (e.g. "[Name] - Survey No. 33"). NEVER produce a partition description that has "as follows:-" / "as under:-" followed immediately by the "The distribution..." closing line — the allocation rows MUST be present whenever the source shows them.
- LIFETIME_DISTRIBUTION / PERSONS_ADD / TO_TRANSFER: When multiple beneficiaries are listed, emit them as bare rows (one per line, no "1.", "2." prefixes):
"That the said [Distributor] made an application of life time distribution in his land bearing Survey No. X measuring <area> Hectare to [add/transfer to] his legal heirs which are as follows:-
[Beneficiary1]
[Beneficiary2]"
  Single-beneficiary lifetime distributions stay as one prose sentence (no list).
- RELEASE (no area): "That upon receiving an application from [Name] for removing the charge of [Bank], [Branch]. The said exemption of burden has been recorded. Entry No. X."
  NEVER state the release certificate date in ANY phrasing — not "on its certificate dated DD/MM/YYYY", not "on the basis of the certificate dated DD/MM/YYYY", not "vide certificate dated ...", and not the issuing body's certificate date (Liquidator, District Registrar, bank or society). Drop the whole clause. NEVER state the lender's release-certificate date (the "તા.DD/MM/YYYY નાં દાખલા" the release cites). House convention omits it entirely — only the entry's own date and its certification date appear in the report. Confirmed 2026-07-28.
- ORDER (government allotment): "That Government survey was conducted and land bearing Survey No. X measuring <area> Hectare was allotted to [Name]."
- ORDER (circular): "That as per Taluka Circular No. X dated Y, Survey No. Z measuring <area> Hectare allotted to [Name]."
- ORDER (error correction): Keep the order's identifying preamble (issuing authority, order number, date, village) in full, then include ONLY the numbered correction item(s) that concern the SUBJECT survey number. A promulgation-correction order routinely lists 30+ unrelated surveys; reproducing all of them buries the relevant line and the lawyer deletes them (2026-07-28 review: 33 items emitted, 1 kept). Preserve the source's own item number so the citation stays traceable. Example: "Vide order was passed by the Mamlatdar, Talaja, vide No. E-Dhara/Worksheet/Bodki-08 dated 14/08/2008, for correcting the errors found in the promulgation of the computerized Village Form No. 7/12 of village Bodki, the corrections in the rights record are as follows:- 26. Survey No. 44(125) - Malubai Alubai". If NO listed item concerns the subject survey, say so plainly rather than dumping the whole list.
- NOT RELATED: "This Entry is not related to Present Survey Number."
- INDEX-ONLY ENTRY: when an entry number appears in the "Entry Details" index list but the record contains NO detail row for it (common for pre-1970 entries that predate the digital record), output exactly: "However, this entry is not shown on the website i.e. anyror but upon physical verification we found this entry related to present Survey No." This is the firm's standard wording for an entry absent from AnyRoR (approved 2026-07-28); the lawyer then fills the entry body from the old scanned Village Form 7/12 during review. Do NOT write "content is not legible" — the content is not illegible, it is absent — and do NOT emit an empty description. Never invent the entry.
- PROMULGATION: Extract the FULL procedural text. Include: issuing authority, court name, all order numbers with dates, public notice and objection period, Mamlatdar preparation, Province Office verification, finalization, page/survey range. Do NOT summarize. Preserve old/new area pairs verbatim (e.g. "old area 7-59-29 Hectare, new area 7-70-84 Hectare").
```

## Certification patterns

Verbatim from `unified_extractor.CERTIFICATION_PATTERNS`.

```text
CRITICAL - Translate Gujarati status words in certification:
| Gujarati | English Translation | entry_status value |
| રદ | cancelled | "rejected" |
| ના મંજૂર | not accepted | "not_accepted" |
| નામંજુર | rejected | "rejected" |
| નામંજૂર | rejected | "rejected" |
| પ્રમાણિત | certified | "certified" |

Certification output formats:
- If રદ found: "The Entry is cancelled by [Name] on DD/MM/YYYY." + entry_status: "rejected"
- If ના મંજૂર or નામંજુર found: "The Entry is not accepted by [Name] on DD/MM/YYYY." + entry_status: "not_accepted"
- If પ્રમાણિત found: "The Entry is certified by [Name] on DD/MM/YYYY." + entry_status: "certified"
- Always output certification dates in 4-digit year format (DD/MM/YYYY).
- Default if unclear: entry_status: "" (empty)

IMPORTANT: Do NOT output "certified" if the Gujarati text contains રદ, ના મંજૂર, or નામંજુર!

CERTIFICATION EXTRACTION IS REQUIRED:
- certification_official and certification_date are REQUIRED fields for all certified/rejected entries when visible in the source document.
- Always extract the certifying officer designation and place (e.g., "C.O. Jadiya", "Mamlatdar Dhanera") into certification_official.
- Always extract the certification date in DD/MM/YYYY format into certification_date.
- Do NOT output just "The Entry is certified." if officer name or date is visible in the document.
```
