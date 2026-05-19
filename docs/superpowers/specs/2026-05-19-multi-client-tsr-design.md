# Multi-Client TSR Generation — Design

**Date:** 2026-05-19
**Status:** Approved (design phase)
**Working tree:** `claude/sweet-hodgkin-7c7d04`

## Problem

The TSR document hardcodes a single client — "ABREL SPV 2 Limited" (Aditya Birla) — across name, CIN, address, attention person, and report reference prefix. To generate a TSR for any other client today, a developer must edit `tsr_generator/document/tsr_document.py` and redeploy. The Streamlit UI exposes no client field at all; only district / taluka / village / survey number.

We want a Streamlit-driven workflow where the team:

1. Keeps the current ABREL details saved permanently as the default client.
2. Can generate TSRs for additional clients without editing the document template each time.
3. Picks the active client once per session from a dropdown.

## Goals & non-goals

**Goals**

- A `clients.json` file in the repo holds every client we ever generate TSRs for.
- The Streamlit sidebar has an "Active Client" dropdown listing all entries.
- Selected client flows from the UI through the API into the generated DOCX (name, CIN, address, attention person, ref prefix, reference email date).
- The GCS cache is correct: two clients running the same survey get two distinct DOCXs (no silent data corruption from shared cache).
- The system is backwards-compatible: if `clients.json` is missing or malformed, the existing hardcoded ABREL defaults are used.

**Non-goals (deferred)**

- UI for editing `clients.json` from the browser. Adding a client requires editing the file and redeploying.
- Per-row client column in the Excel batch. The whole batch uses the active client.
- Configurable lawyer / advocate header (Vijay Choudhary, Advocate & Associates). Stays hardcoded.
- Multi-tenancy / per-user libraries.
- Ad-hoc client override fields in the UI (everything goes in JSON).

## Schema: `clients.json`

A new file at the repo root.

```json
{
  "default_client_id": "abrel_spv_2",
  "clients": [
    {
      "id": "abrel_spv_2",
      "display_name": "ABREL SPV 2 Limited (Aditya Birla)",
      "client_name": "ABREL SPV 2 Limited",
      "client_cin": "(CIN: U40108MH2020PLC352631),",
      "client_address": "A-2, Aditya Birla Centre, S.K. Ahire Marg,\nWorli, Mumbai-400030.",
      "kind_attn": "Kind Attn.: Mr. Rahul Patil",
      "ref_prefix": "ABREL",
      "reference_email_date": "21.11.2023"
    }
  ]
}
```

**Field semantics:**

| Field | Required | Use |
|---|---|---|
| `id` | yes | Stable kebab-case key. Used in cache key, API request body, logs. Must be unique. |
| `display_name` | yes | Shown in the dropdown. |
| `client_name` | yes | "To:" line in the TSR (`tsr_generator/document/tsr_document.py:136`). |
| `client_cin` | optional | CIN line under client name. |
| `client_address` | yes | Multi-line address (newlines preserved). |
| `kind_attn` | optional | "Kind Attn.: ..." line. |
| `ref_prefix` | optional, defaults to `"ABREL"` | Replaces the hardcoded prefix in `Ref. No. ABREL/GUJ/...` on `tsr_document.py:116`. |
| `reference_email_date` | optional | Used in the "Re: Email Dated ..." line. |

`default_client_id` is optional; if missing or unknown, the first entry in `clients` is used.

## UI: sidebar picker

The Streamlit sidebar gains one section, visible on every tab:

```
─── Active Client ───────────────
[ ABREL SPV 2 Limited (Aditya...) ▾ ]

▸ View details
  Name:    ABREL SPV 2 Limited
  CIN:     U40108MH2020PLC352631
  Address: A-2, Aditya Birla Centre...
  Attn:    Mr. Rahul Patil
  Ref:     ABREL/GUJ/...

To add or edit a client, edit clients.json and redeploy.
```

**Behavior:**

- Dropdown lists every entry by `display_name`.
- Pre-selected on load: `default_client_id` (or first entry if not set).
- Selection persisted in `st.session_state.active_client_id` — survives tab switches within the session, resets to default on full reload.
- "View details" is a collapsed expander showing the read-only saved fields for confirmation.
- Both the **Single Record** and **Batch Processing** tabs use whichever client is selected — no per-tab picker.
- A short caption at the top of each form ("*Generating TSR for: ABREL SPV 2 Limited*") confirms which client a click will use.

## Plumbing: UI → API → DOCX

Three layers change.

### 1. Streamlit → API client (`app/api_client.py`)

`TSRAPIClient.process_record()` gains an optional parameter:

```python
def process_record(
    self,
    district: str,
    taluka: str,
    village: str,
    survey_number: str,
    client_id: Optional[str] = None,
) -> APIResponse:
```

When `client_id` is set, it's added to the JSON body sent to `/process-record`. Both `single_record_form.py` and `batch_processing_form.py` read `st.session_state.active_client_id` and pass it through.

