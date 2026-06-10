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

# Run CLI (TSR generation from PDF)
python -m tsr_generator path/to/input.pdf --output output.docx

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
Request → TranslationService (English→Gujarati, deterministic-first) → AnyRoR Scraper (Selenium + Gemini CAPTCHA solver) → PDF → Cache (GCS or local)

### Extraction Modes & Backends

Mode is controlled by `USE_OPTIMIZED_EXTRACTION` (default: `true`), switched in `tsr_generator/__init__.py`:
- **Optimized** (1 LLM call): `tsr_generator/extractors/unified_extractor.py` — 60-70% token savings
- **Original** (3 LLM calls): `tsr_generator/api/tsr_generator.py` — Gemini-only

The optimized path additionally has a backend switch, `EXTRACTION_BACKEND` (default: `claude`):
- **claude** — shells out to `claude -p` using the local Claude Code subscription login (no API key). Requires an authenticated `claude` CLI on PATH, so it only works locally — Docker/Streamlit Cloud deploys must set `EXTRACTION_BACKEND=gemini`. The invocation (`_invoke_claude_cli`) passes `--strict-mcp-config` plus a `--settings` override (low effort, no plugins, no auto-memory); without these flags headless calls hang >300s — keep them if you touch it.
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
- `CLAUDE_EXTRACTION_MODEL` — model alias passed to the `claude` CLI, default: `sonnet`
- `GEMINI_MODEL_NAME` — Gemini extraction model (only used when `EXTRACTION_BACKEND=gemini`), default: `gemini-3.1-pro-preview`
- `GEMINI_THINKING_LEVEL` — thinking level for Gemini extraction, default: `low`
- `CAPTCHA_MODEL_NAME` — captcha solver model, default: `gemini-3-flash-preview`
- `GEMINI_TRANSLATION_MODEL` — translation lookup model, default: `gemini-3.1-flash-lite-preview`
- `TRANSLATION_USE_LLM` — enable the LLM fallback for village matching, default: `false` (deterministic exact + scoped matching only)
- `USE_OPTIMIZED_EXTRACTION` — default: `true`
- `GCS_CACHE_BUCKET` — optional, enables GCS caching
- `LOCAL_CACHE_TTL_DAYS` — local cache TTL in days when no GCS bucket; default `36500` (≈never expire)
- `HEADLESS` — browser headless mode for scraping
- `MAX_WORKERS` — parallel processing thread count

## Domain Concepts

- **Entry types**: SALE, INHERITANCE, PARTITION, LOAN, MORTGAGE, RELEASE, ORDER, PROMULGATION (see `tsr_generator/extractors/entry_schema.py`)
- **Active encumbrance detection**: Loans without matching releases are flagged in findings. Matching uses explicit entry number references and lender name + chronological order (`tsr_generator/extractors/findings.py`)
- **Translation**: English→Gujarati lookup via `anyror_hierarchy.json` (~2MB), deterministic-first and always scoped top-down (district → taluka → village); LLM fallback only when `TRANSLATION_USE_LLM=true`
- **Certification patterns**: Entries may be certified/uncertified, tracked per-entry during extraction

## Journal Protocol

Project journal is at `docs/journal.md`. **At session start, read it.** Then:
1. Use `git log` since the last dated entry + the "Active Draft" section to write a new entry for the previous session, then clear the draft.
2. Surface any lessons from past entries relevant to the current task; suggest alternative approaches when current work matches a past pattern.
3. **During the session**, append bullets to "Active Draft" as milestones are hit (commits, abandoned approaches, surprising results, key decisions).

Goal: avoid repeating mistakes, document approach so future sessions know what's coming, suggest improvements based on past patterns. Never auto-compact — monthly compactification is PR-based and user-reviewed.
