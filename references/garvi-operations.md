# Operating Garvi without paying, and without ringing someone's phone

> **Runtime:** this repo requires **Python >= 3.11** — see `references/runtime.md`.
> Bare `python3` on the office Mac is 3.9.6; run tests with an explicit 3.11 path.


This is about the **free** public property search on `garvi.gujarat.gov.in`
(`frmPropertySearch_New.aspx`) — the Sub-Registrar side, registered deeds. It is
the companion to `anyror-operations.md`, which covers the revenue side. Read this
before changing how Garvi is called, and before telling a lawyer what the output
is.

Every claim below is tagged **VERIFIED** (checked here — against
`tests/fixtures/garvi/frmPropertySearch_New.html`, captured live 2026-08-28, or
against code in this repo) or **REPORTED** (recon, carried over from
`agent-mp/references/portal-operations.md` §4, not reproduced from this machine).
Do not promote a REPORTED claim to fact without checking it.

## Garvi issues the EC, not IORA

`iora.gujarat.gov.in` is the **revenue** portal — NA permission, premium, 135-D.
It does not hold registered deeds. Getting this backwards costs a day.

The confusion is the portal's own doing. Garvi's "Online services" menu labels
three links "(IORA)" and they do not go to the same place. **VERIFIED:**

| Nav label | Where it actually goes |
|---|---|
| Online certified **EC** (IORA) | `garvi.gujarat.gov.in/CitizenApp/Registration/FrmCitizenLogin_New.aspx` — Garvi's own citizen login |
| Online certified Index2 (IORA) | `iora.gujarat.gov.in/OnlineAppl.aspx` |
| Online certified document copy (IORA) | `iora.gujarat.gov.in/OnlineAppl.aspx` |

So the EC is applied for **inside Garvi**, despite its label; certified Index-2
and document copies really do route to IORA. Only the EC matters here.

## There is no free *certified* EC. There is a free search, and IGR names it.

The firm's instruction is explicit — online copies suffice, we do not want to pay.
That is satisfiable, with one limit that must never be blurred.

| Path | Cost | Sealed? | Use |
|---|---|---|---|
| `frmPropertySearch_New.aspx` — public property search | **free** | no | **this is the route** |
| Citizen-login EC application | paid, per application | yes | annexures only |

IGR's own FAQ points the public at the property search as the substitute for a paid
EC, and it returns **the same underlying Book-1 index data**, unsealed. **REPORTED**
— the free path has not yet been driven end to end from this machine.

The page says the same thing itself, in a red banner. **VERIFIED:**

> કોમ્પ્યુટર પ્રિન્ટ ફક્ત આપની જાણ માટે જ છે જેને સત્તાવાર નકલ તરીકે ગણવામાં આવશે નહી.
> આ વિગતો અંગે કોઈ પણ વધારાની માહિતી મેળવવી હોય તો જે તે સબ-રજીસ્ટ્રાર ઑફિસનો સંપર્ક કરવો.

