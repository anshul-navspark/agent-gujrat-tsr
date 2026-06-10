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

---

## Sessions (newest first)

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
