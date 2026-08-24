# Project Journal

> **Purpose:** Avoid repeating mistakes, document the developer's coding approach so future Claude sessions know what's coming next, and surface alternative paths when patterns recur.
>
> **Protocol:**
> 1. **At session start** — Claude reads this file, then formalizes any "Active Draft" content into a new dated entry under "Sessions" using `git log` since the last entry. Clear the draft afterward.
> 2. **During session** — Claude appends bullets to "Active Draft" as milestones are hit (commits landed, approaches abandoned, decisions made, surprising results).
> 3. **Monthly compactification** — A scheduled remote agent opens a PR proposing which entries to keep verbatim, which to compress, and which lessons to promote to the "Lessons Compendium." User must review and merge — agent never auto-applies.
>
> **Why session-start, not session-end:** sessions can close abruptly. Git log + the on-disk Active Draft survive crashes; an end-of-session save does not.

---

## Active Draft

<!-- Claude: append milestone bullets here during the session. The next session
     formalizes them into a dated entry below and clears this section. -->

**2026-08-21 — Miyani (Porbandar) 1300 paiki batch: 1 of 3 delivered, IP burned on #2:**
- Task from a WhatsApp note: Porbandar / Porbandar / Miyani (`મીયાણી - 015`), surveys
  `1300/P1/P1`, `1300/P2`, `1300/P1/P2` — three NESTED-paiki surveys.
- **`_survey_candidate_texts` (`http_fetch.py:117`) does not handle nested paiki.** Its regex
  is `^(\d+)/?p(\d+)$` — single level only. So `1300/p1/p1` generated no correct candidate
  and the fetch failed. Live dropdown (1731 options) spells them
  **`1300/p૧/p૧`, `1300/p૧/p૨`, `1300/p૨`** — Latin base + Latin `p` + **Gujarati** paiki
  digits, which is exactly the pattern the single-level branch builds but the nested case
  never reaches. Passing the exact option text as `survey_number` works. **Candidate fix:
  generalise the paiki regex to N levels.**
- **Added `ANYROR_SELENIUM_FALLBACK` guard (`anyror/scraper.py`).** Default `true` (behaviour
  unchanged); set `false` to make `fetch_land_record` return an error instead of falling
  through to Selenium. Earned its keep immediately — the nested-paiki miss would otherwise
  have launched Selenium and drawn a WAF Attack ID. Recommend making `false` the default.
- **Probe technique worth reusing:** monkeypatch `hf._options` to capture the `ddlSurveyNo`
  list, then call `fetch_record_html` with a deliberately unmatchable survey and `attempts=1`.
  One walk, no captcha, no record generation — dumps all options for a village.
- **Survey 1 delivered**: `~/Downloads/TSR_Miyani_1300_2026-08-21/survey_1300p1p1/` — 11 entries,
  legacy layout (4 tables, 23×3 findings), 214s end-to-end on Opus 5 / high.
- **Run stopped after survey 2 returned a TLS reset** (`SSL: UNEXPECTED_EOF_WHILE_READING`) on
  the very first GET — WAF IP-block signature. Per standing rule, stopped rather than retried.
  Total AnyRoR sessions before the block: 1 failed match + 1 probe + 1 successful fetch = 3,
  paced 60s. **3 sessions in ~6 min was enough to trip it**, which is tighter than the pacing
  memory assumes — worth revisiting the 60s figure.
- **RESOLVED same session — Indian residential proxy defeats the WAF block.** Anshul supplied
  a residential proxy; egress verified as **103.172.154.114, Surat, Gujarat, AS149249 Ruchi
  Communication**. Added `ANYROR_PROXY` support to `http_fetch._session()` (AnyRoR traffic
  only; Gemini captcha calls still go direct; credentials read from env, never the repo).
  Surveys 2 and 3 then completed **first try, HTTP 200, ~210s each** on the same burned local
  machine. This is the first proxy that has worked — the 2026-07 failures were free
  *datacenter* proxies, which got the WAF page; a *residential* ISP IP passes.
  **Now a standing instruction: route every AnyRoR fetch through it, not just after a block.**
- **Proxy verification method matters:** a curl GET through a bad proxy returns a false 200.
  Test against AnyRoR itself — good page ≈36KB with 34 populated district options; WAF page
  ≈44KB with `selects=[]` / "Attack ID".