("The computer print is for your information only and will not be treated as an
official copy. For any further detail, contact the Sub-Registrar office
concerned.") Ample for the analysis. **Not annexable.** Never call the output an
Encumbrance Certificate.

## The paid EC, and why the blocker is not the captcha

Fee is `125 + 10 × (EndYear − StartYear)` — a 30-year EC is **₹425**, not the ₹643
an earlier note recorded. **REPORTED.**

**There is no wallet.** Each application mints its own Cyber Treasury challan.
That, not the captcha and not the OTP, is what makes the paid path unautomatable:
a scraper would have to initiate a payment. It must not. Any build stops at the
prepared request and hands back to a human. **REPORTED.**

Commercially the two are not interchangeable either: the firm buys ECs from the
registry and bills them on as a pass-through — Vijay's quotation of 25-08-2026 to
Tata prices Gujarat DD per acre and says it "excludes the cost of Encumbrance
Certificate retrieval". **REPORTED.**

## The trap that produces a clean, wrong report

The index is keyed on the survey number **as written on the deed at the time of
registration**, not the number the parcel carries today. Search a renumbered
parcel under its present number and you get a short, tidy, **wrong** result — no
error, no warning, just an absence that reads as "no encumbrance". **REPORTED**,
and the same failure mode as MP's pre-renumbering record-room volumes.

Any run must carry the old numbers too, or **say in the output that it did not**.
Absence of a hit is not absence of an encumbrance.

## The page contract

All **VERIFIED** against `tests/fixtures/garvi/frmPropertySearch_New.html`
(74,932 bytes, captured 2026-08-28).

Not an SPA. ASP.NET WebForms: `<form method="post" action="./frmPropertySearch_New.aspx" id="form1">`,
and every dropdown change is a full `__doPostBack` with VIEWSTATE chaining.

Hidden state actually present: `__EVENTTARGET`, `__EVENTARGUMENT`, `__LASTFOCUS`,
`__VIEWSTATE`, `__VIEWSTATEGENERATOR`. **`__EVENTVALIDATION` is absent** — so the
server is not validating that a posted control value was one it rendered, which
makes the postback cascade forgiving. `__VIEWSTATE` must still be chained forward
from every response.

Control names are `ctl00$MainContent$<id>`; the matching DOM ids are
`MainContent_<id>`. The language switch is the one exception: `ctl00$ddlLanguage`
(`en-GB` / `gu-IN`), and it postbacks.

### Search modes

Five radios sharing the name `ctl00$MainContent$rb`:

| value | Label | Postback on click |
|---|---|---|
| `rbproperty` | Property Wise | no — it is `checked` by default |
| `rbparty` | Name Wise | yes |
| `rbdocumentdetails` | Document No / Document Year | yes |
| `rbdocdate` | Date Of Registration | yes |
| `rbdscandocdownload` | Download Scan Document | yes |

`rbproperty` is the mode in scope. **Party-name search exists** (`rbparty`), but
SRO *discovery* by party name was retired by the firm's own decision — the parcel
search is the product. Do not quietly reintroduce name-wise search as a fallback
when a survey number returns nothing; that changes what the finding means.

### The cascade

| Control | Options in the initial HTML |
|---|---|
| `cmbDistrict` | **35** — 34 districts + `---Select District---` |
| `cmbofc` (Sub-Registrar Office) | **0** — populated by the district postback |
| `ddlindex2village` (Index2 Village) | **0** — populated by the office postback |
| `ddlProperty` (Property/Land Type) | **6** — placeholder + AGRICULTURE, RESIDENTIAL, COMMERCIAL, INDUSTRIAL, NA-OPENLAND |
| `ddlsearchtype` (Search Type) | **5** — placeholder + TP./FP. Number, City Survey Number, Survey Number, Block Number |

`ddlsearchtype` postbacks; `ddlProperty` and `ddlindex2village` do not.

**The second level is the Sub-Registrar Office, not the taluka.** The 34 districts
are the same 34 as `anyror_hierarchy.json` (VAV-THARAD included), but below the
district the two portals diverge completely: AnyRoR goes district → taluka →
village, Garvi goes district → SRO → Index2 village, and the district *codes* are
Garvi's own. **`anyror_hierarchy.json` cannot fill Garvi's dropdowns.** The
taluka → SRO mapping does not exist anywhere in this repo; it has to come off the
postback.

### Free-text fields, captcha, OTP

- `txtsearchtypeno` — "TP Number/Survey Number/ValueZone". One box for all four
  search types; `ddlsearchtype` decides how it is read.
- `txtappName` — applicant name. Required by the form, not by the index.
- `txtmbNo` — mobile number. **This is the handset the OTP is sent to.** Whatever
  is typed here rings.
- Captcha image at `CaptchaImage.aspx?guid=<uuid>` (160×50), answer posted as
  `ctl00$MainContent$CaptchaControl1`, `size=5 maxlength=5` — so **5 characters**,
  confirming the recon. Refresh is a postback on `ImageButton1`.
- `BtnSendOTP` — "Send Verification Code(ચકાસણી કોડ મોકલો)".
- **The OTP entry box is not in the initial HTML.** The `<!-- OTP -->` and
  "Buttons Verify" containers ship empty; the input appears only after the
  `BtnSendOTP` postback. Do not look for it before then and conclude the page
  changed.
- A CERSAI search sits on the same page — `lnkCirsaisearch`, a postback link, not
  an external URL. Same-session central-registry check for security interests,
  free, and worth knowing exists.
- Results render into two hidden modal panels ("Party Details" / "Details") whose
  labelled rows are Order Date, Stamp Duty and Remarks. The grids are empty in the
  fixture because no search was run.

There is **no year control anywhere on this page** in its initial state — no
`select`, no text input. Whatever date range the paid EC offers belongs to the
citizen-login application, not here.

## The OTP, and the relay that swallows it silently

The free search is gated by the captcha **and** an SMS OTP to a real handset.
Two rules:

1. **Never request an OTP unattended.** It spends nothing, and it rings a real
   person's phone (Hemant's iPhone on the recon). A scraper may drive the session,
   the VIEWSTATE cascade and the captcha. It may not press Send Verification Code
   on its own.
