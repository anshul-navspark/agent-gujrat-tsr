---
name: gujarat-encumbrance
description: Use to find what is registered against a piece of land in GUJARAT — "is there a mortgage on survey 44 in Bodki", "run an encumbrance check before we sign", "EC for this survey number", "what deeds are registered against this parcel", "any charge on this land", "check the Sub-Registrar index". Searches the Sub-Registrar's Book-1 index through Garvi's free public property search, for a district, Sub-Registrar office, village and survey number, and reports the registered documents found. What comes back is UNSEALED index data — ample for the analysis, but it is NOT the paid certified Encumbrance Certificate and cannot be annexed to a report. The search needs a captcha and an SMS OTP to a real handset, so a person has to be present; this is not an unattended job. For the AnyRoR land record or the TSR itself use gujarat-land-record or gujarat-tsr. NOT for Rajasthan — a Rajasthan "non-encumbrance certificate" is a patwari document off the land record, addressed by khasra/khata, from a different portal entirely. NOT for Madhya Pradesh.
---

# Gujarat encumbrance search

Village + survey number in, a list of what is registered against that parcel out —
from the **free** public property search on Garvi, the Sub-Registrar portal.

**This is not an Encumbrance Certificate, and you must never call it one.** There
is no free *certified* EC in Gujarat. What the free search returns is the same
underlying Book-1 index data, **unsealed**. The portal says so itself, in
Gujarati, on the search page:

> કોમ્પ્યુટર પ્રિન્ટ ફક્ત આપની જાણ માટે જ છે જેને સત્તાવાર નકલ તરીકે ગણવામાં આવશે નહી.
> *(The computer print is for your information only and will not be treated as an
> official copy.)*

That is ample to do the analysis and reason about charges. It **cannot be annexed
to a report**. If
the lawyer needs something to attach, they need the paid certified EC, which the
firm buys and bills on to the client as a pass-through — so the two are not
interchangeable commercially either.

Say this when you deliver, every time. It is the single most expensive thing to
get wrong here.

## Garvi, not IORA

`iora.gujarat.gov.in` is the **revenue** portal — NA permission, premium, 135-D.
Registered deeds live on Garvi. Garvi's own nav labels its certified-EC link
"(IORA)" while pointing back into Garvi's citizen login, which is exactly how this
gets confused. Getting it backwards costs a day.

## Before anything else

```bash
bash scripts/ensure_env.sh          # prints READY: <repo dir>, or fails with the reason
export GUJTSR=$HOME/gujrat_tsr_agent
```

If it fails, relay the reason verbatim and stop. Usual causes are a missing
`GITHUB_TOKEN` (the engine repo is private) or no `claude` CLI. None of these are
things to work around.

**Then read `$GUJTSR/references/garvi-operations.md`** before you touch the portal.
It holds the page contract, the block discipline, and the tagging that tells you
which claims have actually been checked and which are still recon.

## The command surface is landing separately

The Garvi client lives in `gujtsr.garvi` — an injectable transport plus an OTP
seam that **refuses unless you tell it a human is at the handset**. It is landing
separately from this skill, so this skill deliberately documents **no commands**:
any invented here would fail. Run `python -m gujtsr --help` and use the
subcommands that actually exist. Until one appears, describe the steps to the
lawyer and do the portal work by hand if it is urgent.

What the run looks like, in steps:

1. Fetch the search page, keep `__VIEWSTATE` and `__VIEWSTATEGENERATOR`.
2. Select the **district** — a postback that populates the Sub-Registrar office
   list.
3. Select the **Sub-Registrar office** — a postback that populates the Index2
   village list. Note this is an *SRO*, not a taluka: `anyror_hierarchy.json`
   cannot fill these dropdowns.
4. Select the **village**, the property/land type (AGRICULTURE for farm land),
   search type **Survey Number**, and enter the number.
5. Solve the 5-character captcha.
6. **Stop.** Ask a person before the OTP.
7. With the code, submit and read the result grid.

## What you need from the lawyer

`district`, `Sub-Registrar office` (or the taluka, so it can be matched), `village`,
`survey number` — and **any earlier survey numbers the parcel has carried**.

