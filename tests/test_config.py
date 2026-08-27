"""Tests for core/config.py.

The point of these is the zero-credit boot path. `Config.__post_init__` used to
raise `ValueError("GEMINI_API_KEY environment variable is required")`, which
turned an API key nobody has into a hard startup dependency — with Gemini
credits at zero and both the captcha solver and the default extraction backend
running on the local `claude` CLI, nothing booted at all. The key is now
optional at startup and only the Gemini-backed paths fail, at point of use.
"""

import logging

import pytest

import core.config as config_mod
from core.config import Config, get_config, require_gemini_api_key, reset_config


@pytest.fixture(autouse=True)
def _clean_config():
    reset_config()
    yield
    reset_config()


class TestBootsWithoutGeminiKey:
    def test_config_constructs_without_key(self):
        # Used to raise ValueError here.
        cfg = Config(gemini_api_key="")
        assert cfg.gemini_api_key == ""

    def test_get_config_boots_without_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        cfg = get_config()
        # No raise is the assertion; the rest of the config must still be sane.
        assert cfg.anyror_wait_timeout > 0
        assert cfg.api_timeout > 0

    def test_validate_passes_without_key(self):
        assert Config(gemini_api_key="").validate() is True

    def test_missing_key_is_logged_once(self, caplog, monkeypatch):
        monkeypatch.setattr(config_mod, "_gemini_notice_logged", False)
        with caplog.at_level(logging.INFO, logger="core.config"):
            Config(gemini_api_key="")
            Config(gemini_api_key="")
        notices = [r for r in caplog.records if "GEMINI_API_KEY is not set" in r.message]
        assert len(notices) == 1

    def test_other_validation_still_raises(self):
        with pytest.raises(ValueError, match="anyror_wait_timeout"):
            Config(gemini_api_key="", anyror_wait_timeout=0).validate()
        with pytest.raises(ValueError, match="api_timeout"):
            Config(gemini_api_key="", api_timeout=0).validate()


class TestRequireGeminiApiKey:
    def test_raises_at_point_of_use(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        reset_config()
        config_mod._config = Config(gemini_api_key="")
        with pytest.raises(ValueError, match="Gemini extraction requires it"):
            require_gemini_api_key("Gemini extraction")

    def test_returns_key_when_set(self):
        config_mod._config = Config(gemini_api_key="a-key")
        assert require_gemini_api_key("anything") == "a-key"
