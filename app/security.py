"""Token encryption (for stored OAuth creds) and signed short-lived tokens."""
from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings


def _fernet() -> Fernet:
    """Return a Fernet instance. Falls back to a key derived from the app
    secret in local dev so the app runs without extra setup. In production
    TOKEN_ENCRYPTION_KEY must be set to a real generated Fernet key."""
    key = settings.token_encryption_key
    if not key:
        digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise ValueError("Could not decrypt token") from exc


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