Do not guess the district or the office. Gujarat village names repeat — the
gujarat-tsr skill exists because "Bodkee" and "Bodki" are two different villages —
and a search scoped to the wrong office returns a real, empty-looking result rather
than an error.

## The trap that produces a clean, wrong report

**The index is keyed on the survey number as written on the deed at the time of
registration, not the number the parcel carries today.**

Search a renumbered parcel under its present number and you get a short, tidy,
**wrong** result. No error. No warning. Just an absence that reads as "no
encumbrance" — and that is the answer a lawyer will act on.

So:

- Ask whether the survey number has changed, and search the old numbers too.
- If you do not have them, **say so in the output, in the finding itself** — not in
  a footnote. "No registered document found against survey 44; the parcel's earlier
  survey numbers were not available and were not searched" is a usable answer.
  "No encumbrance" is not.
- Absence of a hit is never proof of absence of a charge.

## The OTP — why this skill stops and asks

The free search is gated by a captcha **and** an SMS OTP to a real handset. Whatever
mobile number is typed into the form is the phone that rings.

- **Never request an OTP unattended.** It spends nothing, but it rings a real
  person's phone. Everything up to Send Verification Code can be automated; that
  button is a human decision.
- **The firm's OTP relay currently swallows Gujarat codes silently.** Its keyword
  filter is Rajasthan-shaped — it defaults to the Devanagari wording
  `ओटीपी,प्रतिलिपि` and requires *every* keyword, so a Gujarat SMS arrives, is
  logged `keywordMatch=false`, and is invisible to the status endpoint. It looks
  exactly like the phone not firing. That mistake once burned two days hunting a
  handset while the Mac side was healthy the whole time.

**Until that filter is fixed and tested, a human supplies the code.** Do not build
a wait-loop against the relay for Gujarat; it will time out for the wrong reason.

So the honest shape of this skill today: drive everything up to the OTP, then stop
and ask. Tell the lawyer that is what will happen, before you start, so they know
to be near the phone.

## Rate discipline

One office exit IP; a block stops everyone.

- **Serial only.** Never two searches in flight.
- **≥2 seconds between requests.**
- **On a block page, stop — do not retry.** Retrying deepens the block for the
  whole firm. Report it and let a human decide. Garvi's WAF has never been seen to
  fire, so there is no known block signature: treat any response that is not the
  form (no `__VIEWSTATE`, empty district dropdown) as a possible block.

## Two things nobody has settled

Say so rather than guessing, because both change the answer:

- **How far back the online index reaches.** Reported as 2001, never reproduced.
  If 2001 is really the floor, 1960s–90s Kutch deeds are unverifiable this way —
  and the firm does Kutch work. If the search comes back thin on an old parcel,
  this is a candidate explanation, not evidence of a clean title.
- **Whether one OTP covers a session or every query.** The difference between one
  code per TSR and one per parcel. Warn the lawyer it may be several.

## Before you hand it over

- State plainly: **unsealed index data from Garvi's free property search, not a
  certified Encumbrance Certificate, not annexable.**
- Say exactly what was searched — district, Sub-Registrar office, village, every
  survey number tried — and what was not.
- Report each registered document as found: parties, date, document type, and the
  Order Date / Stamp Duty / Remarks the result panel gives. **Never infer a
  document type** the index does not state.
- A mortgage in the index is not a *subsisting* mortgage. Pairing a charge with its
  release is a human judgment here — the gujarat-tsr skill's automatic pairing
  produces known false positives, and this data is thinner still. Report what is
  registered; let the lawyer conclude.
- **Never invent a value.** A missing party name or date is a bracketed placeholder
  you flag, not something to fill in.

## When to stop and ask

- The parcel may have been renumbered and you do not have the old numbers.
- The survey returns nothing. Report the absence with its caveats; do not go
  hunting by party name instead — SRO discovery by party name was retired by the
  firm's own decision, and it answers a different question.
- Someone asks for a certified EC, or for something they can annex. That is the
  paid path: each application mints its own Cyber Treasury challan, there is no
  wallet, and **you must never initiate a payment**. Prepare the application
  details and hand back. Fee is `125 + 10 × (EndYear − StartYear)` — about ₹425 for
  30 years.
- An OTP is needed and nobody is at the handset.
- A block page appears, or anything that is not the search form comes back.
