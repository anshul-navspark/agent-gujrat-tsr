"""Tests for the per-client DOCX cache split."""

import importlib.util
import sys
import types as _types
from pathlib import Path
import pytest

# ---------------------------------------------------------------------------
# Load services.cache_service without triggering the services/__init__.py
# cascade (which pulls in langchain/GCS/file-service deps).
# Also stub out google.cloud.storage, which hangs on import in environments
# without GCS credentials (the LocalCacheService under test doesn't use it).
# ---------------------------------------------------------------------------
_project_root = str(Path(__file__).resolve().parents[1])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Stub google.cloud.storage so the module-level import in cache_service.py
# doesn't block waiting for credentials.
_google_mod = sys.modules.get("google") or _types.ModuleType("google")
_google_cloud_mod = _types.ModuleType("google.cloud")
_google_storage_mod = _types.ModuleType("google.cloud.storage")
_google_cloud_exceptions_mod = _types.ModuleType("google.cloud.exceptions")
_google_cloud_exceptions_mod.NotFound = type("NotFound", (Exception,), {})
_google_mod.cloud = _google_cloud_mod  # type: ignore[attr-defined]
_google_cloud_mod.storage = _google_storage_mod  # type: ignore[attr-defined]
for _name, _mod in [
    ("google", _google_mod),
    ("google.cloud", _google_cloud_mod),
    ("google.cloud.storage", _google_storage_mod),
    ("google.cloud.exceptions", _google_cloud_exceptions_mod),
]:
    sys.modules.setdefault(_name, _mod)

# Stub out the services package so __init__.py is never executed.
if "services" not in sys.modules:
    sys.modules["services"] = _types.ModuleType("services")

# Load services/cache_service.py directly.
_spec = importlib.util.spec_from_file_location(
    "services.cache_service",
    str(Path(_project_root) / "services" / "cache_service.py"),
)
_cache_mod = importlib.util.module_from_spec(_spec)
sys.modules["services.cache_service"] = _cache_mod
_spec.loader.exec_module(_cache_mod)
LocalCacheService = _cache_mod.LocalCacheService

from core.models import LandRecordRequest


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