2. **The relay on the firm's Mac is Rajasthan-shaped.** `OTP_KEYWORDS` in
   `~/work/apnakhata-captcha-extension/relay/src/server.ts:41` defaults to
   `ओटीपी,प्रतिलिपि` and `:142` requires **every** keyword (`.every(...)`, an AND).
   A Gujarat SMS contains neither Devanagari word, so it is accepted, logged
   `keywordMatch=false`, and then skipped by `/otp/status:188`, which only matches
   messages with `matchesKeyword`. It fails **silently**, looking exactly like the
   phone not firing — which once sent a session hunting the handset for two days
   while the Mac side was healthy throughout. **VERIFIED.**

The filter is env-overridable (`OTP_KEYWORD`), so the fix is configuration, not
code — but until it is actually made and tested against a real Gujarat message,
**a human reads the code off the phone.**

One more thing to check when that fix is attempted: `OTP_PATTERN` at
`server.ts:28` is `/\b\d{6}\b/`. If Garvi's code is not six digits, correcting the
keywords will not be enough. **Unverified — no Gujarat OTP has been observed.**

Garvi also advertises NIC's SANDES app for receiving its OTP SMSes. **VERIFIED**
on the page; untested as a delivery route, and it would move the code off the
shared SIM the relay watches.

## Pacing and blocking

Same discipline as AnyRoR, for the same reason: the office has **one exit IP**, and
a block stops everyone at once.

- **Serial only.** Never two searches in flight.
- **≥2s between requests**, and treat a full search (landing → district postback →
  office postback → captcha → OTP → submit) as one unit of work, not six.
- **On a block page, stop. Do not retry.** Retrying deepens the block for the whole
  firm. Report it and let a human decide.

A Barracuda WAF is present and has never fired. **REPORTED.** Because it has never
fired, there is no known block-page signature for Garvi — unlike AnyRoR, where the
~44 KB `Attack ID` page is a reliable tell. Treat *any* unexpected response that is
not the form (no `__VIEWSTATE`, empty `cmbDistrict`) as a possible block and stop.

The healthy landing page is ~75 KB with `cmbDistrict` carrying 35 options.
**VERIFIED** — that is the fixture.

## Still unsettled, and both matter

**Is the captcha field case-sensitive?** `CaptchaControl1` is `maxlength=5`, and the
model is prompted for uppercase, but nothing here has submitted one — the search
cannot complete without an OTP, so this cannot be settled yet. The reading is passed
through **exactly as read**, not upper-cased, deliberately: if Garvi ignores case the
choice is free; if it is case-sensitive and the image is genuinely mixed-case, forcing
uppercase would break a correct read. Faithful is never worse than normalised here.
Cost of being wrong is one wasted request, not a bad report. **UNVERIFIED.**

- **How far back does the online index reach?** Reported as 2001, never reproduced;
  the initial page ships no year control at all. If 2001 really is the floor, the
  1960s–90s Kutch deeds this firm works with are unverifiable online and much of
  the value evaporates. Settle it before anyone builds on this.
- **OTP granularity — per session or per query?** The difference between one OTP
  per TSR and one per parcel, i.e. between a workable tool and a phone that never
  stops buzzing. Undetermined.

Do not guess either of these in front of a lawyer.

## Never do this

- **Never present the free search output as an Encumbrance Certificate**, and never
  annex it. Unsealed index data informs the TSR; it is not a registry certificate.
- **Never initiate a payment.** No wallet, one challan per application; the build
  stops at the prepared request.
- **Never request an OTP unattended**, and never while the relay's keyword filter
  is still Rajasthan-shaped — the code will arrive and be invisible.
- **Never report "no encumbrance" from a single survey number.** Say which numbers
  were searched and which were not.
- **Never fill Garvi's dropdowns from `anyror_hierarchy.json`.** Different second
  level, different codes.

## Do not confuse this with the Rajasthan document

The Rajasthan `NON ENCUMBRANCE.pdf` is a **patwari** certificate issued "भूमि
रिकॉर्ड के आधार पर" — derived from the land record, so it corroborates the 7/12
rather than cross-checking it. A Gujarat EC is a **registry** search of Book-1 and
is an independent source. Both documents exist, under similar names, from
different issuers. Reading one and generalising to "the firm's ECs are not
registry searches" was an error made once already.
