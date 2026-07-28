"""Tests for the PDF text-extraction fallback chain.

Regression guard for the 2026-07-28 finding: pypdf mis-decodes Gujarati in the
AnyRoR record PDFs (drops conjuncts/reph, writes every o-matra as `ા`+`ે`) which
corrupts title-holder names. poppler `pdftotext` reads the same bytes correctly,
so it must be preferred and pypdf must stay last.
"""
import shutil
import subprocess

import pytest

from tsr_generator.utils import pdf_utils


@pytest.fixture(autouse=True)
def _clear_cache():
    pdf_utils.clear_pdf_cache()
    yield
    pdf_utils.clear_pdf_cache()


def test_extractor_priority_order():
    """poppler first, pymupdf second, pypdf LAST - pypdf mangles Gujarati."""
    names = [name for name, _ in pdf_utils._EXTRACTORS]
    assert names == ["pdftotext", "pymupdf", "pypdf"]


def test_prefers_pdftotext_when_available(monkeypatch):
    calls = []

    def fake_pdftotext(path):
        calls.append("pdftotext")
        return "નોંધ દ્વારા ગ્રામ્ય"

    def fake_pypdf(path):
        calls.append("pypdf")
        return "ના ધ  ારા  ામ્ય"

    monkeypatch.setattr(pdf_utils, "_EXTRACTORS", (
        ("pdftotext", fake_pdftotext),
        ("pypdf", fake_pypdf),
    ))
    assert pdf_utils.extract_text_from_pdf("/tmp/x.pdf") == "નોંધ દ્વારા ગ્રામ્ય"
    assert calls == ["pdftotext"], "pypdf must not run when pdftotext succeeds"


def test_falls_back_when_earlier_extractor_returns_nothing(monkeypatch):
    monkeypatch.setattr(pdf_utils, "_EXTRACTORS", (
        ("pdftotext", lambda p: None),
        ("pymupdf", lambda p: "   "),      # whitespace-only must not count
        ("pypdf", lambda p: "fallback text"),
    ))
    assert pdf_utils.extract_text_from_pdf("/tmp/x.pdf") == "fallback text"


def test_returns_none_when_all_extractors_fail(monkeypatch):
    monkeypatch.setattr(pdf_utils, "_EXTRACTORS", (
        ("pdftotext", lambda p: None),
        ("pypdf", lambda p: None),
    ))
    assert pdf_utils.extract_text_from_pdf("/tmp/x.pdf") is None


def test_pdftotext_missing_binary_returns_none(monkeypatch):
    monkeypatch.setattr(pdf_utils.shutil, "which", lambda name: None)
    assert pdf_utils._extract_with_pdftotext("/tmp/x.pdf") is None


def test_pdftotext_nonzero_exit_returns_none(monkeypatch):
    monkeypatch.setattr(pdf_utils.shutil, "which", lambda name: "/usr/bin/pdftotext")

    class R:
        returncode = 1
        stdout = b""

    monkeypatch.setattr(pdf_utils.subprocess, "run", lambda *a, **k: R())
    assert pdf_utils._extract_with_pdftotext("/tmp/x.pdf") is None


def test_pdftotext_timeout_is_swallowed(monkeypatch):
    monkeypatch.setattr(pdf_utils.shutil, "which", lambda name: "/usr/bin/pdftotext")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="pdftotext", timeout=1)

    monkeypatch.setattr(pdf_utils.subprocess, "run", boom)
    assert pdf_utils._extract_with_pdftotext("/tmp/x.pdf") is None


def test_extraction_result_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_utils, "_EXTRACTORS", (
        ("pdftotext", lambda p: calls.append(p) or "text"),
    ))
    pdf_utils.extract_text_from_pdf("/tmp/same.pdf")
    pdf_utils.extract_text_from_pdf("/tmp/same.pdf")
    assert len(calls) == 1, "second call should hit the lru_cache"


@pytest.mark.skipif(not shutil.which("pdftotext"),
                    reason="poppler pdftotext not installed")
def test_pdftotext_decodes_gujarati_conjuncts(tmp_path):
    """End-to-end guard on a real PDF, if one is available locally.

    Skipped in CI (no cached records there); runs on a dev machine.
    """
    import glob
    import os
    cached = sorted(glob.glob(os.path.expanduser(
        "~/.cache/gujrat_tsr_agent/cache/*/original.pdf")))
    if not cached:
        pytest.skip("no cached AnyRoR PDFs on this machine")

    text = pdf_utils._extract_with_pdftotext(cached[0])
    assert text
    # pypdf's signature failure: o-matra split into ા + ે
    assert "ાે" not in text, "o-matra should not be decomposed"
