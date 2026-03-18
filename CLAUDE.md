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
PDF → `extract_text_from_pdf()` → `extract_all_unified()` (1 LLM call) → `generate_findings_table()` → `create_tsr_document()` → DOCX

**Scraping Pipeline:**
Request → TranslationService (English→Gujarati) → AnyRoR Scraper (Selenium + CAPTCHA solver) → PDF → Cache (GCS)

### Two Extraction Modes

Controlled by `USE_OPTIMIZED_EXTRACTION` env var (default: `true`):
- **Optimized** (1 LLM call): `tsr_generator/extractors/unified_extractor.py` — 60-70% token savings
- **Original** (3 LLM calls): `tsr_generator/api/tsr_generator.py`

Mode switching happens in `tsr_generator/__init__.py`.

### Dependency Injection

Abstract interfaces in `core/interfaces.py` → concrete implementations in `services/` → singleton factories (`get_*_service()`) → FastAPI `Depends()` injection in `api/dependencies.py`.

### Caching

GCS-based with 7-day TTL. Cache key is SHA256 of district+taluka+village+survey_number. DOCX cache auto-clears on new deployments via `GIT_COMMIT_SHA`.

## Key Environment Variables

- `GEMINI_API_KEY` — required, Google Gemini API key
- `GEMINI_MODEL_NAME` — default: `gemini-3-pro-preview`
- `USE_OPTIMIZED_EXTRACTION` — default: `true`
- `GCS_CACHE_BUCKET` — optional, enables GCS caching
- `HEADLESS` — browser headless mode for scraping
- `MAX_WORKERS` — parallel processing thread count

## Domain Concepts

- **Entry types**: SALE, INHERITANCE, PARTITION, LOAN, MORTGAGE, RELEASE, ORDER, PROMULGATION (see `tsr_generator/extractors/entry_schema.py`)
- **Active encumbrance detection**: Loans without matching releases are flagged in findings. Matching uses explicit entry number references and lender name + chronological order (`tsr_generator/extractors/findings.py`)
- **Translation**: English→Gujarati lookup via `anyror_hierarchy.json` (~2MB), context-aware for district/taluka/village hierarchies
- **Certification patterns**: Entries may be certified/uncertified, tracked per-entry during extraction
