"""Regression tests for the local cache TTL.

Land records are effectively immutable, so the local filesystem cache must NOT
inherit the 7-day GCS TTL (which silently expired generated TSRs and forced
needless regeneration). Default is effectively-never; LOCAL_CACHE_TTL_DAYS overrides.
"""
import services.cache_service as cs


def _fresh_service(monkeypatch, **env):
    monkeypatch.delenv("GCS_CACHE_BUCKET", raising=False)
    monkeypatch.delenv("LOCAL_CACHE_TTL_DAYS", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    cs._cache_service = None  # reset module singleton
    return cs.get_cache_service()


def test_local_cache_default_ttl_is_effectively_never(monkeypatch):
    svc = _fresh_service(monkeypatch)
    assert isinstance(svc, cs.LocalCacheService)
    assert svc.ttl_days >= 36500


def test_local_cache_ttl_env_override(monkeypatch):
    svc = _fresh_service(monkeypatch, LOCAL_CACHE_TTL_DAYS="3")
    assert isinstance(svc, cs.LocalCacheService)
    assert svc.ttl_days == 3


def test_local_cache_ttl_bad_value_falls_back(monkeypatch):
    svc = _fresh_service(monkeypatch, LOCAL_CACHE_TTL_DAYS="not-an-int")
    assert isinstance(svc, cs.LocalCacheService)
    assert svc.ttl_days >= 36500
