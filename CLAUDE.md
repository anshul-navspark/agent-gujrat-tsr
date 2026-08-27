# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Gujarat TSR Agent automates Title Search Report generation from Gujarat AnyRoR (Any Record of Rights) land records. It scrapes PDFs from the AnyRoR portal, extracts structured data using Google Gemini AI, and generates professional DOCX reports.

## Commands

```bash
# Run tests
pytest
pytest --cov=. --cov-report=html
pytest -m integration            # integration tests only

# Run API server
uvicorn api.server:app --host 0.0.0.0 --port 8080

# Run Streamlit UI
streamlit run app/streamlit_app_cloud.py

# Docker
docker build -t agent-gujrat-tsr .
docker run -e GEMINI_API_KEY=xxx -p 8080:8080 agent-gujrat-tsr
```

## Architecture

### Layer Structure

```
Presentation:  Streamlit UI (app/) ↔ FastAPI Server (api/)
Services:      translation, scraping, file, cache, processing (services/)
Core:          models, interfaces, config, exceptions (core/)
Infrastructure: AnyRoR scraper (anyror/), TSR generator (tsr_generator/), utils (utils/)
```

### Key Flows

**TSR Generation Pipeline:**
PDF → `extract_text_from_pdf()` → `extract_all_unified()` (1 LLM call — Claude CLI by default, see Extraction Modes & Backends) → `generate_findings_table()` → `create_tsr_document()` → DOCX

**Scraping Pipeline:**
Request → TranslationService (English→Gujarati, deterministic-first) → AnyRoR fetch → PDF → Cache (GCS or local)

`AnyRoRScraper.fetch_land_record()` has exactly one path: the **browser-free HTTP fetch** (`anyror/http_fetch.py`). It walks AnyRoR's ASP.NET cascading postbacks with `requests`, solves the inline base64 captcha with the Gemini `CaptchaSolver`, and renders the record HTML to PDF with a **local** headless Chrome (loading a local file only — never navigating to AnyRoR). On failure it returns `{'success': False, 'error': ...}` and stops. **There is deliberately no Selenium fallback** — browser-shaped clients are the WAF *trigger*, and driving the portal with Chrome drew an Attack ID that burned the source IP (journal 2026-07-31), so the whole Selenium stack (`form_filler.py`, `webdriver_manager.py`, the `ANYROR_SELENIUM_FALLBACK` toggle) was deleted. Gotcha baked into the code: the captcha input field is `txt_captcha_1` (underscore before the `1`), NOT the stale `CONFIG['CAPTCHA_INPUT_ID']` value `txt_captcha1` — posting to the wrong name silently yields "Capcha is not matched". PDF rendering needs a Chrome binary (`CHROME_BIN`, else auto-detected).

### Extraction Modes & Backends

Extraction always runs the unified single-call path (`tsr_generator/extractors/unified_extractor.py`, 60-70% token savings), wired unconditionally in `tsr_generator/__init__.py`. The old 3-call Gemini pipeline (`tsr_generator/api/tsr_generator.py`) is no longer selectable and survives only because `mcp_server/tools/generate_tsr.py` still imports it; `USE_OPTIMIZED_EXTRACTION` is now inert.

The optimized path additionally has a backend switch, `EXTRACTION_BACKEND` (default: `claude`):
- **claude** — shells out to `claude -p` using the local Claude Code subscription login (no API key). Requires an authenticated `claude` CLI on PATH, so it only works locally — Docker/Streamlit Cloud deploys must set `EXTRACTION_BACKEND=gemini`. The invocation (`_invoke_claude_cli`) passes `--strict-mcp-config` plus a `--settings` override (no plugins, no auto-memory, effort from `CLAUDE_EXTRACTION_EFFORT`); the **no-plugins** flag is what prevents the >300s headless hang — keep it if you touch this. Effort defaults to `high` (was a hardcoded `low`); high effort with plugins-off is safe and, on Opus, was faster *and* more accurate than Sonnet in the 2026-06-11 eval. Timeout auto-bumps to 900s for high/xhigh effort.
- **gemini** — LangChain `ChatGoogleGenerativeAI` using `GEMINI_MODEL_NAME` + `GEMINI_THINKING_LEVEL`.

CAPTCHA solving and translation always stay on Gemini regardless of this setting.

### Dependency Injection

Abstract interfaces in `core/interfaces.py` → concrete implementations in `services/` → singleton factories (`get_*_service()`) → FastAPI `Depends()` injection in `api/dependencies.py`.

### Caching

Two backends, auto-selected in `services/cache_service.py:get_cache_service`: **GCS** `CacheService` when `GCS_CACHE_BUCKET` is set (7-day TTL; DOCX cache auto-clears on new deployments via `GIT_COMMIT_SHA`), otherwise a local-filesystem `LocalCacheService` fallback under `~/.cache/gujrat_tsr_agent/cache`. Cache key is SHA256 of (translated) district+taluka+village+survey_number.

