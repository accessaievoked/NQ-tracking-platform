"""Per-brand Shopify apps: each client store installs its own custom-distribution app."""
from __future__ import annotations

import hashlib
import hmac as hmaclib
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import settings
from app.connectors import shopify_oauth as oauth
from app.models import Brand, ShopifyApp
from app.security import encrypt, make_token

SHOP = "indethnic.myshopify.com"


def _sign(params: dict, secret: str) -> str:
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmaclib.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


@pytest.fixture()
def default_app(monkeypatch):
    monkeypatch.setattr(settings, "shopify_api_key", "default-key")
    monkeypatch.setattr(settings, "shopify_api_secret", "default-secret")
    monkeypatch.setattr(settings, "shopify_redirect_uri", "https://nq.test/cb")


def _brand_with_app(auth_client, db_session, name="Indethnic", client_id="indethnic-key",
                    secret="indethnic-secret") -> str:
    brand_id = auth_client.post("/api/brands", json={"name": name}).json()["id"]
    app = ShopifyApp(name=f"NQ-tracker-{name}", client_id=client_id,
                     encrypted_client_secret=encrypt(secret))
    db_session.add(app)
    db_session.flush()
    db_session.get(Brand, brand_id).shopify_app_id = app.id
    db_session.commit()
    return brand_id


def _install_client_id(auth_client, brand_id) -> str:
    r = auth_client.get(
        f"/api/integrations/shopify/install-url?brand_id={brand_id}&shop={SHOP}"
    )
    assert r.status_code == 200, r.text
    return parse_qs(urlparse(r.json()["url"]).query)["client_id"][0]


# --- install URL -----------------------------------------------------------

def test_brand_without_an_app_uses_the_default(auth_client, default_app):
    brand_id = auth_client.post("/api/brands", json={"name": "Three Sixty"}).json()["id"]
    assert _install_client_id(auth_client, brand_id) == "default-key"


def test_brand_with_its_own_app_sends_the_store_to_that_app(
    auth_client, db_session, default_app
):
    brand_id = _brand_with_app(auth_client, db_session)
    assert _install_client_id(auth_client, brand_id) == "indethnic-key"


def test_two_brands_get_two_different_apps(auth_client, db_session, default_app):
    a = _brand_with_app(auth_client, db_session, "Indethnic", "ind-key", "s1")
    b = _brand_with_app(auth_client, db_session, "Sitarey", "sit-key", "s2")
    assert _install_client_id(auth_client, a) == "ind-key"
    assert _install_client_id(auth_client, b) == "sit-key"


def test_no_app_anywhere_is_a_clear_error_not_a_broken_link(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "shopify_api_key", "")
    monkeypatch.setattr(settings, "shopify_api_secret", "")
    brand_id = auth_client.post("/api/brands", json={"name": "X"}).json()["id"]
    r = auth_client.get(f"/api/integrations/shopify/install-url?brand_id={brand_id}&shop={SHOP}")
    assert r.status_code == 409
    assert "register_shopify_app" in r.json()["detail"]


# --- callback ------------------------------------------------------------------

def _callback(auth_client, brand_id, secret, monkeypatch, seen=None):
    state = make_token({"brand_id": brand_id, "shop": SHOP, "nonce": "n"},
                       salt=oauth.STATE_SALT)

    def _exchange(shop, code, app=None):
        if seen is not None:
            seen["app"] = app
        return {"access_token": "shpat_x", "scope": "read_orders"}

    monkeypatch.setattr("app.api.shopify_oauth.exchange_code_for_token", _exchange)
    monkeypatch.setattr(
        "app.connectors.shopify.ShopifyConnector.verify_connection",
        lambda self: {"name": "Indethnic", "currency": "INR"},
    )
    params = {"code": "c", "shop": SHOP, "state": state, "timestamp": "1700000000"}
    params["hmac"] = _sign(params, secret)
    return auth_client.get("/api/integrations/shopify/callback", params=params,
                           follow_redirects=False)


def test_callback_verifies_hmac_with_the_brands_own_app_secret(
    auth_client, db_session, default_app, monkeypatch
):
    brand_id = _brand_with_app(auth_client, db_session)
    seen = {}
    r = _callback(auth_client, brand_id, "indethnic-secret", monkeypatch, seen)
    assert r.status_code in (302, 307), r.text
    # The code is exchanged with the same app that was installed.
    assert seen["app"].client_id == "indethnic-key"
    assert seen["app"].client_secret == "indethnic-secret"

    shopify = [i for i in auth_client.get(f"/api/brands/{brand_id}/integrations").json()
               if i["provider"] == "shopify"][0]
    assert shopify["status"] == "connected"


