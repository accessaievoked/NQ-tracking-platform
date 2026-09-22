"""Changing TOKEN_ENCRYPTION_KEY without breaking stored credentials.

Until now an empty TOKEN_ENCRYPTION_KEY meant every credential was encrypted
with a key derived from APP_SECRET_KEY. These cover the key ring that lets a
real key be introduced with old rows still readable, and the script that moves
those rows onto the new key.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app import security
from app.config import settings

NEW_KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()


@pytest.fixture()
def keys(monkeypatch):
    """Set the primary/previous keys for one test; restored afterwards."""

    def _set(primary: str = "", previous: str = ""):
        monkeypatch.setattr(settings, "token_encryption_key", primary)
        monkeypatch.setattr(settings, "token_encryption_key_previous", previous)

    _set()
    return _set


# --- the key ring ----------------------------------------------------------

def test_empty_key_still_uses_the_legacy_derived_key(keys):
    """Unchanged behaviour: no key configured -> derived from the app secret."""
    token = security.encrypt("secret")
    assert security.which_key(token) == "primary"
    derived = Fernet(security._derived_key())
    assert derived.decrypt(token.encode()).decode() == "secret"


def test_rows_written_under_the_legacy_key_survive_setting_a_real_key(keys):
    """The whole point: set a real key and nothing already stored breaks."""
    legacy_token = security.encrypt("shopify-token")   # empty key -> derived
    keys(primary=NEW_KEY)
    assert security.decrypt(legacy_token) == "shopify-token"
    assert security.which_key(legacy_token).startswith("legacy")


def test_new_writes_use_the_primary_key(keys):
    keys(primary=NEW_KEY)
    token = security.encrypt("ga4-key")
    assert Fernet(NEW_KEY.encode()).decrypt(token.encode()).decode() == "ga4-key"
    assert security.which_key(token) == "primary"


def test_previous_keys_are_accepted_for_decryption(keys):
    keys(primary=OTHER_KEY)
    old_token = security.encrypt("meta-token")
    keys(primary=NEW_KEY, previous=OTHER_KEY)
    assert security.decrypt(old_token) == "meta-token"
    assert security.which_key(old_token) == "previous #1"


def test_unknown_key_gives_an_actionable_error(keys):
    foreign = Fernet(Fernet.generate_key()).encrypt(b"x").decode()
    keys(primary=NEW_KEY)
    with pytest.raises(ValueError, match="TOKEN_ENCRYPTION_KEY_PREVIOUS"):
        security.decrypt(foreign)
    assert security.which_key(foreign) is None


def test_reencrypt_moves_a_legacy_row_onto_the_primary_key(keys):
    legacy_token = security.encrypt("payload")
    keys(primary=NEW_KEY)
    moved = security.reencrypt(legacy_token)
    assert security.which_key(moved) == "primary"
    assert Fernet(NEW_KEY.encode()).decrypt(moved.encode()).decode() == "payload"


def test_ring_drops_a_previous_key_identical_to_the_primary(keys):
    keys(primary=NEW_KEY, previous=NEW_KEY)
    labels = [label for label, _ in security.key_ring()]
    assert labels.count("primary") == 1
    assert "previous #1" not in labels


# --- the rotation script ---------------------------------------------------

def _add_integration(db, brand_name: str, provider, plaintext: str):
    from app.models import Brand, Integration

    brand = Brand(client_id="client-1", name=brand_name)
    db.add(brand)
    db.flush()
    integ = Integration(
        brand_id=brand.id,
        provider=provider,
        encrypted_tokens=security.encrypt(plaintext),
    )
    db.add(integ)
    db.commit()
    return integ


def test_script_dry_run_changes_nothing(keys, db_session, capsys):
    from app.models import IntegrationProvider
    from scripts import rotate_token_key as script

    integ = _add_integration(db_session, "Three Sixty", IntegrationProvider.shopify, "t")
    before = integ.encrypted_tokens
    keys(primary=NEW_KEY)

    counts, _ = script.report(db_session)
    assert integ.encrypted_tokens == before
    assert sum(counts.values()) == 1
    assert "Three Sixty / shopify" in capsys.readouterr().out


def test_script_apply_moves_everything_and_verifies(keys, db_session, capsys):
    from app.models import IntegrationProvider
    from scripts import rotate_token_key as script

    shop = _add_integration(db_session, "Three Sixty", IntegrationProvider.shopify, "s")
    ga4 = _add_integration(db_session, "dev", IntegrationProvider.ga4, "g")
    keys(primary=NEW_KEY)

    _, rows = script.report(db_session)
    assert script.apply(db_session, rows) == 0

    primary = Fernet(NEW_KEY.encode())
    assert primary.decrypt(shop.encrypted_tokens.encode()) == b"s"
    assert primary.decrypt(ga4.encrypted_tokens.encode()) == b"g"
    assert "Verified" in capsys.readouterr().out


def test_script_apply_is_idempotent(keys, db_session):
    from app.models import IntegrationProvider
    from scripts import rotate_token_key as script

    integ = _add_integration(db_session, "Three Sixty", IntegrationProvider.shopify, "s")
    keys(primary=NEW_KEY)
    _, rows = script.report(db_session)
    script.apply(db_session, rows)
    after_first = integ.encrypted_tokens

    _, rows = script.report(db_session)
    assert script.apply(db_session, rows) == 0
    assert integ.encrypted_tokens == after_first     # already primary: untouched


def test_script_reports_unreadable_rows_and_fails(keys, db_session, capsys):
    from app.models import IntegrationProvider
    from scripts import rotate_token_key as script

    keys(primary=OTHER_KEY)
    _add_integration(db_session, "Orphan", IntegrationProvider.meta_ads, "m")
    keys(primary=NEW_KEY)                  # OTHER_KEY is now nowhere in the ring

    _, rows = script.report(db_session)
    assert script.apply(db_session, rows) == 1
    out = capsys.readouterr().out
    assert "UNREADABLE" in out
    assert "TOKEN_ENCRYPTION_KEY_PREVIOUS" in out


def test_script_refuses_to_apply_without_a_real_key(keys, capsys):
    from scripts import rotate_token_key as script

    assert script.main(["--apply"]) == 2
    assert "Refusing to rotate" in capsys.readouterr().out


def test_script_refuses_an_invalid_key(keys, capsys):
    from scripts import rotate_token_key as script

    keys(primary="not-a-fernet-key")
    assert script.main(["--apply"]) == 2
    assert "not a valid Fernet key" in capsys.readouterr().out


def test_generate_key_prints_a_valid_fernet_key(capsys):
    from scripts import rotate_token_key as script

    assert script.main(["--generate-key"]) == 0
    Fernet(capsys.readouterr().out.strip().encode())   # raises if malformed
