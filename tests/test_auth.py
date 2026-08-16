"""Auth allow-list: only pre-registered emails can sign in."""
from __future__ import annotations

from app.auth import register_user


def test_unregistered_email_is_rejected(client):
    r = client.post("/api/auth/magic-link", json={"email": "stranger@nowhere.com"})
    assert r.status_code == 403
    assert "not registered" in r.json()["detail"].lower()


def test_registered_email_can_request_link(client, db_session):
    register_user(db_session, "allowed@brand.com")
    r = client.post("/api/auth/magic-link", json={"email": "allowed@brand.com"})
    assert r.status_code == 200
    assert r.json()["dev_login_url"]


def test_email_is_normalized(client, db_session):
    register_user(db_session, "Mixed.Case@Brand.com")
    # Login with different casing still resolves to the registered account.
    r = client.post("/api/auth/magic-link", json={"email": "mixed.case@brand.com"})
    assert r.status_code == 200
