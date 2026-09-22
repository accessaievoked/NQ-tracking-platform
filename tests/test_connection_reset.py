"""The single encryption key, and the script that wipes connections for a clean start."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app import security
from app.config import settings
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus


# --- startup key check -----------------------------------------------------

@pytest.fixture()
def env(monkeypatch):
    def _set(key: str = "", app_env: str = "local"):
        monkeypatch.setattr(settings, "token_encryption_key", key)
        monkeypatch.setattr(settings, "app_env", app_env)

    return _set


def test_valid_key_passes(env):
    env(Fernet.generate_key().decode(), "production")
    security.check_encryption_key()


def test_malformed_key_stops_startup_with_a_readable_message(env):
    """The padding error from the failed rotation, caught at boot instead."""
    env("HyivuSKz2iFjT4locY85coK7cqPewSPq3o-vHkCkuKU", "production")  # one char short
    with pytest.raises(RuntimeError, match="not a valid Fernet key"):
        security.check_encryption_key()


def test_missing_key_is_refused_in_production(env):
    env("", "production")
    with pytest.raises(RuntimeError, match="not set"):
        security.check_encryption_key()


def test_missing_key_is_fine_locally(env):
    env("", "local")
    security.check_encryption_key()
    assert security.decrypt(security.encrypt("x")) == "x"


def test_surrounding_whitespace_in_the_key_is_tolerated(env):
    env("  " + Fernet.generate_key().decode() + "\n", "production")
    assert security.decrypt(security.encrypt("x")) == "x"


def test_credentials_from_another_key_ask_for_a_reconnect(env):
    env(Fernet.generate_key().decode(), "production")
    foreign = Fernet(Fernet.generate_key()).encrypt(b"x").decode()
    with pytest.raises(ValueError, match="Reconnect this integration"):
        security.decrypt(foreign)


# --- reset script ----------------------------------------------------------

def _brand(db, name: str) -> Brand:
    brand = Brand(client_id="client-1", name=name)
    db.add(brand)
    db.flush()
    return brand


def _integ(db, brand, provider, *, connected=True):
    integ = Integration(
        brand_id=brand.id,
        provider=provider,
        status=IntegrationStatus.connected if connected else IntegrationStatus.not_connected,
        config={"x": 1} if connected else None,
        # Deliberately not decryptable: the reset must not care.
        encrypted_tokens="gAAAA-not-readable-under-any-key" if connected else None,
    )
    db.add(integ)
    db.commit()
    return integ


@pytest.fixture()
def script(db_session, monkeypatch):
    from scripts import reset_connections

    monkeypatch.setattr(reset_connections, "SessionLocal", lambda: _NoClose(db_session))
    return reset_connections


class _NoClose:
    """Hand the test's session to the script's `with SessionLocal()` block."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


def test_dry_run_lists_and_changes_nothing(script, db_session, capsys):
    brand = _brand(db_session, "Three Sixty Leather")
    shop = _integ(db_session, brand, IntegrationProvider.shopify)

    assert script.main([]) == 0
    out = capsys.readouterr().out
    assert "Three Sixty Leather / shopify" in out
    assert "Dry run" in out
    assert shop.status == IntegrationStatus.connected
    assert shop.encrypted_tokens is not None


def test_apply_clears_every_brand_including_unreadable_credentials(
    script, db_session, capsys
):
    a = _brand(db_session, "Three Sixty Leather")
    b = _brand(db_session, "Claura")
    rows = [
        _integ(db_session, a, IntegrationProvider.shopify),
        _integ(db_session, a, IntegrationProvider.ga4),
        _integ(db_session, b, IntegrationProvider.meta_ads),
    ]

    assert script.main(["--apply"]) == 0
    for integ in rows:
        db_session.refresh(integ)
        assert integ.status == IntegrationStatus.not_connected
        assert integ.encrypted_tokens is None
        assert integ.config is None
        assert integ.last_error is None
    assert "Cleared 3" in capsys.readouterr().out


def test_brands_survive_the_reset(script, db_session):
    brand = _brand(db_session, "Three Sixty Leather")
    _integ(db_session, brand, IntegrationProvider.shopify)
    script.main(["--apply"])
    assert db_session.get(Brand, brand.id) is not None


def test_nothing_to_clear_is_reported_plainly(script, db_session, capsys):
    brand = _brand(db_session, "Three Sixty Leather")
    _integ(db_session, brand, IntegrationProvider.clarity, connected=False)
    assert script.main(["--apply"]) == 0
    assert "No connections to clear" in capsys.readouterr().out
