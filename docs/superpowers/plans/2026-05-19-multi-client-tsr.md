# Multi-Client TSR Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the team save lender/client details once in a `clients.json` file and pick the active client from a Streamlit sidebar so TSRs can be generated for any client without editing the document template.

**Architecture:** A new `core/clients.py` module loads a JSON library of clients on startup. The Streamlit sidebar exposes a dropdown; the selected `client_id` flows through the API into `request_metadata`, then into `land_details`, which the existing DOCX template already reads. The GCS cache is split so the scraped PDF stays shared but the generated DOCX is keyed per-client (preventing silent data corruption when two clients share a survey).

**Tech Stack:** Python 3.11, FastAPI, Streamlit, Pydantic, Google Cloud Storage, pytest, python-docx.

**Spec:** [docs/superpowers/specs/2026-05-19-multi-client-tsr-design.md](../specs/2026-05-19-multi-client-tsr-design.md)

---

## File map

| File | Responsibility | New / Modify |
|---|---|---|
| `clients.json` | Repo-root JSON file holding the client library | New |
| `core/clients.py` | `Client` + `ClientLibrary` dataclasses, JSON loader/validator, `get_client_library()` factory | New |
| `tsr_generator/api/tsr_generator_optimized.py` | Copy six new client fields from `request_metadata` to `land_details` | Modify (lines 96–108) |
| `tsr_generator/document/tsr_document.py` | Use `ref_prefix` from `land_details` instead of hardcoded "ABREL" | Modify (line 116) |
| `services/cache_service.py` | Split PDF/DOCX cache methods (per-client DOCX keying) on both `CacheService` and `LocalCacheService` | Modify |
| `api/server.py` | Resolve client from library, merge fields into `request_metadata`, switch to split cache calls | Modify |
| `app/api_client.py` | `process_record()` accepts `client_id` and includes it in the JSON body | Modify |
| `app/streamlit_app_cloud.py` | Sidebar "Active Client" section | Modify |
| `app/components/single_record_form.py` | Pass `st.session_state.active_client_id` to API client; show caption | Modify |
| `app/components/batch_processing_form.py` | Same as above | Modify |
| `tests/test_clients_library.py` | Unit tests for the library loader | New |
| `tests/test_cache_split.py` | Unit tests for the per-client DOCX cache | New |
| `tests/test_server_client_routing.py` | Unit tests for client resolution in the API handler | New |
| `CLAUDE.md` | Note the `clients.json` workflow under "Domain Concepts" | Modify |
| `README.md` | Brief mention of multi-client support and how to add a client | Modify |

---

## Task 1: `core/clients.py` — `Client` dataclass, `ClientLibrary` dataclass, and loader

**Files:**
- Create: `core/clients.py`
- Create: `clients.json`
- Create: `tests/test_clients_library.py`

- [ ] **Step 1: Write failing tests for the loader**

Create `tests/test_clients_library.py`:

