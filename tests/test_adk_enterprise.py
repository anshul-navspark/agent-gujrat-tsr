"""
Tests for enterprise (Vertex AI) auth + the scraper tool decoupling.

Offline only — no network, no key. They assert the *auth routing* (does the
agent fall back to the offline FakeGemini or reach a real backend?) and the
*scraper dispatch* (in-process Selenium vs a remote Cloud Run scraper service).
"""

import base64

import pytest

from adk_agent.app import resolve_model
from adk_agent.config import AdkConfig
from adk_agent.dry_run_model import FakeGemini


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