The **local** cache defaults to ~never-expire (`LOCAL_CACHE_TTL_DAYS`, default 36500) — land records are immutable, so generated TSRs are reused across sessions rather than silently aging out and being regenerated. Pass `skip_cache=true` to force a fresh run (e.g. after changing extraction logic/model). `python scripts/tsr_ledger.py` writes `docs/tsr_ledger.md`, a human-readable index of the locally cached TSRs; diff-vs-handtyped-truth notes are kept in `docs/tsr_ledger_notes.json` and preserved across refreshes.

## Key Environment Variables

- `GEMINI_API_KEY` — required at startup (`core/config.py` validation); used for CAPTCHA solving, translation, and extraction when `EXTRACTION_BACKEND=gemini`
- `EXTRACTION_BACKEND` — `claude` (default) or `gemini`; see Extraction Modes & Backends
- `CLAUDE_EXTRACTION_MODEL` — model alias passed to the `claude` CLI, default: `opus` (Opus 4.8; was `sonnet`)
- `CLAUDE_EXTRACTION_EFFORT` — effort level for the `claude` CLI extraction, default: `high` (was hardcoded `low`); `high`/`xhigh` auto-raise the subprocess timeout to `CLAUDE_EXTRACTION_TIMEOUT` (default 900s)
- `GEMINI_MODEL_NAME` — Gemini extraction model (only used when `EXTRACTION_BACKEND=gemini`), default: `gemini-3.1-pro-preview`
- `GEMINI_THINKING_LEVEL` — thinking level for Gemini extraction, default: `low`
- `CAPTCHA_MODEL_NAME` — captcha solver model, default: `gemini-3-flash-preview`
- `GEMINI_TRANSLATION_MODEL` — translation lookup model, default: `gemini-3.1-flash-lite-preview`
- `TRANSLATION_USE_LLM` — enable the LLM fallback for village matching, default: `false` (deterministic exact + scoped matching only)
- `USE_OPTIMIZED_EXTRACTION` — **inert**, kept only so existing deploy configs do not break
- `GCS_CACHE_BUCKET` — optional, enables GCS caching
- `LOCAL_CACHE_TTL_DAYS` — local cache TTL in days when no GCS bucket; default `36500` (≈never expire)
- `HEADLESS` — browser headless mode for scraping
- `MAX_WORKERS` — parallel processing thread count
- `CHROME_BIN` — Chrome/Chromium binary used by the HTTP-fetch path to render the record HTML to PDF; auto-detected (system Chrome / Playwright chromium) if unset

## Domain Concepts

- **Entry types**: SALE, INHERITANCE, PARTITION, LOAN, MORTGAGE, RELEASE, ORDER, PROMULGATION (see `tsr_generator/extractors/entry_schema.py`)
- **Active encumbrance detection**: Loans without matching releases are flagged in findings. Matching uses explicit entry number references and lender name + chronological order (`tsr_generator/extractors/findings.py`)
- **Translation**: English→Gujarati lookup via `anyror_hierarchy.json` (~2MB), deterministic-first and always scoped top-down (district → taluka → village); LLM fallback only when `TRANSLATION_USE_LLM=true`
- **Certification patterns**: Entries may be certified/uncertified, tracked per-entry during extraction
- **Clients library**: `clients.json` at the repo root holds saved client/lender details (name, CIN, address, attention person, ref prefix, reference email date). Loaded once via `core.clients.get_client_library()`. The Streamlit sidebar lets users pick the active client; the selection flows through the `/process-record` API as `client_id`. Missing/malformed `clients.json` → falls back to hardcoded ABREL defaults in the DOCX template (`tsr_generator/document/tsr_document.py`). When `resolved_client is None` (empty/missing library), DOCX caching is disabled for that request — PDFs are still cached and shared. Each request regenerates the DOCX from the cached PDF. This is acceptable cost since DOCX generation is cheap relative to scraping. To add a client: edit `clients.json`, commit, redeploy.
- **DOCX cache split**: The GCS cache stores PDFs keyed by `(district, taluka, village, survey)` (shared across clients) and DOCXs keyed by `(pdf_key, client_id)` under `cache/{pdf_key}/docx_{client_id}.docx`. Two clients sharing a survey get distinct DOCXs.

## Journal Protocol

Project journal is at `docs/journal.md`. **At session start, read it.** Then:
1. Use `git log` since the last dated entry + the "Active Draft" section to write a new entry for the previous session, then clear the draft.
2. Surface any lessons from past entries relevant to the current task; suggest alternative approaches when current work matches a past pattern.
3. **During the session**, append bullets to "Active Draft" as milestones are hit (commits, abandoned approaches, surprising results, key decisions).

Goal: avoid repeating mistakes, document approach so future sessions know what's coming, suggest improvements based on past patterns. Never auto-compact — monthly compactification is PR-based and user-reviewed.
