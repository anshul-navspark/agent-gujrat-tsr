---
name: gujarat-tsr-from-pdf
description: Use when someone already has a GUJARAT land record PDF and wants the Title Search Report drafted from it — "draft the TSR from this PDF", "turn this land record into a report", "I've got the 7/12, write it up". Reads the PDF, extracts the mutation entries and land details following the firm's drafting rules, and renders a draft TSR .docx on the firm letterhead. No portal access needed. If they do not have the PDF yet, use gujarat-tsr, which fetches it first. NOT for Rajasthan Jamabandi documents.
---

# Draft a TSR from a land record PDF

A land-record PDF in — a **draft** TSR `.docx` out. No AnyRoR access needed, so
none of the proxy or blocking concerns apply here.

**The output is a draft.** It goes out under Vijay Choudhary's letterhead and
signature; a lawyer checks and signs it. Never present it as verified title advice.

## Setup

```bash
bash scripts/ensure_env.sh
export GUJTSR=$HOME/gujrat_tsr_agent
```

## 1. Read the PDF

```bash
cd $GUJTSR
.venv/bin/python -m gujtsr text "/path/to/record.pdf"
```

Prints `{"success": true, "text": ..., "chars": N}`. A healthy Gujarat record is
roughly 15,000 characters of Gujarati. If `success` is false with "no text layer",
the file is a pure scan — say so; this path needs a text layer.

## 2. Extract the structured JSON

Read `$GUJTSR/references/extraction-rules.md` and follow it exactly.

That file is the firm's accumulated drafting practice, corrected by the lawyer
across many matters — entry-type rules, the 21 formatting rules (ઘ transliterates
as "Gh" not "Dh"; the "Borewell-1" convention; how areas are included), per-type
description patterns, and the certification patterns. It also documents the exact
JSON shape the renderer expects: `land_details`, `entry_numbers`, `mutation_entries`.

**Follow the rules as written.** They encode decisions a lawyer already made about
how these documents read. Do not paraphrase them or improve on them.

Write the JSON to a file.

## 3. Render

```bash
.venv/bin/python -m gujtsr render extraction.json \
    --output "TSR_<village>_<survey>.docx" --client abrel_spv_2
```

Rendering is fully deterministic — no model, no network. It builds the four tables,
the chain of title with real Word auto-numbering, and the findings table with live
Word cross-references back to the chain rows.

Bad input returns `{"success": false}` naming the offending field rather than a
traceback. An unknown client id lists the ids that do exist.

## Before you hand it over

- Mark it **DRAFT** and list what needs checking.
- **Check every "subsisting charge" finding against the PDF.** Encumbrance
  detection pairs a loan with its release using a single `lender` field, which
  produces known false positives — three appeared in the 2026-08-21 Miyani batch.
  A wrongly reported live mortgage is the most damaging error this skill can make.
- **Never invent a value.** Missing date, missing name, unreadable entry — bracketed
  placeholder, flagged, not inferred.
- Watch tenure phrasing; it varies between runs. Check the source for જુની શરત
  rather than trusting the wording.
- State the survey number and village the report covers so the lawyer can confirm
  it matches the land they asked about.