def test_callback_signed_by_the_default_app_is_rejected_for_a_brand_with_its_own(
    auth_client, db_session, default_app, monkeypatch
):
    brand_id = _brand_with_app(auth_client, db_session)
    r = _callback(auth_client, brand_id, "default-secret", monkeypatch)
    assert r.status_code == 401


def test_callback_for_a_default_app_brand_still_works(auth_client, default_app, monkeypatch):
    brand_id = auth_client.post("/api/brands", json={"name": "Three Sixty"}).json()["id"]
    r = _callback(auth_client, brand_id, "default-secret", monkeypatch)
    assert r.status_code in (302, 307), r.text


def test_callback_records_which_app_granted_the_token(
    auth_client, db_session, default_app, monkeypatch
):
    from app.models import Integration, IntegrationProvider

    brand_id = _brand_with_app(auth_client, db_session)
    _callback(auth_client, brand_id, "indethnic-secret", monkeypatch)
    integ = db_session.query(Integration).filter_by(
        brand_id=brand_id, provider=IntegrationProvider.shopify).one()
    assert integ.config["app_client_id"] == "indethnic-key"


# --- registration script ----------------------------------------------------------

class _Session:
    def __init__(self, s):
        self.s = s

    def __enter__(self):
        return self.s

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def script(db_session, monkeypatch):
    from scripts import register_shopify_app as mod

    monkeypatch.setattr(mod, "SessionLocal", lambda: _Session(db_session))
    monkeypatch.setenv("SHOPIFY_APP_SECRET", "typed-secret")
    return mod


def _plain_brand(db, name):
    b = Brand(client_id="client-1", name=name)
    db.add(b)
    db.commit()
    return b


def test_script_registers_and_links_with_the_secret_encrypted(script, db_session, capsys):
    from app.security import decrypt

    brand = _plain_brand(db_session, "Indethnic")
    assert script.main(["--brand", "indethnic", "--name", "NQ-tracker-Indethnic",
                        "--client-id", "abc123"]) == 0
    db_session.refresh(brand)
    app = brand.shopify_app
    assert app.client_id == "abc123"
    assert app.encrypted_client_secret != "typed-secret"
    assert decrypt(app.encrypted_client_secret) == "typed-secret"
    out = capsys.readouterr().out
    assert "typed-secret" not in out


def test_script_links_an_already_registered_app(script, db_session):
    a = _plain_brand(db_session, "Indethnic")
    b = _plain_brand(db_session, "Indethnic Outlet")
    script.main(["--brand", "Indethnic", "--name", "Shared", "--client-id", "k1"])
    assert script.main(["--brand", "Indethnic Outlet", "--name", "Shared"]) == 0
    db_session.refresh(a)
    db_session.refresh(b)
    assert a.shopify_app_id == b.shopify_app_id


def test_script_refuses_a_duplicate_client_id_under_a_new_name(script, db_session, capsys):
    _plain_brand(db_session, "Indethnic")
    _plain_brand(db_session, "Sitarey")
    script.main(["--brand", "Indethnic", "--name", "A", "--client-id", "same"])
    assert script.main(["--brand", "Sitarey", "--name", "B", "--client-id", "same"]) == 2
    assert 'already registered as "A"' in capsys.readouterr().out


def test_script_use_default_unlinks(script, db_session):
    brand = _plain_brand(db_session, "Indethnic")
    script.main(["--brand", "Indethnic", "--name", "A", "--client-id", "k"])
    assert script.main(["--brand", "Indethnic", "--use-default"]) == 0
    db_session.refresh(brand)
    assert brand.shopify_app_id is None


def test_script_unknown_brand_lists_the_real_ones(script, db_session, capsys):
    _plain_brand(db_session, "Three Sixty Leather")
    assert script.main(["--brand", "Nope", "--name", "A", "--client-id", "k"]) == 2
    assert "Three Sixty Leather" in capsys.readouterr().out


def test_script_list(script, db_session, capsys):
    _plain_brand(db_session, "Three Sixty Leather")
    _plain_brand(db_session, "Indethnic")
    script.main(["--brand", "Indethnic", "--name", "NQ-tracker-Indethnic", "--client-id", "k"])
    capsys.readouterr()
    assert script.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "Three Sixty Leather  ->  default app" in out
    assert "Indethnic  ->  NQ-tracker-Indethnic" in out


# --- app home page shown inside Shopify admin ---------------------------------

def test_app_home_is_a_public_static_notice_not_the_login(client):
    """Merchants who open the app from Shopify see a notice, with no session needed."""
    r = client.get("/api/integrations/shopify/app?shop=sitarey.myshopify.com&hmac=x")
    assert r.status_code == 200
    assert "connected to NQ" in r.text
    assert "Sign in" not in r.text
