# Lawyer Review Notes — 2026-05-20

Audit of one Trambo-150 TSR generated end-to-end from the local PDF
(`Kutch_Abdasa_Trambo_150_Original.pdf`) using the current `main` code
and the new Gemini key. Generated DOCX at `/tmp/trambo_150.docx`, PDF
render at `~/Downloads/trambo_150_view.pdf`, page screenshots at
`/tmp/trambo_hi-*.png` (Chain of Title is page 2).

## Numbering — no bug reproduced on this DOCX

Outer Chain of Title rows render as `1. 2. 3. 4. 5.` via OOXML
auto-numbering (numId=10, abstractNum 9). The numbering.xml is
well-formed and Word renders it correctly. The Note row at the bottom
correctly has no number.

Caveats worth confirming with a wider sample tomorrow:

- **Sub-list inside each entry** (e.g. `1. Kanji…  2. Naran…` under
  Entry 721) is still **literal text** from `_number_names_after_follows`,
  not OOXML auto-numbers. If a lawyer inserts a heir/distribution row
  mid-list, the rest don't renumber. The May-14 commit (a158ee2) only
  fixed the outer column.
- **Findings table SN column** (1–18 in this DOCX) is also literal
  text. Same issue.

If you have a previous DOCX where the outer numbers actually came out
wrong, share it tomorrow and I'll diff XML against this one.

## Content audit — per Chain-of-Title entry

Source = Gujarati village form for Trambo, Abdasa, Kutch, Survey 150/p1.

### Entry 125 & 243 — ✅ acceptable

Source contains only the entry numbers in the entry-list with no body.
Rendered as *"Entry No. 125 That Entry mentioned in the document but
content is not legible."* — appropriate fallback. Both correctly marked
certified.

### Entry 721 (21/05/2010, lifetime distribution) — ❌ hallucination

**Source distribution (3 rows):**

1. કાનજી માવજી ભાનુશાલી → ૪૬/૧, ૧પ૦ પૈકી, **૨/૪૮/૮૮**
2. નારાણ માવજી ભાનુશાલી → ૧પ૦ પૈકી, **૪/૦૬/૭૧**
3. પ્રેમજી માવજી ભાનુશાલી + અરવિંદ માવજી ભાનુશાલી (સંયુક્ત) —
   **no area specified**

**Rendered (2 rows):**

1. Kanji — 46/1, 150/p — 2-48-88
2. **Naran, Premji, Arvind (Jointly) — 150/p — 4-06-71** ← wrong

- LLM **merged** Naran's solo allocation with Premji+Arvind's joint row.
- LLM **attributed Naran's 4-06-71 to all three jointly**, which is a
  hallucination — that area belongs to Naran alone.
- **Missing**: source says "પુત્રોને" (to his sons); rendered just says
  "legal heirs". Less precise.
- **Missing**: source distinguishes ભાનુશાલી માવજી વીરજી's
  ખાતા નં. ૬૪; the khata number doesn't appear anywhere in the
  rendered text.

### Entry 905 (22/05/2019, lifetime distribution) — ⚠️ source typo + ugly format

**Source distribution:**

- (૧) નારાણ → ૧૦૫/પૈકી ૧ પૈકી ૧-૩૭-૨૫
- (ર) પ્રેમજી → ૧૦૫/પૈકી ૧ પૈકી ૧-૩૭-૨૬
- (૩) અરવિંદ → ૧૦૫/પૈકી ૧ પૈકી ૧-૩૭-૨૬

**Rendered:**

- 1. Naran — Survey No. **105/p1/p** — 1-37-25 Hectare
- 2. Premji — Survey No. 105/p1/p — 1-37-26 Hectare
- 3. Arvind — Survey No. 105/p1/p — 1-37-26 Hectare

- **Notation**: `105/p1/p` is what the LLM produced when transliterating
  `૧૦૫/પૈકી ૧ પૈકી`. The second "પૈકી" is the "out of which" qualifier on
  the area, not part of the survey number. Should read
  `Survey No. 105/p1 — 1-37-25 Hectare`.
- **Source data issue (worth flagging in findings)**: 105 in the body vs
  150 in the entry header is almost certainly a clerk's typo in the
  original village form. The areas (3 × ~1-37 ≈ 4-12) also exceed the
  khata's total area of 1-37-25. Tool faithfully transcribed both;
  nothing the LLM can do.

### Entry 983 (12/07/2023, inheritance) — ❌ multiple omissions

**Source:**

- નારાણ માવજી ભાનુશાલી died on **૧પ/૦૭/૨૦૨૧ (15/07/2021)**
- Death certificate ref: **D૨૦૨૧૨૭૯૦૩૪૭૦૦૩૯૩પ**
- Heirs with relationships and ages:
  1. શાંતિબેન — **wife (પત્નિ), age 57**
  2. વસંત — **son (પુત્ર), age 37**
  3. યોગેશ — **son (પુત્ર), age 34**
- Mutation based on: અરજી, મરણનો દાખલો, પેઢીનામું, સોગંદનામાં

**Rendered:**

- "upon the demise of Naran Mavji Bhanushali" — **death date dropped**
- "1. Shantiben… 2. Vasant… 3. Yogesh…" —
  **no relationships, no ages**
- **Supporting documents not mentioned**

All legally relevant facts.

## Recommended code changes (for tomorrow, post-lawyer-review)

1. **Extractor prompt** (`tsr_generator/extractors/unified_extractor.py`):
   - INHERITANCE/વારસાઈ: require death date, death certificate number
     (if present), per-heir `(relationship, age)`. Add an explicit
     few-shot example.
   - LIFETIME_DISTRIBUTION/PARTITION: require *one row per source row*;
     explicitly forbid merging when the source has both individual and
     joint allocations.
   - Survey-number formatting: rule that `પૈકી N પૈકી area` collapses to
     `Survey N/p1 — area`, not `N/p1/p`.

2. **`_number_names_after_follows`** in
   `tsr_generator/document/docx_generator.py`: switch in-cell sub-list
   to OOXML numPr (same trick as the outer table) so lawyers can
   insert/delete distribution rows without renumbering.

3. **Findings table** in `tsr_generator/document/tsr_document.py`: also
   a candidate for auto-numbering for the same reason.

## Gemini model question (parked for tomorrow)

Hold off switching the main extractor to `gemini-3.5-flash`. The audit
above already shows extraction missing obvious facts (death date,
relationships, joint-vs-solo allocations) on `gemini-3.1-pro-preview` —
dropping to flash will almost certainly make it worse. Safer experiment:
leave `GEMINI_MODEL_NAME=gemini-3.1-pro-preview`, try `gemini-3.5-flash`
for `CAPTCHA_MODEL_NAME` and `GEMINI_TRANSLATION_MODEL`, then A/B the
pro extractor against `gemini-3.5-flash` on one survey and compare
diffs side-by-side.

## Open items from this session

- AnyRoR is unreachable from this machine (foreign-IP geo-block; `ping`
  returns "No route to host"). Need VPN or the deployed scraper to
  generate the 4 surveys from the WhatsApp photo
  (Kharoda/Lakhpat 81, 12, 14 and Vayor/Abdasa 11).
- New Gemini key `AIzaSyCpl…az-JU` works for all models; older two keys
  are dead. Already in `.env` and saved to memory.
