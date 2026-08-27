---
name: tsr
description: Use when someone asks for a Title Search Report, TSR, or land title report for a village and survey number in Gujarat — "TSR for survey 44 in Bodki", "title report for Talaja", "pull the land record and draft the report". Goes from village + survey number to a draft TSR .docx in one request: fetches the record from AnyRoR, reads it, and renders the firm's report. Also use when someone gives a khasra or khata number and a village and expects a title report — those are the Rajasthan words for the same thing, but say that Gujarat records are addressed by survey number and ask for that. For the PDF alone use fetch-land-record; for a report from a PDF you already have use generate-tsr.
---

# Gujarat Title Search Report

Village + survey number in, a **draft** TSR `.docx` out. This is the path a lawyer
should normally use; the other two skills exist for when only half is wanted.

**The report is a draft, always.** It is not verified title advice. Every TSR goes
out under Vijay Choudhary's letterhead and signature, so what you produce is
material a lawyer checks and signs — never a final opinion. Say so when you deliver it.

## Before anything else

```bash
bash scripts/ensure_env.sh          # prints READY: <repo dir>, or fails with the reason
export GUJTSR=$HOME/gujrat_tsr_agent
```

If it fails, relay the reason verbatim and stop. The common causes are a missing
`GITHUB_TOKEN` (the engine repo is private), a missing `ANYROR_PROXY`, or no
`claude` CLI. None of these are things to work around.

## What you need from the lawyer

`district`, `taluka`, `village`, `survey number`.

**Do not guess the district or taluka.** There are 33,830 villages in Gujarat and
names repeat: unscoped, "Bodkee" and "Bodki" resolve to two *different* villages.
Guessing returns a real, valid-looking report for the wrong land. If you were only
given a village, ask which district and taluka — that question costs a message; a
wrong TSR costs a client relationship.

Survey numbers may look like `44`, `150/p1`, or `1300/p1/p2`. Pass them through
unchanged.

## Run it

```bash
cd $GUJTSR

# 1. fetch the land record  (~90s; goes through the residential proxy)
.venv/bin/python -m gujtsr fetch \
    --district "Bhavnagar" --taluka "Talaja" --village "Bodki" --survey "44" \
    --out-dir ./output

# 2. read the text layer  (deterministic, instant)
.venv/bin/python -m gujtsr text "./output/Survey No.44.pdf"

# 3. extract the structured JSON  — see below
# 4. render the document
.venv/bin/python -m gujtsr render extraction.json \
    --output "TSR_Bodki_44.docx" --client abrel_spv_2
```

Every command prints JSON on stdout and returns non-zero on failure. On
`{"success": false}` read the `error` string — it is written to be shown to the
lawyer as-is — and stop rather than retrying blindly. **A failed fetch is not
free:** it burns a session against a WAF that blocks by source IP, and the firm has
one shared proxy exit. Read `references/anyror-operations.md` in the repo before
retrying anything.

## Step 3 — the extraction

Read `$GUJTSR/references/extraction-rules.md` and follow it exactly. It holds the
firm's drafting conventions, corrected by the lawyer over many matters: entry-type
rules, the 21 formatting rules (including that ઘ transliterates as "Gh" not "Dh",
and the "Borewell-1" convention), per-type description patterns, and the
certification patterns. It also documents the exact JSON shape `render` expects.

Those rules are the product. Do not paraphrase them or substitute your own judgment
about how an entry should read.

If the repo's `EXTRACTION_BACKEND=claude` path is available you may instead run the
whole pipeline in one step, which uses the same rules from the Python constants:

```bash
.venv/bin/python -c "from tsr_generator import generate_tsr_from_pdf; ..."
```

Prefer the three-step path when you are the model doing the reading — it is one
process, not two, and you can see what you extracted.

## Before you hand it over

- Deliver it **marked DRAFT**, listing what needs checking.
- **Every "subsisting charge" finding needs a human check.** Encumbrance detection
  matches a loan to its release using a single `lender` field, and that produces
  known false positives — three appeared in the 2026-08-21 Miyani batch. Never
  report a live mortgage as fact.
- **Never invent a value.** A missing date or name is a bracketed placeholder you
  flag, not something to infer.
- Tenure phrasing varies between runs ("Old Tenure" vs "Old, Agricultural"). If it
  looks off, check the source PDF for જુની શરત rather than accepting the phrasing.
- Say which survey number and village the report covers, in English and Gujarati,
  so the lawyer can confirm you fetched the right land.

## When to stop and ask

- The village name is ambiguous, or you were not given a district and taluka.
- The fetch returns a WAF block page — do not retry; report it, because retrying
  deepens the block for everyone.
- AnyRoR is in its daily maintenance window (14:00–14:30 IST).
- The extraction is missing entries you can see in the PDF text.
