"""
Tests for enterprise (Vertex AI) auth + the scraper tool decoupling.

Offline only — no network, no key. They assert the *auth routing* (does the
agent fall back to the offline FakeGemini or reach a real backend?) and the
*scraper dispatch* (in-process Selenium vs a remote Cloud Run scraper service).
"""

import base64
import json

import pytest

from adk_agent.app import resolve_model
from adk_agent.config import AdkConfig
from adk_agent.dry_run_model import FakeGemini
from adk_agent.skills import scrape


# ------------------------------------------------------------------- auth modes
def test_dev_mode_without_key_falls_back_to_fake(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    cfg = AdkConfig()
    assert cfg.use_vertex is False
    assert cfg.has_credentials is False
    assert isinstance(resolve_model(cfg), FakeGemini)


def test_dev_mode_with_key_reaches_real_backend(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    cfg = AdkConfig()
    assert cfg.has_credentials is True
    assert resolve_model(cfg) == cfg.model_name  # a model id string, not FakeGemini


def test_vertex_mode_is_enterprise_without_api_key(monkeypatch):
    """Enterprise: Vertex AI / ADC — credentials present, must NOT use FakeGemini."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "asia-south1")
    cfg = AdkConfig()
    assert cfg.use_vertex is True
    assert cfg.has_credentials is True              # ADC, no personal key
    assert cfg.project == "my-proj" and cfg.location == "asia-south1"
    model = resolve_model(cfg)
    assert not isinstance(model, FakeGemini)        # the bug this guards against
    assert model == cfg.model_name


def test_dry_run_forces_fake_even_under_vertex(monkeypatch):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
    cfg = AdkConfig(dry_run=True)
    assert isinstance(resolve_model(cfg), FakeGemini)


# ----------------------------------------------------------------- scraper tool
class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_scrape_dispatches_remote_when_url_set(monkeypatch):
    monkeypatch.setenv("ANYROR_SCRAPER_URL", "https://scraper.example")
    seen = {}

    def fake_remote(url, token, *a, **k):
        seen["remote_url"] = url
        return {"pdf_path": "x"}

    def fake_local(*a, **k):
        seen["local"] = True
        return {"pdf_path": "x"}

    monkeypatch.setattr(scrape, "_remote_scrape_to_pdf", fake_remote)
    monkeypatch.setattr(scrape, "_local_scrape_to_pdf", fake_local)
    scrape.scrape_to_pdf("Kutch", "Abdasa", "Ustiya", "578", "/tmp/x.pdf")
    assert seen.get("remote_url") == "https://scraper.example"
    assert "local" not in seen


def test_scrape_dispatches_local_when_no_url(monkeypatch):
    monkeypatch.delenv("ANYROR_SCRAPER_URL", raising=False)
    seen = {}

    def fake_local(*a, **k):
        seen["local"] = True
        return {"pdf_path": "x"}

    def fake_remote(*a, **k):
        seen["remote"] = True
        return {"pdf_path": "x"}

    monkeypatch.setattr(scrape, "_local_scrape_to_pdf", fake_local)
    monkeypatch.setattr(scrape, "_remote_scrape_to_pdf", fake_remote)
    scrape.scrape_to_pdf("Kutch", "Abdasa", "Ustiya", "578", "/tmp/x.pdf")
    assert seen.get("local") is True
    assert "remote" not in seen


def test_remote_scrape_decodes_and_writes_pdf(monkeypatch, tmp_path):
    pdf_bytes = b"%PDF-1.4 fake content"
    payload = {
        "success": True,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "g_village": "ઉસ્તિયા",
        "survey_number": "578",
    }
    monkeypatch.setattr(scrape.urllib.request, "urlopen", lambda req, timeout=300: _FakeResp(payload))
    out = tmp_path / "ustiya_578.pdf"
    res = scrape._remote_scrape_to_pdf(
        "https://scraper.example", "tok", "Kutch", "Abdasa", "Ustiya", "578", str(out)
    )
    assert out.read_bytes() == pdf_bytes
    assert res["remote"] is True
    assert res["survey_number"] == "578"


def test_remote_scrape_raises_on_service_error(monkeypatch, tmp_path):
    payload = {"success": False, "error": "AnyRoR unreachable"}
    monkeypatch.setattr(scrape.urllib.request, "urlopen", lambda req, timeout=300: _FakeResp(payload))
    with pytest.raises(RuntimeError, match="AnyRoR unreachable"):
        scrape._remote_scrape_to_pdf(
            "https://scraper.example", None, "Kutch", "Abdasa", "Ustiya", "578", str(tmp_path / "x.pdf")
        )
