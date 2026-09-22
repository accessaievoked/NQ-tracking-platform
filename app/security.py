"""Token encryption (for stored OAuth creds) and signed short-lived tokens.

Stored integration credentials are encrypted with one Fernet key,
TOKEN_ENCRYPTION_KEY. Locally, if it is empty, a dev key is derived from
APP_SECRET_KEY so the app runs without setup; in production it must be set.

`check_encryption_key()` runs at startup, so a missing or malformed key stops
the app from booting — and fails the deploy's health check, leaving the
previous release serving — instead of breaking every credential read later.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings


def _key() -> bytes:
    key = settings.token_encryption_key.strip()
    if key:
        return key.encode()
    if not settings.is_local:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is not set. It is required outside local dev — "
            "generate one with: python -m scripts.generate_encryption_key"
        )
    digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_key())


def check_encryption_key() -> None:
    """Fail fast, with a readable message, if the key can't be used."""
    try:
        _fernet()
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is not a valid Fernet key — it should be 44 "
            "url-safe base64 characters ending in '='. Generate one with: "
            "python -m scripts.generate_encryption_key"
        ) from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt stored credentials — they were saved under a "
            "different TOKEN_ENCRYPTION_KEY. Reconnect this integration."
        ) from exc


# --- Signed, expiring tokens (magic links & sessions) ---

def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.app_secret_key, salt=salt)


def make_token(payload: dict[str, Any], salt: str) -> str:
    return _serializer(salt).dumps(payload)


def read_token(token: str, salt: str, max_age_seconds: int) -> dict[str, Any] | None:
    try:
        return _serializer(salt).loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
