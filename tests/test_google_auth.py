"""Tests for Google service-account JWT signing + token minting."""
from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.connectors import google_auth


def _make_key_info():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "client_email": "svc@project.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": google_auth.GOOGLE_TOKEN_URI,
    }, key.public_key()


def _b64pad(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def test_sign_jwt_is_verifiable():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    key_info, public_key = _make_key_info()
    token = google_auth.sign_jwt(key_info, google_auth.ANALYTICS_READONLY)
    header_b64, claims_b64, sig_b64 = token.split(".")

    claims = json.loads(_b64pad(claims_b64))
    assert claims["iss"] == "svc@project.iam.gserviceaccount.com"
    assert claims["scope"] == google_auth.ANALYTICS_READONLY
    assert claims["exp"] > claims["iat"]

    # Signature verifies against the public key (raises if invalid).
    public_key.verify(
        _b64pad(sig_b64),
        f"{header_b64}.{claims_b64}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def test_mint_access_token(monkeypatch):
    import httpx

    key_info, _ = _make_key_info()

    class FakeResp:
        status_code = 200

        def json(self):
            return {"access_token": "ya29.fake", "expires_in": 3599}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    token, expires_in = google_auth.mint_access_token(key_info)
    assert token == "ya29.fake"
    assert expires_in == 3599


def test_refresh_access_token(monkeypatch):
    import httpx

    class FakeResp:
        status_code = 200

        def json(self):
            return {"access_token": "ya29.refreshed", "expires_in": 3600}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    token, expires_in = google_auth.refresh_access_token("cid", "csecret", "rtok")
    assert token == "ya29.refreshed"
    assert expires_in == 3600
