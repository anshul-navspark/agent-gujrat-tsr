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

# ADK 2.x agent workflow (adk_agent/) — single-command E2E
pip install -r requirements.txt -r requirements-adk.txt
python -m adk_agent --pdf record.pdf --out report.docx     # PDF -> TSR
python -m adk_agent --pdf record.pdf --dry-run             # offline (no API key)
python -m adk_agent --survey "Kutch/Abdasa/Keshav/150"     # live scrape -> TSR
python -m adk_agent feedback import --run <run_id> --truth ground_truth.json
python -m adk_agent eval                                    # score vs golden set
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
PDF → `extract_text_from_pdf()` → `extract_all_unified()` (1 LLM call) → `generate_findings_table()` → `create_tsr_document()` → DOCX

**Scraping Pipeline:**
Request → TranslationService (English→Gujarati) → AnyRoR Scraper (Selenium + CAPTCHA solver) → PDF → Cache (GCS)

### Two Extraction Modes

Controlled by `USE_OPTIMIZED_EXTRACTION` env var (default: `true`):
- **Optimized** (1 LLM call): `tsr_generator/extractors/unified_extractor.py` — 60-70% token savings
- **Original** (3 LLM calls): `tsr_generator/api/tsr_generator.py`

Mode switching happens in `tsr_generator/__init__.py`.

### ADK 2.x Agent Workflow (`adk_agent/`)

A skill-based **Google Agent Development Kit (ADK 2.x)** re-expression of the pipeline that runs E2E through one command (`python -m adk_agent`). It is a NEW orchestration + observability layer that **reuses** the existing internals — the legacy Streamlit/API/CLI/Docker paths are untouched. Full design: `docs/adk_architecture.md`.

- **Skill graph** (`adk_agent/graph.py`): ADK 2.0 `Workflow` of `ingest → extractor → assemble`. `ingest`/`assemble` are function nodes wrapping `extract_text_from_pdf`/`process_entry_details`+`generate_findings_table`+`create_tsr_document`; `extractor` is a native ADK `LlmAgent` (Gemini) whose instruction reuses `build_unified_prompt` (supplied as a callable `InstructionProvider` since the prompt contains literal `{}`) with `output_schema=UnifiedExtraction`.
- **Two engines** (`adk_agent/pipeline.py`): `engine="pipeline"` (default, Python orchestration driving an ADK `Runner` for the LLM step) and `engine="graph"` (the full ADK `Workflow`). Run config + the live run record ride a `contextvars` `RunContext` (`adk_agent/observability/run_context.py`).
- **Observability** (`adk_agent/observability/plugin.py`): `ObservabilityPlugin` (a `BasePlugin` on the `App`) captures every model call (rendered prompt, raw response, `usage_metadata` tokens) + skill timings into `runs/<run_id>/{record.json,extraction.json,source.txt,trace.md}`.
- **Ground-truth feedback loop** (`adk_agent/feedback/`): `feedback import` diffs the model extraction against a lawyer-corrected `ground_truth.json` (aligned by entry number), distils each correction into a deduped prompt guideline injected into the next extraction prompt (`prompting_guidelines.jsonl`), and promotes the run into the golden eval set.
- **Eval** (`adk_agent/eval/`): `golden.evalset.json` (ADK evalset shape) + a structured evaluator (`python -m adk_agent eval`) reporting `field_accuracy` / `entry_recall` / `type_accuracy` vs ground truth.
- **Offline**: `--dry-run` (or no `GEMINI_API_KEY`) swaps in `FakeGemini` (`adk_agent/dry_run_model.py`) so the whole pipeline + tests run with no network. Tests: `tests/test_adk_pipeline.py`, `tests/test_adk_feedback.py`.

### Dependency Injection

Abstract interfaces in `core/interfaces.py` → concrete implementations in `services/` → singleton factories (`get_*_service()`) → FastAPI `Depends()` injection in `api/dependencies.py`.

### Caching

Two backends, auto-selected in `services/cache_service.py:get_cache_service`: **GCS** `CacheService` when `GCS_CACHE_BUCKET` is set (7-day TTL; DOCX cache auto-clears on new deployments via `GIT_COMMIT_SHA`), otherwise a local-filesystem `LocalCacheService` fallback under `~/.cache/gujrat_tsr_agent/cache`. Cache key is SHA256 of (translated) district+taluka+village+survey_number.

The **local** cache defaults to ~never-expire (`LOCAL_CACHE_TTL_DAYS`, default 36500) — land records are immutable, so generated TSRs are reused across sessions rather than silently aging out and being regenerated. Pass `skip_cache=true` to force a fresh run (e.g. after changing extraction logic/model). `python scripts/tsr_ledger.py` writes `docs/tsr_ledger.md`, a human-readable index of the locally cached TSRs; diff-vs-handtyped-truth notes are kept in `docs/tsr_ledger_notes.json` and preserved across refreshes.

## Key Environment Variables

- `GEMINI_API_KEY` — required, Google Gemini API key
- `GEMINI_MODEL_NAME` — main extraction model, default: `gemini-3.1-pro-preview`
- `CAPTCHA_MODEL_NAME` — captcha solver model, default: `gemini-3-flash-preview`
- `GEMINI_TRANSLATION_MODEL` — translation lookup model, default: `gemini-3.1-flash-lite-preview`
- `USE_OPTIMIZED_EXTRACTION` — default: `true`
- `GCS_CACHE_BUCKET` — optional, enables GCS caching
- `LOCAL_CACHE_TTL_DAYS` — local cache TTL in days when no GCS bucket; default `36500` (≈never expire)
- `HEADLESS` — browser headless mode for scraping
- `MAX_WORKERS` — parallel processing thread count

## Domain Concepts

- **Entry types**: SALE, INHERITANCE, PARTITION, LOAN, MORTGAGE, RELEASE, ORDER, PROMULGATION (see `tsr_generator/extractors/entry_schema.py`)
- **Active encumbrance detection**: Loans without matching releases are flagged in findings. Matching uses explicit entry number references and lender name + chronological order (`tsr_generator/extractors/findings.py`)
- **Translation**: English→Gujarati lookup via `anyror_hierarchy.json` (~2MB), context-aware for district/taluka/village hierarchies
- **Certification patterns**: Entries may be certified/uncertified, tracked per-entry during extraction