```python
"""Tests for the clients library loader."""

import json
import pytest
from pathlib import Path

from core.clients import (
    Client,
    ClientLibrary,
    load_client_library,
)


def _write_clients_file(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "clients.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_loads_valid_library(tmp_path):
    path = _write_clients_file(tmp_path, {
        "default_client_id": "abrel_spv_2",
        "clients": [
            {
                "id": "abrel_spv_2",
                "display_name": "ABREL SPV 2 Limited",
                "client_name": "ABREL SPV 2 Limited",
                "client_cin": "(CIN: U40108MH2020PLC352631),",
                "client_address": "A-2, Aditya Birla Centre,\nWorli, Mumbai-400030.",
                "kind_attn": "Kind Attn.: Mr. Rahul Patil",
                "ref_prefix": "ABREL",
                "reference_email_date": "21.11.2023",
            }
        ],
    })

    lib = load_client_library(path)

    assert lib.default_client_id == "abrel_spv_2"
    assert "abrel_spv_2" in lib.clients
    c = lib.clients["abrel_spv_2"]
    assert c.client_name == "ABREL SPV 2 Limited"
    assert c.ref_prefix == "ABREL"
    assert c.kind_attn == "Kind Attn.: Mr. Rahul Patil"


def test_missing_file_returns_empty_library(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    lib = load_client_library(missing)

    assert lib.clients == {}
    assert lib.default_client_id is None


def test_malformed_json_returns_empty_library(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")

    lib = load_client_library(bad)

    assert lib.clients == {}
    assert lib.default_client_id is None


def test_duplicate_ids_falls_back_to_empty(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            {"id": "dup", "display_name": "A", "client_name": "A", "client_address": "X"},
            {"id": "dup", "display_name": "B", "client_name": "B", "client_address": "Y"},
        ],
    })

    lib = load_client_library(path)

    assert lib.clients == {}
    assert lib.default_client_id is None


def test_unknown_default_falls_back_to_first(tmp_path):
    path = _write_clients_file(tmp_path, {
        "default_client_id": "nonexistent",
        "clients": [
            {"id": "first", "display_name": "First", "client_name": "First Co", "client_address": "X"},
            {"id": "second", "display_name": "Second", "client_name": "Second Co", "client_address": "Y"},
        ],
    })

    lib = load_client_library(path)

    assert lib.default_client_id == "first"
    assert set(lib.clients.keys()) == {"first", "second"}


def test_invalid_id_regex_skips_entry(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            {"id": "valid_id", "display_name": "V", "client_name": "V Co", "client_address": "X"},
            {"id": "BAD ID!", "display_name": "B", "client_name": "B Co", "client_address": "Y"},
        ],
    })

    lib = load_client_library(path)

    assert "valid_id" in lib.clients
    assert "BAD ID!" not in lib.clients


def test_missing_required_fields_skips_entry(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            {"id": "good", "display_name": "G", "client_name": "G", "client_address": "X"},
            {"id": "bad", "display_name": "B"},  # missing client_name, client_address
        ],
    })

    lib = load_client_library(path)

    assert "good" in lib.clients
    assert "bad" not in lib.clients


def test_optional_fields_default_to_none(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            {
                "id": "minimal",
                "display_name": "Minimal Co",
                "client_name": "Minimal Co",
                "client_address": "Somewhere.",
            }
        ],
    })

    lib = load_client_library(path)
    c = lib.clients["minimal"]

    assert c.client_cin is None
    assert c.kind_attn is None
    assert c.ref_prefix is None
    assert c.reference_email_date is None


def test_library_get_returns_default_when_id_unknown(tmp_path):
    path = _write_clients_file(tmp_path, {
        "default_client_id": "primary",
        "clients": [
            {"id": "primary", "display_name": "P", "client_name": "P", "client_address": "X"},
        ],
    })

    lib = load_client_library(path)
    resolved = lib.resolve("does-not-exist")

    assert resolved is not None
    assert resolved.id == "primary"


def test_library_resolve_none_returns_default(tmp_path):
    path = _write_clients_file(tmp_path, {
        "default_client_id": "primary",
        "clients": [
            {"id": "primary", "display_name": "P", "client_name": "P", "client_address": "X"},
        ],
    })

    lib = load_client_library(path)

    assert lib.resolve(None).id == "primary"


def test_empty_library_resolve_returns_none(tmp_path):
    missing = tmp_path / "x.json"
    lib = load_client_library(missing)

    assert lib.resolve("anything") is None
    assert lib.resolve(None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_clients_library.py -v`
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'core.clients'`.

- [ ] **Step 3: Implement `core/clients.py`**

Create `core/clients.py`:

```python
"""
Client library: load and validate clients.json so the team can save
lender/client details and pick the active one from the Streamlit UI.

The file lives at the repo root by default. If it is missing or malformed,
the loader returns an empty library — the DOCX template's hardcoded ABREL
fallback then takes over, preserving existing behavior.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Union


logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9_-]+$")
_REQUIRED_FIELDS = ("id", "display_name", "client_name", "client_address")


@dataclass(frozen=True)
class Client:
    """A single client/lender entry from the library."""

    id: str
    display_name: str
    client_name: str
    client_address: str
    client_cin: Optional[str] = None
    kind_attn: Optional[str] = None
    ref_prefix: Optional[str] = None
    reference_email_date: Optional[str] = None


@dataclass
class ClientLibrary:
    """The full set of clients loaded from clients.json."""

    clients: Dict[str, Client] = field(default_factory=dict)
    default_client_id: Optional[str] = None

    def resolve(self, client_id: Optional[str]) -> Optional[Client]:
        """
        Look up a client by id. If the id is None or unknown, fall back to
        the default client. Returns None only when the library is empty.
        """
        if not self.clients:
            return None
        if client_id and client_id in self.clients:
            return self.clients[client_id]
        if self.default_client_id and self.default_client_id in self.clients:
            return self.clients[self.default_client_id]
        return None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_client_library(path: Union[str, Path, None] = None) -> ClientLibrary:
    """
    Load clients.json and return a validated ClientLibrary.

    Validation failures (missing file, malformed JSON, duplicate ids,
    invalid id chars, missing required fields) never raise — they log
    and return whatever portion of the library is valid. Duplicate ids
    are treated as a hard error and yield an empty library because the
    intent is ambiguous.
    """
    if path is None:
        path = _project_root() / "clients.json"
    path = Path(path)

    if not path.exists():
        logger.warning("clients.json not found at %s — using empty library", path)
        return ClientLibrary()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse %s: %s", path, exc)
        return ClientLibrary()

    raw_clients = raw.get("clients") or []
    if not isinstance(raw_clients, list):
        logger.error("clients.json 'clients' must be a list, got %r", type(raw_clients).__name__)
        return ClientLibrary()

    # First pass: detect duplicate ids
    ids_seen = [entry.get("id") for entry in raw_clients if isinstance(entry, dict)]
    duplicates = {i for i in ids_seen if ids_seen.count(i) > 1 and i}
    if duplicates:
        logger.error("clients.json has duplicate ids %s — returning empty library", duplicates)
        return ClientLibrary()

    clients: Dict[str, Client] = {}
    for idx, entry in enumerate(raw_clients):
        if not isinstance(entry, dict):
            logger.warning("clients[%d] is not an object — skipping", idx)
            continue
        missing = [f for f in _REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            logger.warning("clients[%d] missing required fields %s — skipping", idx, missing)
            continue
        client_id = entry["id"]
        if not _ID_RE.match(client_id):
            logger.warning("clients[%d] id %r does not match %s — skipping", idx, client_id, _ID_RE.pattern)
            continue
        clients[client_id] = Client(
            id=client_id,
            display_name=entry["display_name"],
            client_name=entry["client_name"],
            client_address=entry["client_address"],
            client_cin=entry.get("client_cin") or None,
            kind_attn=entry.get("kind_attn") or None,
            ref_prefix=entry.get("ref_prefix") or None,
            reference_email_date=entry.get("reference_email_date") or None,
        )

    default_id = raw.get("default_client_id")
    if default_id and default_id not in clients:
        logger.warning(
            "default_client_id %r not found in clients — falling back to first entry",
            default_id,
        )
        default_id = None
    if not default_id and clients:
        default_id = next(iter(clients))

    for c in clients.values():
        logger.info("Loaded client: id=%s display_name=%r", c.id, c.display_name)
    if default_id:
        logger.info("Default client: %s", default_id)

    return ClientLibrary(clients=clients, default_client_id=default_id)


@lru_cache(maxsize=1)
def get_client_library() -> ClientLibrary:
    """Singleton accessor — loads once per process."""
    return load_client_library()
```

- [ ] **Step 4: Create `clients.json` at repo root**

Create `clients.json`:

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

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_clients_library.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/clients.py clients.json tests/test_clients_library.py
git commit -m "$(cat <<'EOF'
add core.clients library + clients.json

Loads a JSON-backed client library so the team can save lender details
and pick the active client from the UI. Falls back to an empty library
on any validation error (existing hardcoded ABREL fallback in the DOCX
template still fires). No callers wired up yet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: TSR generator and DOCX template read client fields from `request_metadata`

**Files:**
- Modify: `tsr_generator/api/tsr_generator_optimized.py` (around lines 96–108)
- Modify: `tsr_generator/document/tsr_document.py` (line 116)

This task makes the TSR generator able to receive client fields. Existing callers don't pass them yet, so behavior is unchanged. Once Task 4 wires the API handler, the fields will start flowing.

- [ ] **Step 1: Extend the `request_metadata` → `land_details` block**

In [tsr_generator/api/tsr_generator_optimized.py](tsr_generator/api/tsr_generator_optimized.py:96), find the existing block:

```python
        # Override land details with request metadata if provided
        old_survey = None
        if request_metadata:
            if request_metadata.get('survey_number'):
                old_survey = land_details.get('survey_number', '')
                land_details['survey_number'] = request_metadata['survey_number']
                logger.info(f"Overriding survey_number: '{old_survey}' -> '{request_metadata['survey_number']}'")
            if request_metadata.get('village'):
                land_details['village_name'] = request_metadata['village']
            if request_metadata.get('taluka'):
                land_details['taluka_name'] = request_metadata['taluka']
            if request_metadata.get('district'):
                land_details['district_name'] = request_metadata['district']
```

Add the six client fields immediately after the `district` line, inside the same `if request_metadata:` guard:

```python
            for client_field in (
                'client_name',
                'client_cin',
                'client_address',
                'kind_attn',
                'ref_prefix',
                'reference_email_date',
            ):
                if request_metadata.get(client_field):
                    land_details[client_field] = request_metadata[client_field]
```

- [ ] **Step 2: Replace the hardcoded "ABREL" reference prefix in the DOCX template**

In [tsr_generator/document/tsr_document.py:116](tsr_generator/document/tsr_document.py:116), find this block:

```python
        if profile == "final_sample_v1":
            report_date = sanitize_text(land_details.get("report_date")) or current_date
            ref_text_val = f"Ref. No. ABREL/GUJ/{taluka_prefix}/{village_prefix}/{survey_number}\t\t\t\tDated :{report_date}"
        else:
            ref_text_val = f"Ref. No. ABREL/GUJ/{district_prefix}/{taluka_prefix}/{village_prefix}/{survey_number}                    Dated: {current_date}"
```

Replace it with:

```python
        ref_prefix = sanitize_text(land_details.get("ref_prefix")) or "ABREL"
        if profile == "final_sample_v1":
            report_date = sanitize_text(land_details.get("report_date")) or current_date
            ref_text_val = f"Ref. No. {ref_prefix}/GUJ/{taluka_prefix}/{village_prefix}/{survey_number}\t\t\t\tDated :{report_date}"
        else:
            ref_text_val = f"Ref. No. {ref_prefix}/GUJ/{district_prefix}/{taluka_prefix}/{village_prefix}/{survey_number}                    Dated: {current_date}"
```

- [ ] **Step 3: Sanity-check the existing test suite still passes**

Run: `pytest tests/ -v --ignore=tests/test_clients_library.py -k "not integration"`
Expected: Same passing/failing state as before this commit (no new failures from these edits).

If any tests reference `"ABREL/GUJ/"` as a literal, they will fail. Search before running:

Run: `grep -rn "ABREL/GUJ" tests/ tsr_generator/ 2>/dev/null`
Expected: only the two ref_text_val lines you just edited, nothing in tests.

- [ ] **Step 4: Commit**

```bash
git add tsr_generator/api/tsr_generator_optimized.py tsr_generator/document/tsr_document.py
git commit -m "$(cat <<'EOF'
thread client fields through TSR generator

Extend request_metadata → land_details to copy six client fields
(client_name, client_cin, client_address, kind_attn, ref_prefix,
reference_email_date). The DOCX template already reads these keys
via .get() with hardcoded ABREL fallbacks, so this is a no-op until
the API starts passing them. Also replace the hardcoded "ABREL/GUJ/"
report-reference prefix with land_details.ref_prefix (still falls
back to "ABREL").

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Cache service — split into per-PDF and per-(PDF, client) DOCX

**Files:**
- Modify: `services/cache_service.py`
- Create: `tests/test_cache_split.py`

Both `CacheService` (GCS-backed) and `LocalCacheService` (filesystem-backed) need the new methods. We test against `LocalCacheService` because it doesn't require GCS — same interface, real I/O via `tmp_path`.

- [ ] **Step 1: Write failing tests for the split cache**

Create `tests/test_cache_split.py`:

```python
"""Tests for the per-client DOCX cache split."""

import pytest

from core.models import LandRecordRequest
from services.cache_service import LocalCacheService


@pytest.fixture
def cache(tmp_path):
    return LocalCacheService(cache_dir=str(tmp_path))


@pytest.fixture
def request_kutch():
    return LandRecordRequest(
        district="Kutch", taluka="Abdasa", village="Trambo", survey_number="150"
    )


def _key(cache):
    # Use translated-style keying (same as production); content doesn't matter here.
    return cache.generate_cache_key_from_translated(
        translated_district="કચ્છ",
        translated_taluka="અબડાસા",
        translated_village="ત્રંબો - 033",
        survey_number="150",
    )


def test_pdf_cache_miss_then_hit(cache):
    pdf_key = _key(cache)

    assert cache.get_cached_pdf_by_key(pdf_key) is None

    cache.cache_pdf_by_key(pdf_key, b"PDFBYTES")

    assert cache.get_cached_pdf_by_key(pdf_key) == b"PDFBYTES"


def test_docx_cache_is_per_client(cache, request_kutch):
    pdf_key = _key(cache)
    cache.cache_pdf_by_key(pdf_key, b"PDFBYTES")

    cache.cache_docx_by_key(
        pdf_key=pdf_key,
        client_id="client_a",
        original_request=request_kutch,
        translated_district="કચ્છ",
        translated_taluka="અબડાસા",
        translated_village="ત્રંબો - 033",
        docx_content=b"DOCX_FOR_A",
    )
    cache.cache_docx_by_key(
        pdf_key=pdf_key,
        client_id="client_b",
        original_request=request_kutch,
        translated_district="કચ્છ",
        translated_taluka="અબડાસા",
        translated_village="ત્રંબો - 033",
        docx_content=b"DOCX_FOR_B",
    )

    assert cache.get_cached_docx_by_key(pdf_key, "client_a") == b"DOCX_FOR_A"
    assert cache.get_cached_docx_by_key(pdf_key, "client_b") == b"DOCX_FOR_B"
    assert cache.get_cached_pdf_by_key(pdf_key) == b"PDFBYTES"


def test_docx_miss_when_pdf_hit(cache, request_kutch):
    pdf_key = _key(cache)
    cache.cache_pdf_by_key(pdf_key, b"PDFBYTES")

    # Cache the DOCX for one client only
    cache.cache_docx_by_key(
        pdf_key=pdf_key,
        client_id="client_a",
        original_request=request_kutch,
        translated_district="કચ્છ",
        translated_taluka="અબડાસા",
        translated_village="ત્રંબો - 033",
        docx_content=b"DOCX_FOR_A",
    )

    # Different client → DOCX miss
    assert cache.get_cached_docx_by_key(pdf_key, "client_b") is None
    # Same key → PDF still hits (separate layer)
    assert cache.get_cached_pdf_by_key(pdf_key) == b"PDFBYTES"


def test_docx_cache_miss_returns_none(cache):
    assert cache.get_cached_docx_by_key("nonexistent_key", "any_client") is None


def test_pdf_cache_miss_returns_none(cache):
    assert cache.get_cached_pdf_by_key("nonexistent_key") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cache_split.py -v`
Expected: All FAIL with `AttributeError: 'LocalCacheService' object has no attribute 'cache_pdf_by_key'` (or similar).

- [ ] **Step 3: Add the four new methods to `LocalCacheService`**

In [services/cache_service.py](services/cache_service.py), add these methods to `LocalCacheService` (after `cache_record_by_key`):

```python
    # ---- Per-PDF / per-client split cache ----

    def get_cached_pdf_by_key(self, pdf_key: str) -> Optional[bytes]:
        """Return the cached PDF bytes for this location key, or None on miss/expiry."""
        entry = self._entry_dir(pdf_key)
        metadata_path = os.path.join(entry, "metadata.json")
        pdf_path = os.path.join(entry, "original.pdf")

        if not os.path.exists(metadata_path) or not os.path.exists(pdf_path):
            return None
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not read local cache metadata: {e}")
            return None
        if not self._is_cache_valid(metadata):
            self.logger.info(f"Local PDF cache expired for key {pdf_key}")
            self._cleanup_cache(pdf_key)
            return None
        with open(pdf_path, "rb") as f:
            return f.read()

    def cache_pdf_by_key(self, pdf_key: str, pdf_content: bytes) -> bool:
        """Store the PDF under this location key. Creates a metadata.json if absent."""
        try:
            entry = self._entry_dir(pdf_key)
            os.makedirs(entry, exist_ok=True)

            metadata_path = os.path.join(entry, "metadata.json")
            if not os.path.exists(metadata_path):
                metadata = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ttl_days": self.ttl_days,
                }
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

            with open(os.path.join(entry, "original.pdf"), "wb") as f:
                f.write(pdf_content)
            self.logger.info(f"Locally cached PDF {pdf_key}: {len(pdf_content)} bytes")
            return True
        except Exception as e:
            self.logger.error(f"Failed to write local PDF cache: {e}")
            return False

    def get_cached_docx_by_key(self, pdf_key: str, client_id: str) -> Optional[bytes]:
        """Return the cached DOCX bytes for this (location, client) pair, or None on miss."""
        entry = self._entry_dir(pdf_key)
        metadata_path = os.path.join(entry, "metadata.json")
        docx_path = os.path.join(entry, f"docx_{client_id}.docx")

        if not os.path.exists(metadata_path) or not os.path.exists(docx_path):
            return None
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not read local cache metadata: {e}")
            return None
        if not self._is_cache_valid(metadata):
            self.logger.info(f"Local DOCX cache expired for key {pdf_key}")
            self._cleanup_cache(pdf_key)
            return None
        with open(docx_path, "rb") as f:
            return f.read()

    def cache_docx_by_key(
        self,
        pdf_key: str,
        client_id: str,
        original_request: LandRecordRequest,
        translated_district: str,
        translated_taluka: str,
        translated_village: str,
        docx_content: bytes,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store the DOCX under cache/{pdf_key}/docx_{client_id}.docx."""
        try:
            entry = self._entry_dir(pdf_key)
            os.makedirs(entry, exist_ok=True)

            metadata_path = os.path.join(entry, "metadata.json")
            metadata: Dict[str, Any] = {}
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                except Exception:
                    metadata = {}

            metadata.update({
                "timestamp": metadata.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                "original_district": original_request.district,
                "original_taluka": original_request.taluka,
                "original_village": original_request.village,
                "survey_number": original_request.survey_number,
                "translated_district": translated_district,
                "translated_taluka": translated_taluka,
                "translated_village": translated_village,
                "ttl_days": self.ttl_days,
                **(additional_metadata or {}),
            })
            docx_versions = metadata.get("docx_versions") or {}
            docx_versions[client_id] = datetime.now(timezone.utc).isoformat()
            metadata["docx_versions"] = docx_versions

            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            with open(os.path.join(entry, f"docx_{client_id}.docx"), "wb") as f:
                f.write(docx_content)
            self.logger.info(
                f"Locally cached DOCX {pdf_key}/docx_{client_id}: {len(docx_content)} bytes"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to write local DOCX cache: {e}")
            return False
```

- [ ] **Step 4: Add the same four methods to `CacheService` (GCS-backed)**

Still in [services/cache_service.py](services/cache_service.py), add these to the `CacheService` class (after `cache_record_by_key`):

```python
    # ---- Per-PDF / per-client split cache ----

    def get_cached_pdf_by_key(self, pdf_key: str) -> Optional[bytes]:
        """Return the cached PDF bytes for this location key, or None on miss/expiry."""
        try:
            metadata_blob = self._bucket.blob(self._get_cache_path(pdf_key, "metadata.json"))
            pdf_blob = self._bucket.blob(self._get_cache_path(pdf_key, "original.pdf"))
            if not metadata_blob.exists() or not pdf_blob.exists():
                return None
            metadata = json.loads(metadata_blob.download_as_text())
            if not self._is_cache_valid(metadata):
                self.logger.info(f"PDF cache expired for key {pdf_key}")
                self._cleanup_cache(pdf_key)
                return None
            return pdf_blob.download_as_bytes()
        except NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error reading PDF cache: {e}")
            return None

    def cache_pdf_by_key(self, pdf_key: str, pdf_content: bytes) -> bool:
        """Store the PDF under this location key. Creates a metadata.json if absent."""
        try:
            metadata_path = self._get_cache_path(pdf_key, "metadata.json")
            metadata_blob = self._bucket.blob(metadata_path)
            if not metadata_blob.exists():
                metadata = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ttl_days": self.ttl_days,
                }
                metadata_blob.upload_from_string(
                    json.dumps(metadata, indent=2, ensure_ascii=False),
                    content_type="application/json",
                )

            pdf_blob = self._bucket.blob(self._get_cache_path(pdf_key, "original.pdf"))
            pdf_blob.upload_from_string(pdf_content, content_type="application/pdf")
            self.logger.info(f"Cached PDF {pdf_key}: {len(pdf_content)} bytes")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cache PDF: {e}")
            return False

    def get_cached_docx_by_key(self, pdf_key: str, client_id: str) -> Optional[bytes]:
        """Return the cached DOCX bytes for this (location, client) pair, or None on miss."""
        try:
            metadata_blob = self._bucket.blob(self._get_cache_path(pdf_key, "metadata.json"))
            docx_blob = self._bucket.blob(self._get_cache_path(pdf_key, f"docx_{client_id}.docx"))
            if not metadata_blob.exists() or not docx_blob.exists():
                return None
            metadata = json.loads(metadata_blob.download_as_text())
            if not self._is_cache_valid(metadata):
                self.logger.info(f"DOCX cache expired for key {pdf_key}")
                self._cleanup_cache(pdf_key)
                return None
            return docx_blob.download_as_bytes()
        except NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error reading DOCX cache: {e}")
            return None

    def cache_docx_by_key(
        self,
        pdf_key: str,
        client_id: str,
        original_request: LandRecordRequest,
        translated_district: str,
        translated_taluka: str,
        translated_village: str,
        docx_content: bytes,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store the DOCX under cache/{pdf_key}/docx_{client_id}.docx."""
        try:
            metadata_path = self._get_cache_path(pdf_key, "metadata.json")
            metadata_blob = self._bucket.blob(metadata_path)
            metadata: Dict[str, Any] = {}
            if metadata_blob.exists():
                try:
                    metadata = json.loads(metadata_blob.download_as_text())
                except Exception:
                    metadata = {}
            metadata.update({
                "timestamp": metadata.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                "original_district": original_request.district,
                "original_taluka": original_request.taluka,
                "original_village": original_request.village,
                "survey_number": original_request.survey_number,
                "translated_district": translated_district,
                "translated_taluka": translated_taluka,
                "translated_village": translated_village,
                "ttl_days": self.ttl_days,
                **(additional_metadata or {}),
            })
            docx_versions = metadata.get("docx_versions") or {}
            docx_versions[client_id] = datetime.now(timezone.utc).isoformat()
            metadata["docx_versions"] = docx_versions

            metadata_blob.upload_from_string(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                content_type="application/json",
            )

            docx_blob = self._bucket.blob(self._get_cache_path(pdf_key, f"docx_{client_id}.docx"))
            docx_blob.upload_from_string(
                docx_content,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            self.logger.info(
                f"Cached DOCX {pdf_key}/docx_{client_id}: {len(docx_content)} bytes"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to cache DOCX: {e}")
            return False
```

- [ ] **Step 5: Update `clear_all_docx_cache` to also delete the new `docx_*.docx` files**

In [services/cache_service.py](services/cache_service.py), find `clear_all_docx_cache` on the `CacheService` class and update the inner loop:

```python
            for b in blobs:
                name = b.name
                # Old combined key OR new per-client key
                if name.endswith("tsr.docx") or "/docx_" in name and name.endswith(".docx"):
                    try:
                        b.delete()
                        deleted_count += 1
```

This ensures the existing `GIT_COMMIT_SHA` invalidation also wipes the new per-client DOCX files on a version bump.

- [ ] **Step 6: Run cache split tests to verify they pass**

Run: `pytest tests/test_cache_split.py -v`
Expected: 5 PASS.

- [ ] **Step 7: Run the full suite to verify nothing else broke**

Run: `pytest tests/ -v -k "not integration"`
Expected: All previously-passing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add services/cache_service.py tests/test_cache_split.py
git commit -m "$(cat <<'EOF'
split GCS cache: PDF shared, DOCX per-client

Add get_cached_pdf_by_key/cache_pdf_by_key and
get_cached_docx_by_key/cache_docx_by_key on both CacheService and
LocalCacheService. The PDF stays shared across clients (scraping is
the expensive step), but DOCX is now keyed by (location, client_id)
under docx_{client_id}.docx. Without this, two clients sharing a
survey would silently get each other's DOCX. Also extend
clear_all_docx_cache to wipe the new per-client files on version bump.
The API handler is updated to use these methods in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: API handler resolves client and uses the split cache

**Files:**
- Modify: `api/server.py` (request model + `/process-record` handler)
- Create: `tests/test_server_client_routing.py`

- [ ] **Step 1: Write failing tests for client resolution**

Create `tests/test_server_client_routing.py`:

```python
"""Tests for the _build_request_metadata_for_client helper in api/server.py.

The library resolve() logic itself is exercised in test_clients_library.py;
here we focus on the server-side merging behavior.
"""

import pytest

from core.clients import Client, ClientLibrary


@pytest.fixture
def sample_library():
    abrel = Client(
        id="abrel_spv_2",
        display_name="ABREL",
        client_name="ABREL SPV 2 Limited",
        client_address="A-2, Aditya Birla Centre.",
        client_cin="(CIN: ...)",
        kind_attn="Kind Attn.: Mr. Rahul Patil",
        ref_prefix="ABREL",
        reference_email_date="21.11.2023",
    )
    other = Client(
        id="other_client",
        display_name="Other",
        client_name="Other Co",
        client_address="Somewhere else.",
    )
    return ClientLibrary(
        clients={"abrel_spv_2": abrel, "other_client": other},
        default_client_id="abrel_spv_2",
    )


def test_request_metadata_includes_resolved_client_fields(sample_library):
    """The handler logic that builds _request_metadata should merge non-None client fields."""
    from api.server import _build_request_metadata_for_client

    metadata = _build_request_metadata_for_client(
        district="Kutch",
        taluka="Abdasa",
        village="Trambo",
        survey_number="150",
        client=sample_library.resolve("abrel_spv_2"),
    )

    assert metadata["district"] == "Kutch"
    assert metadata["client_name"] == "ABREL SPV 2 Limited"
    assert metadata["ref_prefix"] == "ABREL"
    assert metadata["kind_attn"] == "Kind Attn.: Mr. Rahul Patil"


def test_request_metadata_skips_none_client_fields(sample_library):
    """Optional client fields that are None should not be added to request_metadata."""
    from api.server import _build_request_metadata_for_client

    metadata = _build_request_metadata_for_client(
        district="Kutch",
        taluka="Abdasa",
        village="Trambo",
        survey_number="150",
        client=sample_library.resolve("other_client"),  # has only required fields
    )

    assert metadata["client_name"] == "Other Co"
    assert "client_cin" not in metadata
    assert "kind_attn" not in metadata
    assert "ref_prefix" not in metadata


def test_request_metadata_no_client_passes_geography_only():
    """When client is None (empty library), only geography is in request_metadata."""
    from api.server import _build_request_metadata_for_client

    metadata = _build_request_metadata_for_client(
        district="Kutch",
        taluka="Abdasa",
        village="Trambo",
        survey_number="150",
        client=None,
    )

    assert metadata == {
        "district": "Kutch",
        "taluka": "Abdasa",
        "village": "Trambo",
        "survey_number": "150",
    }


def test_unknown_client_id_falls_back_to_default(sample_library):
    """Server-side fallback path: unknown id → default client, surfaced via library.resolve."""
    resolved = sample_library.resolve("does-not-exist")
    assert resolved is not None
    assert resolved.id == "abrel_spv_2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server_client_routing.py -v`
Expected: All 4 tests FAIL with `ImportError: cannot import name '_build_request_metadata_for_client' from 'api.server'`.

- [ ] **Step 3: Extend the `LandRecordRequest` Pydantic model**

In [api/server.py](api/server.py:90), find:

```python
class LandRecordRequest(BaseModel):
    """Pydantic model for API request validation."""
    district: str
    taluka: str
    village: str
    survey_number: str
    output_format: str = "zip"  # Added to support returning just docx
```

Replace with:

```python
from typing import Optional

class LandRecordRequest(BaseModel):
    """Pydantic model for API request validation."""
    district: str
    taluka: str
    village: str
    survey_number: str
    output_format: str = "zip"  # Added to support returning just docx
    client_id: Optional[str] = None  # Picks a client from clients.json
```

(If `Optional` is already imported elsewhere in the file, skip the import line.)

- [ ] **Step 4: Add the helper function and wire client resolution into the handler**

In [api/server.py](api/server.py), add this helper near the top of the module (after the imports, before route definitions):

```python
from core.clients import Client, get_client_library


def _build_request_metadata_for_client(
    district: str,
    taluka: str,
    village: str,
    survey_number: str,
    client: Optional[Client],
) -> dict:
    """Build the request_metadata dict, merging in only non-None client fields."""
    metadata = {
        "district": district,
        "taluka": taluka,
        "village": village,
        "survey_number": survey_number,
    }
    if client is not None:
        for field in (
            "client_name",
            "client_cin",
            "client_address",
            "kind_attn",
            "ref_prefix",
            "reference_email_date",
        ):
            value = getattr(client, field)
            if value:
                metadata[field] = value
    return metadata
```

Then in the `/process-record` handler, replace the existing block that builds `_request_metadata` around [api/server.py:364](api/server.py:364):

```python
        # Generate TSR (lazy load to improve startup time)
        logger.info(f"Starting TSR generation from PDF: {pdf_path}")
        generate_tsr = get_tsr_generator()
        _request_metadata = {
            'district': request.district,
            'taluka': request.taluka,
            'village': request.village,
            'survey_number': request.survey_number
        }
        tsr_result = generate_tsr(pdf_path, docx_path, logger, request_metadata=_request_metadata)
```

With:

```python
        # Resolve client from library (unknown / None → default)
        client_library = get_client_library()
        resolved_client = client_library.resolve(request.client_id)
        if request.client_id and (resolved_client is None or resolved_client.id != request.client_id):
            logger.warning(
                "Unknown client_id %r — falling back to default (%s)",
                request.client_id,
                resolved_client.id if resolved_client else None,
            )

        # Generate TSR (lazy load to improve startup time)
        logger.info(f"Starting TSR generation from PDF: {pdf_path}")
        generate_tsr = get_tsr_generator()
        _request_metadata = _build_request_metadata_for_client(
            district=request.district,
            taluka=request.taluka,
            village=request.village,
            survey_number=request.survey_number,
            client=resolved_client,
        )
        tsr_result = generate_tsr(pdf_path, docx_path, logger, request_metadata=_request_metadata)
```

- [ ] **Step 5: Switch the cache lookups and writes to the split-cache API**

Still in [api/server.py](api/server.py), the `/process-record` handler has a cache-check block around line 244 and a cache-store block around line 401. Replace them as follows.

**Cache check (replace the existing block):**

Old:
```python
    if cache_service is not None:
        try:
            cache_key = cache_service.generate_cache_key_from_translated(...)
            cached_result = cache_service.get_cached_record_by_key(cache_key)
            if cached_result is not None:
                ...
```

New (this fully replaces the existing cache-check block; the inner logic that builds the HTTP response from `docx_content`/`pdf_content` stays the same, only the lookup changes):

```python
    pdf_key = None
    cached_pdf_content: Optional[bytes] = None
    cached_docx_content: Optional[bytes] = None
    if cache_service is not None:
        try:
            pdf_key = cache_service.generate_cache_key_from_translated(
                translated_district=district_guj,
                translated_taluka=taluka_guj,
                translated_village=village_guj,
                survey_number=request.survey_number,
            )

            cached_pdf_content = cache_service.get_cached_pdf_by_key(pdf_key)
            if resolved_client is not None:
                cached_docx_content = cache_service.get_cached_docx_by_key(
                    pdf_key, resolved_client.id
                )

            if cached_pdf_content is not None and cached_docx_content is not None:
                import time; time.sleep(5)
                logger.info(
                    "✅ FULL CACHE HIT for %s/%s/%s/%s (client=%s)",
                    request.district, request.taluka, request.village,
                    request.survey_number, resolved_client.id if resolved_client else None,
                )

                docx_filename = file_service.generate_filename(core_request, file_type='docx', prefix='TSR')
                pdf_filename = file_service.generate_filename(core_request, file_type='pdf', prefix='Original')
                zip_filename = file_service.generate_filename(core_request, file_type='zip', prefix='TSR_Package')

                if getattr(request, 'output_format', 'zip') == 'docx':
                    encoded_filename = quote(docx_filename)
                    return Response(
                        content=cached_docx_content,
                        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        headers={
                            'Content-Disposition': f"attachment; filename=\"{docx_filename}\"; filename*=UTF-8''{encoded_filename}",
                            'X-Cache-Status': 'HIT',
                        }
                    )
                files_to_zip = {docx_filename: cached_docx_content}
                if cached_pdf_content:
                    files_to_zip[pdf_filename] = cached_pdf_content
                zip_content = file_service.create_zip(files_to_zip, zip_filename)
                encoded_filename = quote(zip_filename)
                zip_filename_ascii = f"TSR_Package_{os.urandom(4).hex()}.zip"
                return Response(
                    content=zip_content,
                    media_type='application/zip',
                    headers={
                        'Content-Disposition': f"attachment; filename=\"{zip_filename_ascii}\"; filename*=UTF-8''{encoded_filename}",
                        'X-Cache-Status': 'HIT',
                    }
                )

            if cached_pdf_content is not None:
                logger.info(
                    "🟡 PARTIAL CACHE HIT (PDF hit, DOCX miss) for %s/%s/%s/%s (client=%s)",
                    request.district, request.taluka, request.village,
                    request.survey_number, resolved_client.id if resolved_client else None,
                )
            else:
                logger.info(
                    "❌ CACHE MISS for %s/%s/%s/%s",
                    request.district, request.taluka, request.village, request.survey_number,
                )
        except Exception as e:
            logger.warning(f"Cache check failed, proceeding without cache: {e}")
            pdf_key = None
            cached_pdf_content = None
            cached_docx_content = None
```

**Scraping skip when PDF is cached:** Just before the existing scraping call (`scraping_service.fetch_land_record(...)`), add:

```python
        if cached_pdf_content is not None:
            with open(pdf_path, "wb") as f:
                f.write(cached_pdf_content)
            logger.info(f"Wrote cached PDF to {pdf_path}, skipping scrape")
        else:
            logger.info(
                f"Calling scraper with: district='{district_guj}', taluka='{taluka_guj}', "
                f"village='{village_guj}', survey='{request.survey_number}'"
            )
            result = scraping_service.fetch_land_record(
                district=district_guj,
                taluka=taluka_guj,
                village=village_guj,
                survey_number=request.survey_number,
                output_path=pdf_path
            )
            if not result.get('success'):
                logger.error(f"Scraping failed with result: {result}")
                raise HTTPException(status_code=500, detail=f"Scraping failed: {result.get('error')}")
```

(This replaces the existing `logger.info(f"Calling scraper...")` block and the `result = scraping_service.fetch_land_record(...)` / `if not result.get('success'):` block in one swap. Keep all the surrounding logging/diagnostics after.)

**Cache store (replace the existing block at ~line 401):**

Old:
```python
        if cache_service is not None:
            try:
                cache_service.cache_record_by_key(
                    cache_key=cache_key,
                    original_request=core_request,
                    translated_district=district_guj,
                    translated_taluka=taluka_guj,
                    translated_village=village_guj,
                    docx_content=docx_content,
                    pdf_content=pdf_content
                )
```

New:
```python
        if cache_service is not None and pdf_key is not None:
            try:
                if cached_pdf_content is None and pdf_content:
                    cache_service.cache_pdf_by_key(pdf_key, pdf_content)
                if resolved_client is not None:
                    cache_service.cache_docx_by_key(
                        pdf_key=pdf_key,
                        client_id=resolved_client.id,
                        original_request=core_request,
                        translated_district=district_guj,
                        translated_taluka=taluka_guj,
                        translated_village=village_guj,
                        docx_content=docx_content,
                    )
                logger.info(
                    "💾 CACHED PDF + DOCX for %s/%s/%s/%s (client=%s)",
                    request.district, request.taluka, request.village,
                    request.survey_number, resolved_client.id if resolved_client else None,
                )
            except Exception as e:
                logger.warning(f"Failed to cache record: {e}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_server_client_routing.py tests/test_clients_library.py tests/test_cache_split.py -v`
Expected: All PASS.

- [ ] **Step 7: Run the full test suite**

Run: `pytest tests/ -v -k "not integration"`
Expected: All previously-passing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add api/server.py tests/test_server_client_routing.py
git commit -m "$(cat <<'EOF'
resolve client_id in /process-record and use split cache

Extend LandRecordRequest with an optional client_id, resolve it from
the clients library (None / unknown → default client, no 400),
and merge non-None client fields into request_metadata. Replace
the combined cache get/store with the new split API: PDF stays
shared across clients, DOCX is keyed per-client. PARTIAL HIT
(PDF cached, DOCX miss) skips scraping but still re-generates
the DOCX. Adds _build_request_metadata_for_client helper for unit
testing the merge logic.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: API client (Streamlit-side) accepts `client_id`

**Files:**
- Modify: `app/api_client.py`

- [ ] **Step 1: Extend `TSRAPIClient.process_record()`**

In [app/api_client.py:62](app/api_client.py:62), find:

```python
    def process_record(
        self,
        district: str,
        taluka: str,
        village: str,
        survey_number: str
    ) -> APIResponse:
```

Replace with:

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

Then update the `payload` block below it:

```python
        payload = {
            "district": district,
            "taluka": taluka,
            "village": village,
            "survey_number": survey_number
        }
        if client_id:
            payload["client_id"] = client_id
```

- [ ] **Step 2: Sanity-check imports**

`Optional` should already be imported from `typing` (verify the top of the file). If not, add it.

- [ ] **Step 3: Commit**

```bash
git add app/api_client.py
git commit -m "$(cat <<'EOF'
TSRAPIClient.process_record accepts client_id

Optional kwarg. Sent in the JSON body when provided. Callers updated
in the next two commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Streamlit sidebar — "Active Client" picker

**Files:**
- Modify: `app/streamlit_app_cloud.py`

- [ ] **Step 1: Add a helper function for the sidebar and call it from the main flow**

In [app/streamlit_app_cloud.py](app/streamlit_app_cloud.py), add this import near the other imports:

```python
from core.clients import get_client_library
```

Then add this helper function before the `# Main UI` section (after the file_service init around line 74):

```python
def _render_client_sidebar() -> None:
    """Render the 'Active Client' picker in the sidebar."""
    library = get_client_library()

    with st.sidebar:
        st.markdown("### Active Client")
        if not library.clients:
            st.warning(
                "No clients.json found. Falling back to hardcoded ABREL defaults. "
                "Add clients.json to the repo root to enable the picker."
            )
            st.session_state.active_client_id = None
            return

        client_ids = list(library.clients.keys())
        display_names = [library.clients[cid].display_name for cid in client_ids]

        # Pre-select default (or first) the very first time
        if "active_client_id" not in st.session_state:
            st.session_state.active_client_id = (
                library.default_client_id or client_ids[0]
            )

        current_idx = (
            client_ids.index(st.session_state.active_client_id)
            if st.session_state.active_client_id in client_ids
            else 0
        )

        selected_idx = st.selectbox(
            "Generating TSR for",
            options=range(len(client_ids)),
            format_func=lambda i: display_names[i],
            index=current_idx,
            key="sidebar_client_selector",
        )
        st.session_state.active_client_id = client_ids[selected_idx]

        selected = library.clients[st.session_state.active_client_id]
        with st.expander("View details", expanded=False):
            st.write(f"**Name:** {selected.client_name}")
            if selected.client_cin:
                st.write(f"**CIN:** {selected.client_cin}")
            st.write(f"**Address:** {selected.client_address}")
            if selected.kind_attn:
                st.write(f"**Attn:** {selected.kind_attn}")
            st.write(f"**Ref prefix:** {selected.ref_prefix or 'ABREL'}")

        st.caption("To add or edit a client, edit `clients.json` and redeploy.")
```

Then call it right before the `# Main UI – three tabs delegating to components` line:

```python
_render_client_sidebar()

# Main UI – three tabs delegating to components
tab1, tab2, tab3 = st.tabs(["📄 Single Record", "📊 Batch (Excel)", "📋 Results"])
```

- [ ] **Step 2: Smoke test the Streamlit UI locally**

Run: `streamlit run app/streamlit_app_cloud.py`
Expected: page opens, sidebar shows "Active Client" with a dropdown listing "ABREL SPV 2 Limited (Aditya Birla)". Expander shows the client's details. (Stop the server with Ctrl-C when done.)

If `streamlit` is not on PATH, run: `python -m streamlit run app/streamlit_app_cloud.py`.

- [ ] **Step 3: Commit**

```bash
git add app/streamlit_app_cloud.py
git commit -m "$(cat <<'EOF'
sidebar 'Active Client' dropdown in Streamlit

Reads clients.json via get_client_library() and stores the selected
client id in st.session_state.active_client_id. Both tabs will use it
once the next two commits wire the forms.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Single Record form uses the active client

**Files:**
- Modify: `app/components/single_record_form.py`

- [ ] **Step 1: Pass `client_id` through to the API**

In [app/components/single_record_form.py:64](app/components/single_record_form.py:64), find:

```python
            result = process_single_record_api(
                api_client, district, taluka, village, normalized_survey
            )
```

Replace with:

```python
            result = process_single_record_api(
                api_client,
                district,
                taluka,
                village,
                normalized_survey,
                client_id=st.session_state.get("active_client_id"),
            )
```

Then update the `process_single_record_api` signature at the bottom of the file:

```python
def process_single_record_api(
    client: TSRAPIClient,
    district: str,
    taluka: str,
    village: str,
    survey: str,
    client_id: Optional[str] = None,
) -> dict:
```

And use it:

```python
        response: APIResponse = client.process_record(
            district=district,
            taluka=taluka,
            village=village,
            survey_number=survey,
            client_id=client_id,
        )
```

Add `from typing import Optional` near the top of the file if it's not already imported.

- [ ] **Step 2: Add a caption above the form**

Just below the `st.subheader("Process Single Land Record")` line in [app/components/single_record_form.py:47](app/components/single_record_form.py:47), add:

```python
    active_client_id = st.session_state.get("active_client_id")
    if active_client_id:
        from core.clients import get_client_library
        lib = get_client_library()
        client = lib.clients.get(active_client_id)
        if client:
            st.caption(f"Generating TSR for: **{client.client_name}**")
```

- [ ] **Step 3: Smoke test**

Run: `streamlit run app/streamlit_app_cloud.py`
Expected: the single-record tab shows "Generating TSR for: **ABREL SPV 2 Limited**" above the form. (Don't actually click Generate unless you want to exercise the real backend.)

- [ ] **Step 4: Commit**

```bash
git add app/components/single_record_form.py
git commit -m "$(cat <<'EOF'
single-record form passes active client_id

Reads st.session_state.active_client_id (set by the sidebar) and
forwards it to TSRAPIClient.process_record. Adds a 'Generating TSR
for: <client>' caption so the user is never confused about which
client a click will use.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Batch processing form uses the active client

**Files:**
- Modify: `app/components/batch_processing_form.py`

- [ ] **Step 1: Pass `client_id` through the batch flow**

In [app/components/batch_processing_form.py](app/components/batch_processing_form.py), find the `_process_batch` function and update the call to `_process_single_record` inside the `ThreadPoolExecutor` block:

```python
            future = executor.submit(
                _process_single_record,
                api_client,
                str(row[district_col]).strip(),
                str(row[taluka_col]).strip(),
                str(row[village_col]).strip(),
                survey_number,
                idx + start_row,  # Original row index
                st.session_state.get("active_client_id"),
            )
```

Update the `_process_single_record` signature:

```python
def _process_single_record(
    client: TSRAPIClient,
    district: str,
    taluka: str,
    village: str,
    survey: str,
    row_idx: int,
    client_id: Optional[str] = None,
) -> Dict[str, Any]:
```

And inside it, pass `client_id` to `client.process_record(...)`:

```python
        response: APIResponse = client.process_record(
            district=district,
            taluka=taluka,
            village=village,
            survey_number=survey,
            client_id=client_id,
        )
```

Do the same in `_retry_failed_entries` — pass `st.session_state.get("active_client_id")` as the last arg to `_process_single_record`.

`Optional` is already imported at the top of the file via `from typing import Optional`.

- [ ] **Step 2: Add a caption above the batch form**

Just below the `st.subheader("📊 Batch Processing (Excel)")` line in [app/components/batch_processing_form.py:34](app/components/batch_processing_form.py:34), add the same caption pattern as Task 7:

```python
    active_client_id = st.session_state.get("active_client_id")
    if active_client_id:
        from core.clients import get_client_library
        lib = get_client_library()
        client = lib.clients.get(active_client_id)
        if client:
            st.caption(f"Batch will generate TSRs for: **{client.client_name}**")
```

- [ ] **Step 3: Smoke test**

Run: `streamlit run app/streamlit_app_cloud.py`
Expected: the batch tab shows "Batch will generate TSRs for: **ABREL SPV 2 Limited**". Switching the sidebar dropdown changes the caption on both tabs.

- [ ] **Step 4: Commit**

```bash
git add app/components/batch_processing_form.py
git commit -m "$(cat <<'EOF'
batch form passes active client_id

Threads client_id through _process_single_record (both initial run
and retry path). Adds a 'Batch will generate TSRs for: <client>'
caption.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Update `CLAUDE.md`**

In [CLAUDE.md](CLAUDE.md), under the "Domain Concepts" section (the last section in the file), append:

```markdown
- **Clients library**: `clients.json` at the repo root holds saved client/lender details (name, CIN, address, attention person, ref prefix, reference email date). Loaded once via `core.clients.get_client_library()`. The Streamlit sidebar lets users pick the active client; the selection flows through the `/process-record` API as `client_id`. Missing/malformed `clients.json` → falls back to hardcoded ABREL defaults in the DOCX template (`tsr_generator/document/tsr_document.py`). To add a client: edit `clients.json`, commit, redeploy.
- **DOCX cache split**: The GCS cache stores PDFs keyed by `(district, taluka, village, survey)` (shared across clients) and DOCXs keyed by `(pdf_key, client_id)` under `cache/{pdf_key}/docx_{client_id}.docx`. Two clients sharing a survey get distinct DOCXs.
```

- [ ] **Step 2: Update `README.md`**

In [README.md](README.md), under "🚀 Features", add this bullet right after "Multi-Language Support":

```markdown
- **Multi-Client Support**: Save lender/client details in `clients.json` and pick the active client from a sidebar dropdown. The Streamlit UI plumbs the selection through the API into the DOCX template.
```

Then add a new section after "## ⚡ Optimized Extraction":

```markdown
---

## 👥 Multi-Client TSRs

The application supports generating TSRs for multiple clients (lenders / borrowers / counterparties).

### How it works

1. A `clients.json` file at the repo root holds saved client details:
   - `client_name`, `client_cin`, `client_address`, `kind_attn`, `ref_prefix`, `reference_email_date`
2. The Streamlit sidebar has an **Active Client** dropdown listing every entry by `display_name`.
3. The selected client flows through the API into the generated DOCX (the "To:" block and the "Ref. No." prefix both update).
4. The GCS cache is split: scraped PDFs are shared across clients, generated DOCXs are stored per-client. Two clients running the same survey get distinct DOCXs.

### Adding a client

Edit `clients.json`, add an entry like:

```json
{
  "id": "my_new_client",
  "display_name": "My New Client",
  "client_name": "My New Client Pvt Ltd",
  "client_cin": "(CIN: ...),",
  "client_address": "Address line 1,\nAddress line 2.",
  "kind_attn": "Kind Attn.: Mr. Foo",
  "ref_prefix": "MNC",
  "reference_email_date": "DD.MM.YYYY"
}
```

Then commit and redeploy. The new client appears in the sidebar dropdown.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
document the clients.json workflow

Note the new clients library, sidebar picker, cache split, and the
'edit JSON + commit + redeploy' workflow for adding a client.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v -k "not integration"`
Expected: All non-integration tests pass.

- [ ] **Step 2: End-to-end smoke check**

Run: `streamlit run app/streamlit_app_cloud.py`

- Sidebar shows "Active Client" with the ABREL entry pre-selected.
- Both tabs show "Generating TSR for: ABREL SPV 2 Limited".
- Switch the dropdown to any second entry (add a test one to `clients.json` if needed) → caption updates on both tabs.

- [ ] **Step 3: Manual data flow check (optional, requires backend)**

Generate a TSR for one survey with `abrel_spv_2`. Then add a second client to `clients.json` and generate a TSR for the same survey with that client. Open both DOCXs:

- The "To:" block differs (name / CIN / address / attention).
- The "Ref. No." prefix differs.
- The PDF download for both is byte-identical (PDF cache shared).
- Logs show: first run "CACHE MISS" → "CACHED PDF + DOCX". Second run "🟡 PARTIAL CACHE HIT (PDF hit, DOCX miss)" → "CACHED PDF + DOCX" with the new client_id.
