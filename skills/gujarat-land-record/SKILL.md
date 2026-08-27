---
name: gujarat-land-record
description: Use to get the raw GUJARAT land record PDF itself rather than a report — "get me the 7/12 for survey 44 in Bodki", "pull the AnyRoR record", "download the land record", "I need the original document". Fetches the Integrated Survey No. Details record (7/12 + 8-A + entry details) from AnyRoR for a district, taluka, village and survey number and saves it as a PDF. If they want a Title Search Report drafted from it, use gujarat-tsr instead. NOT for Rajasthan records, which come from a different portal.
---

# Fetch a Gujarat land record

District, taluka, village and survey number in — the AnyRoR record as a PDF out.

**Read `references/anyror-operations.md` in the repo before you retry anything.**
AnyRoR blocks by source IP, the firm has one residential proxy exit, and a block
takes fetching down for everyone. A careless retry loop is the single most
damaging thing this skill can do.

## Setup

```bash
bash scripts/ensure_env.sh          # prints READY: <repo dir>, or fails with the reason
export GUJTSR=$HOME/gujrat_tsr_agent
```

Relay any failure verbatim and stop.

## Fetch

```bash
cd $GUJTSR
.venv/bin/python -m gujtsr fetch \
    --district "Bhavnagar" --taluka "Talaja" --village "Bodki" --survey "44" \
    --out-dir ./output
```

Takes roughly 90 seconds. Prints JSON: on success `output_path`, `size_bytes`, and
a `resolved` block showing the Gujarati names it actually used. **Show the lawyer
that `resolved` block** — it is how they confirm you fetched the right land.

Names may be English or Gujarati. Survey numbers stay as written: `44`, `150/p1`,
`1300/p1/p2`.

## Getting the location right matters more than it looks

There are 33,830 villages in Gujarat and the names repeat. Resolved without a
district and taluka, "Bodkee" lands on village code 040 and "Bodki" on 094 — two
different places, both returning a real, plausible PDF. **Never guess a district
or taluka.** Ask.

An unknown name fails instantly, before any network call, and comes back with
`did_you_mean` suggestions from the hierarchy. That costs nothing — offer the
suggestions and let the lawyer choose.

## When a fetch fails

Read the `error` string; it is written to be shown as-is.

- **WAF block page** ("Attack ID", ~44 KB, empty dropdowns) — **stop**. Do not
  retry. Report it. Retrying deepens the block for the whole firm.
- **`ProxyError` / read timeout** — transient; the asocks exit drops connections
  occasionally. One retry after a pause is reasonable.
- **`taluka '...' not found`** — a name problem, not a portal problem. Fix the
  name; do not re-run hoping.
- **Daily maintenance, 14:00–14:30 IST** — AnyRoR is down. Say so and wait.

Leave **≥60 seconds between fetches**. Three sessions in six minutes tripped the
WAF once already.

## What you get

The "Integrated Survey No. Details" record — 7/12, 8-A and the entry details in one
document, in Gujarati. Note for expectations: **khata-based lookup is not
implemented**, only survey number. It is an official-format printout but not a
certified copy; AnyRoR says so on the page itself.
