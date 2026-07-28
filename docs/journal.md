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
