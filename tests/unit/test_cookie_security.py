"""Unit tests for cookie security helper functions across environments (Phase 11)."""


from app.core.config import settings
from app.core.security import get_cookie_samesite, get_cookie_secure


def test_CS_01_local_environment_respects_cookie_secure(monkeypatch):
    """In local environment, get_cookie_secure returns settings.COOKIE_SECURE."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    assert get_cookie_secure() is False

    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    assert get_cookie_secure() is True


def test_CS_02_production_and_staging_enforce_secure(monkeypatch):
    """In non-local environments (staging, production), get_cookie_secure always returns True."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    assert get_cookie_secure() is True

    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    assert get_cookie_secure() is True


def test_CS_03_local_environment_respects_cookie_samesite(monkeypatch):
    """In local environment, get_cookie_samesite returns settings.COOKIE_SAMESITE."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "lax")
    assert get_cookie_samesite() == "lax"

    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "strict")
    assert get_cookie_samesite() == "strict"


def test_CS_04_production_and_staging_enforce_samesite_none(monkeypatch):
    """In non-local environments, get_cookie_samesite always returns 'none' for cross-domain auth."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert get_cookie_samesite() == "none"

    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    assert get_cookie_samesite() == "none"