### 2. API request model & handler (`api/server.py`)

```python
class LandRecordRequest(BaseModel):
    district: str
    taluka: str
    village: str
    survey_number: str
    output_format: str = "zip"
    client_id: Optional[str] = None   # NEW
```

In the `/process-record` handler, after loading the client library:

- If `client_id` is provided and exists → look up that client record.
- If `client_id` is missing → use `default_client_id`.
- If `client_id` is provided but unknown → log a warning, fall back to default client (don't 400).
- If `clients.json` is missing entirely → leave `request_metadata` without client fields → DOCX template falls back to its hardcoded ABREL defaults (no regression).

The resolved client fields are merged into the existing `_request_metadata` dict. **Only non-None client fields are merged**, so a client that omits an optional field (e.g., `kind_attn`) lets the DOCX template's hardcoded fallback handle it rather than overwriting it with an empty string:

```python
_request_metadata = {
    'district': request.district,
    'taluka': request.taluka,
    'village': request.village,
    'survey_number': request.survey_number,
}
if client is not None:
    for field in ('client_name', 'client_cin', 'client_address',
                  'kind_attn', 'ref_prefix', 'reference_email_date'):
        value = getattr(client, field)
        if value:
            _request_metadata[field] = value
```

### 3. TSR generator (`tsr_generator/api/tsr_generator_optimized.py`)

Lines 98–108 already copy known keys from `request_metadata` into `land_details`. Extend the same block to copy the six new client fields under the same `request_metadata.get(key)` pattern. The DOCX template (`tsr_generator/document/tsr_document.py:136-142`) already reads these `land_details` keys — no template changes needed except one small adjustment:

- `tsr_document.py:116` — replace the hardcoded `"ABREL/GUJ/"` with `f"{ref_prefix}/GUJ/"`, where `ref_prefix = sanitize_text(land_details.get('ref_prefix')) or 'ABREL'`.

## Cache key fix

Today, `services/cache_service.py` keys both the scraped PDF and the generated DOCX by `SHA256(district + taluka + village + survey_number)`. If two clients run the same survey, the second call returns the first client's DOCX — silent data corruption, since the DOCX has the client name, CIN, and address embedded.

**Fix: split the cache so the PDF stays shared and the DOCX is per-client.**

- `cache/{pdf_key}/original.pdf` — keyed by `SHA256(district+taluka+village+survey)`, shared across clients.
- `cache/{pdf_key}/docx_{client_id}.docx` — separate DOCX per client.
- `cache/{pdf_key}/metadata.json` — gains a `docx_versions: { "<client_id>": "<timestamp>", ... }` field tracking each per-client DOCX.

**Request flow:**

1. Compute `pdf_key`.
2. Look up `original.pdf` — hit means skip scraping.
3. Look up `docx_{client_id}.docx` — hit means skip extraction + DOCX generation. Either layer can hit independently.
4. On miss at either layer, run that step and write back to its own cache slot.

The existing `GIT_COMMIT_SHA` invalidation in `api/server.py:lifespan` continues to clear all DOCX cache entries on new deployments. PDF cache is untouched by version bumps (PDFs don't depend on app code).

`services/cache_service.py` API changes:

- Replace `get_cached_record_by_key(cache_key)` / `cache_record_by_key(...)` with:
  - `get_cached_pdf_by_key(pdf_key) -> Optional[bytes]`
  - `cache_pdf_by_key(pdf_key, pdf_content)`
  - `get_cached_docx_by_key(pdf_key, client_id) -> Optional[bytes]`
  - `cache_docx_by_key(pdf_key, client_id, docx_content)`
- No legacy-compat reads. The existing `GIT_COMMIT_SHA` invalidation in `api/server.py:lifespan` already clears every cached DOCX on the first deploy after this change, so the legacy `cache/{key}/tsr.docx` files disappear before the new code ever needs to read them. PDFs in the cache are preserved (PDF scraping result doesn't depend on app code).

## Validation, errors, and tests

### Validation (at startup)

A new module `core/clients.py` loads and validates `clients.json`:

- Returns a `ClientLibrary` dataclass with `clients: dict[str, Client]` and `default_client_id: Optional[str]`.
- Validates: file exists, valid JSON, every entry has `id` + `client_name` + `client_address`, `id` values are unique, `default_client_id` (if set) refers to an existing id, every `id` matches `^[a-z0-9_-]+$`.
- Validation errors log field-level detail and the system falls back to a legacy library (empty — triggers hardcoded ABREL fallback). Never crashes startup.
- Loaded once via an `@lru_cache` factory `get_client_library()`, mirroring the existing `get_*_service()` pattern in [services/](services/).

### Error handling at runtime

| Condition | Behavior |
|---|---|
| Unknown `client_id` in `/process-record` | Log warning, fall back to default client. Don't 400. |
| Missing `clients.json` at startup | Log warning. Every request uses legacy hardcoded ABREL fallback. |
| Malformed `clients.json` | Same as missing — fall back, log error with parse detail. |
| `client_id` is `None` in API request | Use `default_client_id`. |

Existing CLI usage (`python -m tsr_generator path/to/input.pdf`) continues to work unmodified — it doesn't go through the API or `request_metadata` path, so the DOCX template's existing fallback fires.

### Tests (in `tests/`)

**`test_clients_library.py`** (`core/clients.py`):

- Loads a valid `clients.json` → returns expected library
- Missing file → returns empty library, no crash, warning logged
- Malformed JSON → returns empty library, warning logged
- Duplicate `id` values → rejected, falls back to empty
- Unknown `default_client_id` → falls back to first entry
- `id` regex violation → entry skipped, warning logged

**`test_server_client_routing.py`** (`api/server.py`):

- Request with valid `client_id` → resolved `_request_metadata` contains that client's fields
- Request with `client_id=None` → uses `default_client_id`'s fields
- Request with unknown `client_id` → falls back to default, warning logged, request succeeds
- Backwards compat: when `clients.json` is absent, request still succeeds with no client fields in metadata (DOCX uses hardcoded ABREL)

**`test_cache_split.py`** (`services/cache_service.py`):

- Same survey + two different `client_id`s → PDF cache hits both times, DOCX caches are distinct
- Same survey + same `client_id` → both PDF and DOCX cache hit (full HIT)
- DOCX miss + PDF hit → scraping skipped, DOCX regenerated and written under the per-client key

All tests are unit-level; mock the GCS cache service rather than hitting real GCS.

## File-by-file change summary

| File | Change |
|---|---|
| `clients.json` (new) | Repo-root file with at least the ABREL entry as default. |
| `core/clients.py` (new) | `Client` dataclass, `ClientLibrary` dataclass, `get_client_library()` factory, JSON loader + validator. |
| `app/streamlit_app_cloud.py` | Add sidebar `Active Client` section. Read library once, store selection in `st.session_state.active_client_id`. |
| `app/components/single_record_form.py` | Read `st.session_state.active_client_id` and pass to `api_client.process_record(...)`. Add "Generating TSR for: ..." caption. |
| `app/components/batch_processing_form.py` | Same — pass `client_id` to each `_process_single_record()` call. Caption at top. |
| `app/api_client.py` | Add `client_id: Optional[str] = None` parameter to `process_record()`. Include in JSON body. |
| `api/server.py` | Extend `LandRecordRequest` with `client_id`. Resolve client from library, merge into `_request_metadata`. Update cache flow to use split keys. |
| `services/cache_service.py` | Split `get_cached_record_by_key` / `cache_record_by_key` into PDF and DOCX variants. Legacy-compatible reads. |
| `tsr_generator/api/tsr_generator_optimized.py` | Extend `request_metadata`→`land_details` copy to include the six client fields. |
| `tsr_generator/document/tsr_document.py` | Line 116: read `ref_prefix` from `land_details` instead of hardcoding `"ABREL"`. |
| `tests/test_clients_library.py` (new) | Unit tests for the library loader. |
| `tests/test_server_client_routing.py` (new) | Unit tests for client resolution in the API handler. |
| `tests/test_cache_split.py` (new) | Unit tests for the split cache. |
| `CLAUDE.md` | Add `clients.json` to the "Key Environment Variables" / domain concepts section. Note "Adding a client" workflow. |
| `README.md` | Brief mention of multi-client support and how to add a client. |

## Rollout plan

1. Land the `core/clients.py` loader + `clients.json` (with ABREL only) + tests. No behavior change yet — nothing reads the library.
2. Land the API + cache split + tests. Both client routes still resolve to ABREL since there's only one entry. Verify cache hit/miss in logs.
3. Land the Streamlit sidebar. From here, the user can already pick "ABREL" (only option) and confirm the plumbing.
4. Add the second client entry to `clients.json` and dogfood end-to-end: generate a TSR with each client for the same survey, confirm the DOCX `To:` block and `Ref. No.` differ, confirm the cache split.

Each step is independently shippable and reversible.

## Risks

- **First deploy clears the entire DOCX cache.** The `GIT_COMMIT_SHA` invalidation runs at startup and wipes every cached DOCX. Until each (survey, client) pair is re-requested, every request is a DOCX cache miss. PDFs in the cache are untouched, so scraping is not re-triggered. Not a real risk, just informational — same behavior as any other deploy that changes app code.
- **`clients.json` accidentally checked in with wrong CIN / address.** Mitigation: validator logs every loaded client at startup. Future-work: a CI test that runs the library loader and fails the build on validation errors.
- **Adding many clients (>10) makes the dropdown unwieldy.** Out of scope for this change; revisit with a search/filter input if it happens.