- **All 3 TSRs delivered** to `~/Downloads/TSR_Miyani_1300_2026-08-21/`
  (`survey_1300p1p1` 13 entry rows, `survey_1300p1p2` 11, `survey_1300p2` 11). All legacy
  layout (4 tables, 23×3 findings), correct per-survey ref lines. **All three report a
  subsisting charge** — 4888 for both 1300/p૧/* and 4907 for 1300/p૨ — which needs the usual
  human check against the known single-`lender`-field false-positive bug.
- **SECURITY (flagged, not actioned): `.env` is git-TRACKED** despite `.gitignore` line 23 —
  it was committed before the rule existed. A live `GEMINI_API_KEY=AIza…` is in committed
  history. Proxy credentials therefore kept OUT of `.env`. Needs key rotation + history
  purge; Anshul's call.
- **Cloud Run (`asia-south1`) is ALIVE again** — `/health` 200 (was 503 crash-on-boot in July).
  A `/process-record` test returned `Captcha could not be solved`, which is
  **`scraper.py:212` — the Selenium path**, so http_fetch failed there first for an unknown
  reason (that deploy predates the guard). NOT yet evidence that a Mumbai GCP IP can reach
  AnyRoR; needs Cloud Run logs to tell a WAF page from a dead `GEMINI_API_KEY`. **Open lead**
  — if http_fetch works from asia-south1, it solves the IP-burn problem permanently.

**2026-08-24 — Proxy path re-verified end-to-end; credentials finally persisted to disk:**
- Anshul asked whether the AnyRoR issue is fixed and for a live test scrape, and challenged
  whether past sessions were at fault for "not going to the VPS". **Journal check: there is
  no VPS** — 2026-08-10 already confirmed it (no ssh config, Oracle Mumbai still unbuilt) and
  the paid *residential proxy* only arrived 2026-08-21, i.e. after the two burned batches.
  The 08-10 burn was genuinely our fault (4s spacing vs the journal's own 60s rule); 07-28
  predates the lesson; 08-21 was correctly paced and the WAF simply bit at 3 sessions/6 min.
- **Root cause of the "proxy keeps going unused" feeling: it was never stored anywhere.**
  It lived only in chat + the memory file, so every session had to re-ask. Recovered the
  credential from an old session transcript, confirmed it matches memory byte-for-byte, and
  with Anshul's explicit permission wrote it to **`.env.local` (git-ignored)** — deliberately
  NOT `.env`, which is git-tracked and already leaks a `GEMINI_API_KEY`.
- **Proxy is alive and unblocked**: same sticky exit `103.172.154.114` (Surat). Landing page
  36,115 bytes with **34 populated districts** = the known-good signature (WAF page ≈44KB /
  Attack ID). Fetched **Bodkee/Talaja/Bhavnagar survey 44** in **83s**, single attempt, no
  retry: 16-page PDF, 15,489 chars of clean Gujarati text, correct UPIN.
- **Two proxy gotchas, both now in memory:** (1) only gateway **port 443** authenticates —
  8080 and 12321 are open but return `407`, which reads like a dead subscription and isn't;
  (2) the **HTTPS CONNECT tunnel cold-starts >10s** then settles at ~2s, so the module's 6s
  `ANYROR_CONNECT_TIMEOUT` was failing whole attempts. Fixed: the default is now **30s
  whenever `ANYROR_PROXY` is set**, 6s otherwise (the NAT64 fast-fail case still holds).
- **New bug surfaced (not fixed):** `fetch_record_pdf` cannot resolve an **ASCII district
  name** — `ddlDistrict` carries Gujarati only and, unlike taluka/village, has no ASCII
  fallback, so "Bhavnagar" dies with "district not found". Pass code `14` or `ભાવનગર`.
  Production is unaffected (the scraper passes translated Gujarati), but it is a trap for
  any direct caller and the docstring claims ASCII works.
- **Fixed all three, TDD (tests first, watched them fail, then implemented):** 13 new tests
  in `tests/test_http_fetch.py` (28 in that file, **438 in the suite, all passing**).
  1. **Nested paiki generalised to N levels** — regex is now
     `^(\d+)((?:\s*/?\s*p(?:k)?\s*\d+)+)$`, and candidates are built by applying one
     separator across every level. Verified it emits the exact live spellings
     `1300/p૧/p૧`, `1300/p૧/p૨`, `1300/p૨`; the single-level cases (`24p૧`, `48/p૪`) have a
     regression guard. Spelled-out forms (` પૈકી `) stay one-level-only.
  2. **District resolution extracted to `_resolve_district(dopts, district)`** and given an
     ASCII fallback via `translate_to_gujarati(..., context='district')`. Accepts code,
     Gujarati, and ASCII (case-insensitive); returns None for unknown, and the blank
     "Select" option can no longer be chosen (the old `wanted in text` test matched the
     empty string against every option).
  3. **`_default_connect_timeout(env)`** — 30s when `ANYROR_PROXY` is set, 6s direct, and an
     explicit `ANYROR_CONNECT_TIMEOUT` always wins.
- Writing the tests exposed a fragility worth keeping in mind: `_resolve_district` reached for
  `self.log`, which does not exist on the `__new__`-constructed fixture the test file uses to
  avoid a Gemini client. Now falls back to the module logger.
- Committed to `feat/old-entry-chain-phase0` → **PR #10**. Deliberately left OUT of the commit:
  `.env` (tracked + carries secrets) and `anyror_hierarchy.json` (auto-learned spelling
  variations from earlier sessions, unrelated to this change).
- **Note for whoever merges:** `anyror/http_fetch.py` does not exist on `main` at all — the
  entire browser-free fetch is still unmerged (PR #9, open since 2026-07-22). Every scraper
  fix since then is stacked on unmerged work. **Five PRs are open** (#6–#10); this is the
  backlog to clear before the scraper story is really "fixed" on main.

**2026-08-21 (later) — Old-entry chain for Miyani 1300: Mittali already appended it; verified:**
- Task: add the pre-digital chain entries to the three 1300 TSRs from two handwritten photos
  (`~/Downloads/WhatsApp Image 2026-08-21 at 13.04.12/13.04.37.jpeg`) covering **old S.No. 431**
  (and 346/2P). Checked OneDrive first — **Mittali had already done all three** and uploaded
  `1300_p1_p1 / 1300_p1_p2 / 1300_p2 - complete.docx` (15:34–15:58). No agent edit needed.
- She prepended **7 old entries** — 260, 1396, 1901, 2130, 2461, 2875, 3159 — ahead of 3659.
  The blocks are **byte-identical across all three files** (per-entry md5 match), so she wrote
  them once and pasted. Chain length went 13→20 (p1p1), 11→18 (p1p2), 11→18 (p2).
- **Verified entry-by-entry against the photos: 6 of 7 are faithful**, including the details
  the extractor normally drops — death dates (Duda Rajshi 02/05/2007, Raja Rajshi 16/10/2008),
  full heir lists (6 and 7 names), "– Widow" on Rupiben, and every certification date.
- **Two things to check before this goes out:**
  1. **Entry number 260 vs 207.** AnyRoR's own old-entry index on the Village Form 7 she
     uploaded reads `નોંધ નંબરો: ૨૦૭,૧૩૯૬,૧૯૦૧,૨૧૩૦,૨૪૬૧,૨૮૭૫` + other-rights `૩૧૫૯` — i.e.
     **207**, where the note and all three TSRs say **260**. Every other number matches the
     index exactly. Unresolved: she replaced the Form 7 PDF with the finished DOCX, so the
     source is gone from OneDrive *and* her PC; can't re-read it.
  2. **Entry 2875 drops the area allocations.** The note gives Jeeva Duda 431p = 3-06-21 Hec
     and Natha + Naga 431p = 1-53-11 Hec; her text names the 10 relinquishers and the 3
     beneficiaries but omits the areas. Her own convention (18f352f) renders partition
     allocations as a nested table — inconsistent here.
- **Structural finding — the old-entry index is NOT in what we scrape.** `http_fetch` pulls
  `RECORD_TYPE_VALUE = "8"` ("Integrated Survey No Details"); the `જૂના સર્વે નંબર ને લગત
  નોંધ નંબરો` header block lives on **Village Form 7 (ગામ નમૂનો ૭)**, a different record type.
  Confirmed: all 3 of our scraped `Original_*.pdf` lack the line; her Form 7 print has it.
  **This is the missing input for the whole `feat/old-entry-chain-phase0` project** — fetching
  Form 7 would give the authoritative old-entry number list for free, turning the handwritten
  transcription into a verify-against-index step instead of a from-scratch one. Next action:
  probe `drpLandRecord` for the Form 7 option value.
- Also noted in her edits: `Jiva` → **`Jeeva`** throughout p1p1, and 4692/4834/4835/4841
  trimmed (khata numbers in parens and "(market value Rs. …)" removed) — same trimming
  convention seen in the Bodki batch.

**2026-08-12 — Picked a demo survey for tomorrow; found the cache was hiding a fixed bug:**
- Task: choose a khasra with full documents for a demo. Scored candidates with
  `scripts/eval_chain_vs_truth.py` (chain vs AnyRoR's authoritative Entry Details index)
  plus a table-level diff against the lawyer's delivered TSRs. Rebuilt the whole comparison
  from banked cache PDFs — **no AnyRoR traffic at all**, so zero WAF/pacing risk.
- **Bodki (Talaja, Bhavnagar) is the best-documented site** (Form 7, Form 12, EC Reports,
  delivered TSRs in Word+PDF; 7 surveys banked locally). But none of the 7 is demo-clean:
  44 / 44p1 / 45-4p2 emit a **false "charge subsisting"** (the known co-op-lender /
  single-`lender`-field bug); 56p1/56p2 claim "clear" where the lawyer wrote **not clear**;
  56p1 also has phantom 889 + 5 missing entries. Only 57p1/57p3 conclude correctly, and
  57p1 renders 7 of 12 entries as boilerplate.
- **User overrode the shortlist and picked Kutch/Abdasa/Trambo 150.** Two discoveries:
  1. The cached record labelled survey `150` is actually **૧૫૦/પૈકી ૧ (150p1)** — a live
     instance of `ISSUES.md` #1 (silent first-dropdown-option fallback). Lucky here, since
     150p1 is one of the three Trambo surveys with a delivered TSR; it could as easily have
     produced a confidently wrong report for a different survey. Worth fixing.
  2. **The 2026-06-09 cached TSR was bad — current code is not.** Cached run fabricated
     entries 105/160/223 (khata numbers lifted as entry numbers) and dropped **243**, the
     1968 sale that is the root of title. Regenerating from the same banked PDF with today's
     code gives **5/5 entries, 0 phantom, 0 missing** — exactly the lawyer's chain
     (125, 243, 721, 905, 983), with 721/905/983 narratives near-verbatim and the same
     "clear and marketable" conclusion. 150p1 has **no loan entries**, so the encumbrance
     bug cannot fire.
  - **Lesson: never judge extraction quality from the local cache.** TTL is ~never-expire,
    so a cached DOCX can predate months of fixes and silently misrepresent current quality.
    Regenerate with `skip_cache` before any eval or demo decision.
- `python -m tsr_generator` is **broken** — `tsr_generator/__main__.py` imports
  `tsr_generator.utils.logging_utils`, which does not exist. Used `generate_tsr_from_pdf` +
  `_build_request_metadata_for_client` directly instead (same path as 07-31).
- Built `~/Downloads/demo_trambo_150p1/` — a 20-page merged demo pack (source RoR →
  agent-generated TSR → lawyer-delivered TSR, with section dividers).

**2026-08-12 (later) — Regenerated 150p1 from the demo pack; found the phantom-entry root cause:**
- Generated the TSR from `~/Downloads/demo/Gujarat/Trambo-150p1/AnyRoR_Trambo_150p1.pdf`
  (byte-identical to banked cache `726c6a0c…/original.pdf` — verified with `cmp`). No AnyRoR
  traffic. Delivered `~/Downloads/TSR_Kutch_Abdasa_Trambo_150p1_2026-08-12.docx`.
- **First run came out defective**: chain 125 / **160** / **223** / 721 / 905 / 983 — the two
  khata numbers promoted to entries and **243 (the 1968 sale, root of title) dropped**. Same
  failure this morning's note attributed to the stale June cache. Second run from the identical
  input was correct (125, 243, 721, 905, 983), so it is **intermittent, not fixed**.
- **Root cause is `_identify_entry_numbers_fast` (`unified_extractor.py:503`), not the model.**
  The hint it feeds the prompt for this record is `['125','૧૬૦','૨૨૩','721','905','983']` —
  poisoned and incomplete, for two independent reasons:
  1. `\d{3,4}` is Unicode-aware, so **Gujarati digits match**; ખાતા નંબર ૧૬૦/૨૨૩ become
     candidate entry numbers. The context filter only looks for ASCII `khata`/`survey`/…,
     which never appear in Gujarati text, so it never fires. Fix: `[0-9]{3,4}` / `re.ASCII`.
  2. The pattern **consumes** its surrounding separator, and `finditer` cannot overlap, so in
     the index run `125\n243\n721\n905\n983` every second number is skipped — 243 and 905
     are both lost (905 is recovered later from its narrative row; 243 has no narrative in the
     record, so it disappears). Fix: lookarounds `(?<![0-9])(\d{3,4})(?![0-9])`.
- Direct extractor called 3× on the same text returned the correct 5 entries each time, so the
  model usually overrides the bad hint — which is why this reads as flaky rather than broken.
  **Verify the chain against the record's Entry Details index on every run until this is fixed.**
- `demo/README.md` (the pack's, in `~/Downloads/demo`) lists Trambo as **Taluka Bhuj**; the
  record says **Abdasa**. Pack text needs correcting before the demo.

**2026-08-10 — Visavada (Porbandar) surveys 61-64; format drift traced to a doc profile:**
- Anshul flagged that TSRs had been carrying "extra info" for ~15 days and supplied
  `~/Downloads/1772.docx` (Visavada survey 1772, delivered Dec 2025) as the target format,
  guessing Opus 5 was the cause. **It was not the model — it was template code.**
  `tsr_document.py` / `findings.py` branch on `land_details["tsr_profile"]`, default
  `final_sample_v1`, added 2026-07-28 in `18f352f`. The delivered format is the *legacy*
  branch. Diffs: intro gains "as per above subject reference"/"(Gujarat)"/trailing "-";
  recipient gains CIN + Kind Attn + Re: lines; findings 5/18 swap "point no. 3 of table
  no. 4" for a live REF field; tabs + curly apostrophes in headers. Fix was one metadata
  key, not a prompt change. Memory: `project-tsr-document-profile`.
- Added `tsr_profile` to the `request_metadata` whitelist in `tsr_generator_optimized.py`
  so the profile is selectable per request; **repo default is still `final_sample_v1`** —
  flipping it is an open decision for Anshul (legacy hardcodes the ABREL recipient and
  ignores `clients.json`, so it is not a free switch).
- Also patched the legacy area format to the delivered style
  (`0-52-72 Hectare i.e., (05272 Sq. mts)`, zero-padded, lowercase "mts").
- **Repeated the 2026-07-28 pacing mistake and lost the batch.** Fetch script used
  `time.sleep(4)` between records against the journal's own "use ~60s" lesson, and
  `fetch_record_html` defaults to `attempts=10`. Survey 61 landed 11:50; TLS reset by
  11:51; ~24 further requests fired into the block before I killed it. Signature was
  `SSLError(SSLEOFError)` = real WAF IP block, not the NAT64 timeout. Memory:
  `feedback-anyror-pacing-60s`.
- **Recovered without touching AnyRoR again:** Anshul hand-saved the four record pages
  from his browser as `.mht`. Chrome reads MHTML natively, so
  `--headless --print-to-pdf` on the `.mht` produced clean 9-12 page PDFs with an intact
  Gujarati text layer — a genuine WAF-free path for any record a human can load in a
  browser. Worth keeping in the toolkit.
- Confirmed there is **no VPS** (checked ssh config, repo, journal) — the Oracle Cloud
  Mumbai microservice is still an unbuilt "Next" item. Cloud Run is down *and* GCP-blocked;
  WARP egress is WAF-blocked; free proxies return the block page. Only a fresh Indian
  residential IP works. A paid Indian *residential* proxy is untested and plausible.
- Delivered `~/Downloads/{61,62,63,64}.docx`. Old-survey cross-check vs source: 109/2,
  109/3, 110, 113 — all correct. Survey 61's tenure came back as "Old, Agricultural" on a
  re-run (LLM variance; the `'old tenure' in nature` check fell through to the raw value),
  corrected to "Old Tenure / Agricultural Use" after verifying જુ ની શરત (જુ .શ) in the
  source PDF. **Extraction phrasing varies run-to-run — the tenure branch needs a
  normalizer, not an exact-substring match.**

**2026-07-28 — Bodki (Talaja, Bhavnagar) TSR batch; scrape/extract decoupled:**
- Identified the "Bodki" site from OneDrive TSRs (`2023 GUJRAT aditya Birla/TSR of
  Bhavnagar -Solar/Bodki 4dec 2023/`): Village Bodki, Taluka Talaja, District Bhavnagar,
  client ABREL SPV 2. Cross-checked against `anyror_hierarchy.json` → `બોડકી - 094`.
- **Portal spells the village "Bodkee", the lawyer's TSRs spell it "Bodki".** Passing
  "Bodki" → HTTP 400 with a correct "did you mean: Bodkee" hint (deterministic matcher
  did its job — no silent wrong-village fetch). Candidate fix: add the spelling variant.
- **Probe-before-batch pattern (new, worth keeping):** dumped the live survey dropdown
  (664 options) via steps 1–4 of the postback walk — no captcha, no submit — before
  generating anything. Caught that requested survey `56` does **not** exist as a plain
  number (only `56p૧`/`56p૨`), and confirmed `44`, `44/p૧`, `45/૪p૨`, `57p૧`, `57p૩`.
  Cheap insurance against wrong-record TSRs; probe script kept in the session scratchpad.
- Confirmed `_survey_candidate_texts` would NOT have matched `45/4p2` (its paiki regex
  assumes a plain integer base, so `45/4` + `p2` falls through) — but http_fetch fails
  loudly with the option list rather than silently picking option 0, so it surfaced.
  The slash-insensitive fallback is what actually rescues this case.
- Per Anshul: **decoupled scraping from extraction** — scrape-only pass seeds the local
  cache under the same key `/process-record` computes (verified: survey 44 resolved to the
  identical key `3ab75d34…` from both paths), so the later TSR pass skips the WAF entirely.
- Cloud Run deployment still down: `/health` → **500** (was 503 on 2026-07-22). Local
  http_fetch is currently the only working path; it walked AnyRoR fine from this machine.
- **WAF IP-block hit mid-batch** (~11:11, after ~4 dropdown walks in 7 min): survey 44
  completed at 11:09, then every connection from 49.36.238.109 got TLS-reset (curl exit 35).
  Cloudflare is a **known dead end** here (journal 2026-07-22: WARP `104.28.x` is WAF-blocked;
  `warp-cli` not installed, and `cloudflared` is a tunnel client that can't change egress).
  Pacing lesson: 3s between records is too aggressive; use ~60s.
- **BIG FIND — `pypdf` mis-decodes Gujarati; it is NOT model-drop.** Chasing a "use
  screenshots instead" idea, rendered the survey-44 PDF to 200-DPI PNG and read it with
  Opus 5 vision. The vision read was *cleaner than the PDF text layer*, which led to
  measuring three extractors on the identical file (16 pages):
  | extractor | correct `ો` | decomposed `ાે` | mid-word gaps |
  |---|---|---|---|
  | **pypdf (in use)** | **0** | 227 | **587** |
  | PyMuPDF | 242 | 0 | 10 |
  | poppler `pdftotext` | 242 | 0 | 88 |
  pypdf drops conjuncts/reph outright (`જીલ્લો`→`જી ાે`, `દ્વારા`→` ારા`, `ગ્રામ્ય`→` ામ્ય`)
  and **corrupts holder names** (`હિતેષભાઈ`→`હતેષભાઈ`). poppler reads all of them correctly;
  PyMuPDF is close but doubles `ા` in ર-conjuncts. The PDF is fine — pypdf's char mapping isn't.
- Consequence: **every locally generated TSR was extracted from mangled text**, and the
  2026-05 "extraction gaps = model-drop" diagnosis is confounded. Any model/prompt eval
  predating this needs re-baselining. Memory `project_anyror_pdfs_are_text` corrected.
- Proposed fix (NOT yet applied, awaiting Anshul): swap `pypdf` → poppler `pdftotext` in
  `tsr_generator/utils/pdf_utils.py::_extract_text_cached`, pypdf as fallback, then
  regenerate survey 44 with `skip_cache=true`.
- Also found: `tsr_generator/__main__.py:28` passes `args.output_path` but argparse defines
  `output` → the CLI documented in CLAUDE.md crashes with `AttributeError` on every run,
  and it imports the original 3-call Gemini path, bypassing the Claude/Opus backend.
- **Fix landed on `main`:** `3563a28` (pdftotext → PyMuPDF → pypdf chain + 9 tests) and
  `302f6a6` (poppler-utils in `Dockerfile.optimized` — cloudbuild builds *that*, not
  `Dockerfile`, so the first commit alone would never have reached the deployed image).
  Merged into the working branch as `fd54ccb`. **Both still unpushed** (push → Cloud Run
  auto-deploy, wanted Anshul's go-ahead).
- **`main` is not a runnable configuration.** It lacks `http_fetch` (PR #9) *and* the
  multi-client cache (PR #8) — its cache looks for `tsr.docx`, not `docx_{client_id}.docx`.
  Switching the tree to main and running the API made it miss the cached PDF and fall back
  to Selenium → chromedriver → WAF 500. Also: main's 3 failing tests are already fixed on
  the PR branches (feature branch: **389 passed, 0 failed**). Argument for merging #8/#9.
- **Regenerated survey 44 off the cached PDF** (deleted only `docx_*.docx`, kept
  `original.pdf` → forces DOCX regen with no scrape; `skip_cache=true` would have been
  WRONG, it bypasses the PDF cache too and would have triggered a doomed scrape).
- **Old-vs-new TSR diff is MIXED, not a clean win** — 8 of 56 blocks differ. Better: entry
  539 now isolates the one relevant loan instead of dumping 19 unrelated farmers; entry 543
  numbering fixed. Worse: entry 89 became an empty stub (`Entry No. 89 Dated :`), entries
  1351/1352 **dropped the certificate dates**, 543/1142 dropped khata numbers in parens,
  and 1353 turned "affidavits before the Notary" (source: `નોટરી રૂબરૂના સોગંદનામા મુજબ`)
  into "their consent" — the OLD wording was the accurate one there.
  **Lesson: the fix corrects the INPUT (measured, certain); it does NOT follow that the
  OUTPUT improves.** A single before/after run changes two variables at once (input text +
  LLM sampling) and cannot separate them. Needs a controlled repeat-run comparison plus
  lawyer review. The dropped certificate dates / khata numbers look like a prompt gap
  independent of this fix.
- IP block never cleared: 12 checks over ~55 min, all TLS-reset. Stopped polling.
- **Afternoon: all 7 Bodki TSRs delivered to OneDrive**; Mittali reviewed and marked 5
  `- complete` (44, 44-p1, 45-4p2, 57p1, 57p3) and sent them to the client. 56p1/56p2
  await her review. Her PC reachable over SSH as host `mittali` (192.168.29.69).
- **Learnings encoded from her edits** (commit `18f352f`, 406 tests): INHERITANCE drops
  its supporting-documents closing sentence (PARTITION keeps its own); no heir ages or
  death-certificate numbers but keep the exact death date; `નિસંતાન` MUST survive as
  "(Childless)"; omnibus *correction orders* trim to the subject survey (but bulk *loan*
  lists keep every name — confirmed by her keeping entry 539's 19 names verbatim);
  "affidavits before the Notary" not "their consent"; release-certificate dates never
  stated in any phrasing; partition allocations render as a nested table; full month name
  in the Ref date.
- **Empty-client-field bug fixed across FOUR layers** (`core/clients.py`, `api/server.py`,
  `tsr_generator_optimized.py`, `tsr_document.py`): an explicitly empty field in
  clients.json was indistinguishable from a missing one, so hardcoded ABREL defaults were
  silently reinstated. NO client could suppress the CIN / Kind Attn / Re: lines. Not
  Bodki-specific — it would have put ABREL's CIN on every new client's report.
- **Measured: 49% of chain entries are index-only** (25 of 51 across the 7 reports) — they
  appear in AnyRoR's "Entry Details" index with no detail row, because they predate the
  digital record. Mittali hand-types these from the old scanned Village Form 7/12.
  Per Anshul (2026-07-28): this is by design, NOT a gap to close; do not chase it.
- **Cross-reference caveat:** findings 5/18 compute "point N in table no. 3" from the
  charge entries' chain positions — correct at generation time in all 7 files. It goes
  stale only when the lawyer INSERTS a chain row (she added entry 82 to 57p3, shifting
  the charges from positions 2-3 to 3-4). Not a generator bug; parked with her.
- **Process lessons:** (1) a running uvicorn serves STALE code — always restart after a
  prompt/template edit, this silently generated 56p1/56p2 with an outdated prompt;
  (2) never write to a OneDrive file without checking it is not open in Word — the batch
  uploader overwrote 57p1.docx while she had it open; a lock guard is now in place;
  (3) base64-over-SSH times out past ~300KB — use scp.

**2026-07-31 — Bhungar (Talaja, Bhavnagar) TSRs 57p1/57p3/56; NAT64 discovery; encumbrance bug:**
- New site **ભુંગર - 093 "Bhungar"**, the village adjacent to Bodki (094). Translator resolves
  the user's spelling "Bhunagar" → `ભુંગર - 093` unaided. Probe-before-batch again paid off:
  dumped all 329 survey options; `56` exists plain here (unlike Bodki, where only 56p1/56p2
  exist), plus `57p૧`/`57p૨`/`57p૩`. All 3 requested surveys delivered.
- **Selenium is the WAF *trigger*, not a victim.** Anshul asked to default to Selenium; tested
  it honestly on a fresh IP → the WAF block page ("Attack ID 20000009", `selects=[]`) on
  navigation #1, and that IP escalated to a full block in ~4 min. http_fetch had fetched a
  record cleanly on the same connection minutes earlier. Reverted; `.env` now carries a
  "do not set this to false" comment. Consider removing the Selenium fallback entirely — when
  http_fetch fails because the IP is blocked, the fallback fires a browser at the WAF and
  deepens the block.
- **The big one: many "WAF blocks" this session were actually IPv6/NAT64 routing.** The mobile
  hotspot flips, as its CGNAT address rotates, between (a) IPv6-only + NAT64/DNS64
  (`AAAA = 64:ff9b::67ea:a267`, the well-known prefix wrapping `103.234.162.103`) where IPv4
  is dead, and (b) IPv4-working / IPv6-dead. `curl` survives both via happy-eyeballs;
  `requests`/urllib3 does **not**. urllib3's `create_connection` *does* iterate all
  getaddrinfo results, but a **scalar** timeout is spent in full on the first dead address so
  it never reaches the second → 25-30s hangs misread as WAF blocks.
  **Fix = short CONNECT timeout, long read timeout** (`timeout=(6, 45)`), which falls through
  to whichever family is alive in *either* direction. Pinning a family is wrong — we proved
  both directions occur within one hour. Currently a scratchpad monkeypatch; belongs in
  `http_fetch.py`. Distinguish the signatures: TLS reset (exit 35) / "Web Page Blocked" +
  Attack ID = real WAF; connect timeout (exit 28) / errno 65 = probably this routing issue.
- **Encumbrance false positive in `findings.py` (unresolved, affects legal output).** 57p3
  reported "charge subsisting" citing entries 446+454, but entry 760 (2016) discharges *both*
  — "State Bank of India, Agriculture Branch, Talaja **and** Bodki Seva Sahkari Mandali Ltd."
  (446 is the same charge pre-merger: S.B.S. = State Bank of Saurashtra → SBI 2008, and
  "Krushi Vibhag" = "Agriculture Branch"). Two compounding defects: (1) `_extract_lender_name`
  regexes all require the literal word `Bank`, so a co-op society ("Bodki Seva Sahkari
  Mandali") yields `None` and can never match a release — `[A-Za-z\s]+` also can't match
  "S.B.S." because of the periods; (2) one `lender` field per entry, so a release naming
  **two** institutions can clear at most one loan. Direction of error is the dangerous one:
  a false encumbrance on clear land. **Flagged to Anshul; the 5 delivered Bodki reports may
  carry the same defect** (Bodki entry 539 was a bulk loan list, same no-"Bank" lender shape)
  — audit not yet run, awaiting his call.
- Process: generated 57p3/56 TSRs from banked PDFs via a scratchpad replica of
  `/process-record`'s post-scrape step (`_build_request_metadata_for_client` +
  `generate_tsr_from_pdf`) — `/generate-tsr` takes no `client_id` and would have reinstated
  the hardcoded ABREL defaults that `18f352f` suppressed. Scrape-then-extract-offline is the
  right sequencing: AnyRoR access is the scarce resource, extraction is local.
- Also confirmed: a uvicorn started before a template commit serves stale code (restarted it
  4 min shy of `87397a5`). `.env` is tracked in git with a live `GEMINI_API_KEY` — flagged.
- Delivered the 3 DOCX to OneDrive under `Bodki 4dec 2023/**Bhungar 31.07.2026**/` — a named
  subfolder, not loose, because Bodki and Bhungar both have surveys 57p1/57p3 and her
  delivered Bodki versions of exactly those sit in `TSR in word/`. Checked for `~$` Word lock
  files first (the 28-July overwrite lesson) and used `cp -n`.

**2026-08-01 — Diffed Mittali's delivered Bodki TSRs against the generated Bhungar ones:**
- **Structure is identical** — 12 paragraphs, 4 tables, Table 2 boilerplate byte-identical,
  Table 4 23×3. A full diff of the findings tables (her 57p3 vs mine) returns **only rows 5
  and 18**. Ref line adapts correctly (`.../BOD/57p3` vs `.../BHU/57p3`).
- **Findings 5/18 phrasing depends on DEFECT TYPE, not on review status** (first guess was
  "she edits the pointer out" — wrong, `45-4p2` is complete and keeps it). Bank charge →
  "subject to bank charge." plainly; bespoke defect (uncertified entries, name mismatch) →
  "point no. N in table no. 3". She writes "point **no.** N", no trailing "above"; generator
  emits "point 8 and 9 in table no. 3 **above**" unconditionally. Captured in memory
  `project-tsr-drafting-findings-5-18` — **inferred from her files, not confirmed by her.**
- **Encumbrance audit of the 7 delivered Bodki TSRs: CLEAN.** Co-op releases matched fine
  there (57p1: release 535 cleared loans 326/360, actives 585/740/921; 56p2: release 1104
  cleared 326, actives 713/825; 57p3: 947/1063 with no release, both active). Nothing wrong
  reached the client — the item flagged for audit on 07-31 is closed.
- **Root cause of the 57p3 false encumbrance corrected by unit-testing
  `detect_active_encumbrances` directly.** My 07-31 claim that the "Bank"-only regex means
  co-op lenders "can never match" was WRONG — `_get_lender_from_entry` prefers the LLM's
  structured `lender` field and the regex is only a fallback. Operative defect is the
  **single `lender` field**: entry 760 names two institutions, only the first survives, so
  454 is never cleared (`760 = both names → active ['446']`; `760 = first only → active
  ['446','454']`, which is what reality produced). Entry 446 stays active under *every*
  scenario — S.B.S. (State Bank of Saurashtra, merged into SBI 2008) vs "State Bank of India,
  Agriculture Branch" is a semantic identity no string matcher reaches.
- Method note: the first synthetic repro was invalid — it used key `entry_type` when
  `_get_entry_type_str` reads `type`, so it found 0 loan entries and "passed" vacuously. The
  giveaway was in an INFO log line I had grepped away. Always assert the intermediate count.

---

## Sessions (newest first)

### 2026-07-22/23 — Browser-free AnyRoR fetch (WAF workaround) + made it the default

- Task: generate TSRs for Belda (Talaja, Bhavnagar) surveys `24/p1` + `48/p4` from a
  handwritten WhatsApp note. The local Selenium scraper was **WAF-blocked** the whole
  session (`ERR_CONNECTION_RESET`/`CLOSED`; the 44 KB `selects=[]` JS-challenge page).
- Ruled out every network angle: WARP/Cloudflare egress (`104.28.x`) is WAF-blocked;
  switching Wi-Fi/mobile didn't help (same office public IP / IPv6-broken Airtel);
  Abu's PC (192.168.29.58) shares the office IP **and** runs WARP → no help; the deployed
  Cloud Run scraper is **down** (503 crash-on-boot, likely a dead `GEMINI_API_KEY` secret;
  gcloud scoped to the wrong project so couldn't inspect).
- **Key discovery:** AnyRoR's WAF resets the *browser* but lets plain HTTP `requests`
  through. Built `anyror/http_fetch.py` — walks the ASP.NET cascading postbacks with
  `requests`, solves the inline base64 captcha via the Gemini `CaptchaSolver`, renders the
  record HTML → PDF with a **local** headless Chrome (local file only, never navigates to
  AnyRoR). Fetched both RoRs → PDFs → TSRs (Opus/high) end-to-end.
- **The bug that ate ~2 hours:** the captcha field is **`txt_captcha_1`** (underscore
  before the `1`), NOT the stale `CONFIG['CAPTCHA_INPUT_ID']` = `txt_captcha1`. Posting to
  the wrong name silently returns "Capcha is not matched" for *every* submit — proven not
  a model/OCR issue by reading captchas by eye and still getting rejected. Also learned the
  survey option format quirks (base ASCII + Gujarati paiki digit, `5`→`પ`, `/p` vs `p`
  inconsistent: `24p૧` vs `48/p૪`).
- Per Anshul's call, **wired http_fetch as the PRIMARY path** in
  `AnyRoRScraper.fetch_land_record()` (Selenium fallback, `ANYROR_HTTP_FETCH` toggle) —
  same dict/PDF contract so callers are unchanged. Added `tests/test_http_fetch.py` (14,
  incl. a regression guard for the captcha field name + the primary/fallback wiring); full
  suite **380 passed**. PR #9 (`feat/anyror-http-fetch-default`), **CI green**. Awaiting
  merge decision (merge → Cloud Run auto-deploy, but GCP IP is WAF-blocked so this helps
  local, not the remote).
- Memory saved: `project_anyror_http_fetch.md`.

---

### 2026-06-10 — CLAUDE.md architecture refresh (closes a bootstrap Next item)

- Updated Key Flows / extraction-modes / env-vars / translation sections to match the
  current pipeline: `EXTRACTION_BACKEND=claude` default (CLI, local-only, hang-prevention
  flags documented), `TRANSLATION_USE_LLM` + `GEMINI_THINKING_LEVEL` + `CLAUDE_EXTRACTION_MODEL`
  added, deterministic-first translation noted. Verified every default against code first.
- Decision: architecture lives in CLAUDE.md (single source of truth, auto-loaded each
  session), NOT duplicated in this journal — journal records changes/decisions only.
- Noticed while verifying (not yet acted on): `extract_all_structured` in
  `unified_extractor.py` (two-pass Gemini variant, ~line 982) has zero callers — dead
  experimental code, candidate for deletion. Dockerfile pins `GEMINI_MODEL_NAME=gemini-2.5-flash`
  (stale vs the `gemini-3.1-pro-preview` default) and does not set `EXTRACTION_BACKEND=gemini`,
  which a cloud/Docker deploy would need.

---

### 2026-06-10 — Journal system bootstrap + current-state snapshot

**Did:** Ported the journal system from `agent-raj-tsr` (same protocol, same structure). Added the Journal Protocol to `CLAUDE.md` so both devs (Anshul + Rishabh) and every Claude session follow it. Per Anshul's call, this entry is a snapshot of *where the project stands now* — past session history was deliberately not reconstructed.

**Current state (orientation for anyone picking this up):**

- **Extraction backend is now Claude CLI, not Gemini.** `EXTRACTION_BACKEND` defaults to `claude` (`tsr_generator/extractors/unified_extractor.py`): shells out to `claude -p` using the local subscription login — no API key, local-only, will NOT work on a headless cloud deploy. Model via `CLAUDE_EXTRACTION_MODEL` (default `sonnet`). Captcha solving + translation stay on Gemini. Rationale: 2026-06-02 model eval scored Opus/Sonnet ≈8.5 vs gemini-3-flash ≈7 on TSR extraction quality.
- **Translation is deterministic-first.** Village matching is exact + scoped lookup against `anyror_hierarchy.json`, always top-down (district → taluka → village); LLM fallback is opt-in via `TRANSLATION_USE_LLM` (default `false`). Includes gadh/garh equivalence and "did you mean" hints (`0d49ee8`, `7e9a5a4`).
- **Local cache ≈ never expires.** `LOCAL_CACHE_TTL_DAYS` defaults to 36500 — land records are immutable, generated TSRs are reused across sessions. `python scripts/tsr_ledger.py` regenerates `docs/tsr_ledger.md` (index of cached TSRs); diff-vs-handtyped-truth notes live in `docs/tsr_ledger_notes.json` and survive refreshes. Use `skip_cache=true` after changing extraction logic/model.
- **Known extraction quality gaps** (per-entry audit in `LAWYER_REVIEW_NOTES_2026_05_20.md`): INHERITANCE entries drop death date + heir relationships; DISTRIBUTION merges solo+joint ownership rows; surveys occasionally gain a spurious `/p` suffix. These are model-drop, not PDF/OCR problems (see Lessons).
- **Open bugs** (`ISSUES.md`): (1) scraper silently selects the first dropdown option when survey-number partial match fails (`anyror/form_filler.py` ~510-517) → can fetch a completely wrong record, worst failure mode in the repo; (2) translation dict mutation race on concurrent requests (`utils/json_translations.py`) → `dictionary changed size during iteration`.
- **Cloud deploy is blocked on infra, not code.** AnyRoR blocks Streamlit Cloud's GCP IP ranges (IPv4 timeouts + IPv6 errno 99). Fix is a scraper microservice on an Indian IP (e.g. Oracle Cloud Mumbai) — code-side retries won't help.
- **Repo hygiene:** `adk_agent/` at repo root is an untracked leftover (only `__pycache__`, sources deleted) — safe to ignore/delete. `CLAUDE.md`'s env-var section still describes Gemini-only extraction and predates `EXTRACTION_BACKEND` / `CLAUDE_EXTRACTION_MODEL` / `TRANSLATION_USE_LLM`.

**Next:**
- Fix `ISSUES.md` #1 (remove the silent dropdown fallback — fail loudly, log the available options, consider khata-aware selection) and #2 (lock around `_add_spelling_variation`).
- Close the lawyer-review extraction gaps (INHERITANCE death dates/relationships, DISTRIBUTION row merging, spurious `/p`) — likely prompt work now that extraction runs on Claude; add supporting-docs guidance to the prompt (model-eval follow-up).
- Stand up the Indian-IP scraper microservice so the Streamlit Cloud deploy works end-to-end.
- Refresh `CLAUDE.md`'s env-var/extraction sections for the Claude CLI backend.
- Schedule the monthly journal-compactification agent (not yet set up for this repo).

---

## Lessons Compendium

<!-- Compacted, still-load-bearing lessons. Normally promoted from session entries
     during monthly review; seeded at bootstrap with lessons accumulated before the
     journal existed (these previously lived only in Anshul's Claude memory). -->

- **AnyRoR has daily downtime 14:00–15:00 IST.** Scrape failures in that window are expected maintenance, not a bug. Retry after ~15:05 IST.
- **Run TSR generations sequentially, never in parallel.** Parallel `/process-record` calls conflict in the scraper (Selenium sessions); on `invalid session id`, retry the request. Holds even under time pressure.
- **Pass survey numbers as ASCII** (e.g. `"38/3"`), never Gujarati digits — the scraper maps to the Gujarati-digit dropdown internally (since `b1a459a`).
- **Translate top-down:** scope taluka by district and village by district+taluka. Flat village lookup picks the wrong village across districts; the deterministic matcher now enforces this.
- **"Khalsa" is a real Gujarat tenure classification**, not a village-name leak into `nature_of_land`. Don't whitelist tenure values.
- **AnyRoR PDFs carry a real digital text layer** (verified across the whole local cache). Extraction gaps are the model dropping data, not OCR failure — don't reach for vision/HTR as the first lever. The handwritten ~10% is a separate image stream; frontier-vision + verification beats custom HTR there.
- **The Claude CLI backend must keep its hang-prevention flags.** `_invoke_claude_cli` passes `--strict-mcp-config` and `--settings` with `effortLevel:low`, `enabledPlugins:{}`, auto-memory/dream off. Without these a headless call inherits the interactive config and hangs >300s on a ~23KB prompt. If you touch the invocation, keep them.
- **Local vs cloud output can silently differ** when env vars, model names, or cache state diverge between environments — compare configs before debugging "regressions".
