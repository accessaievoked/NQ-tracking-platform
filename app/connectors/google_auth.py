"""Google service-account auth: mint short-lived access tokens via a signed JWT.

A service account (with a downloaded JSON key) lets the backend authenticate to
Google APIs with no human and no expiring credential to babysit: we sign a JWT
with the account's private key and exchange it for a 1-hour access token, which
the service layer caches and re-mints automatically. This is the durable
alternative to OAuth Playground tokens.

Uses only `cryptography` (already a dependency) + httpx — no google-auth needed.
"""
from __future__ import annotations

import base64
import json
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
ANALYTICS_READONLY = "https://www.googleapis.com/auth/analytics.readonly"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def sign_jwt(key_info: dict, scope: str) -> str:
    """Build and RS256-sign a Google service-account assertion JWT."""
    token_uri = key_info.get("token_uri", GOOGLE_TOKEN_URI)
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": key_info["client_email"],
        "scope": scope,
        "aud": token_uri,
        "iat": now,
        "exp": now + 3600,
    }
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(claims, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode()
    private_key = serialization.load_pem_private_key(
        key_info["private_key"].encode(), password=None
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    segments.append(_b64url(signature))
    return ".".join(segments)


def mint_access_token(key_info: dict, scope: str = ANALYTICS_READONLY) -> tuple[str, int]:
    """Exchange a signed JWT for a Google access token. Returns (token, expires_in)."""
    import httpx

    token_uri = key_info.get("token_uri", GOOGLE_TOKEN_URI)
    assertion = sign_jwt(key_info, scope)
    resp = httpx.post(
        token_uri,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Google token mint failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    return data["access_token"], int(data.get("expires_in", 3600))


def refresh_access_token(
    client_id: str, client_secret: str, refresh_token: str
) -> tuple[str, int]:
    """Exchange a long-lived refresh token for a fresh access token (keyless).

    Returns (access_token, expires_in). This is the service-account-free durable
    path: authorize once, then refresh forever with no downloadable key.
    """
    import httpx

    resp = httpx.post(
        GOOGLE_TOKEN_URI,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Google token refresh failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    return data["access_token"], int(data.get("expires_in", 3600))
