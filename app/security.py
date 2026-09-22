"""Token encryption (for stored OAuth creds) and signed short-lived tokens.

Stored credentials are encrypted with Fernet. Encryption always uses the
*primary* key; decryption accepts any of the keys below, newest first, so the
primary key can be changed without breaking rows written under an older one:

  1. TOKEN_ENCRYPTION_KEY           — the primary key (a real Fernet key)
  2. TOKEN_ENCRYPTION_KEY_PREVIOUS  — optional, comma-separated retired keys
  3. the legacy dev key derived from APP_SECRET_KEY

(3) is what the app used whenever TOKEN_ENCRYPTION_KEY was empty. Keeping it as
a read-only fallback is what lets a real key be introduced with no downtime:
set the new key, and existing rows keep decrypting until
`python -m scripts.rotate_token_key --apply` re-encrypts them under it.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings


def _derived_key() -> bytes:
    """The legacy dev key: SHA-256 of the app secret, as a Fernet key."""
    digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _previous_keys() -> list[bytes]:
    raw = settings.token_encryption_key_previous or ""
    return [k.strip().encode() for k in raw.split(",") if k.strip()]


def key_ring() -> list[tuple[str, bytes]]:
    """Every key the app can decrypt with, labelled, primary first.

    Duplicates are dropped (e.g. a previous key equal to the primary) so a
    label always names the first key that would actually be tried.
    """
    primary = settings.token_encryption_key
    ring: list[tuple[str, bytes]] = [
        ("primary", primary.encode() if primary else _derived_key())
    ]
    for i, key in enumerate(_previous_keys(), start=1):
        ring.append((f"previous #{i}", key))
    ring.append(("legacy (derived from APP_SECRET_KEY)", _derived_key()))

    seen: set[bytes] = set()
    unique = []
    for label, key in ring:
        if key not in seen:
            seen.add(key)
            unique.append((label, key))
    return unique


def _primary() -> Fernet:
    return Fernet(key_ring()[0][1])


def _multi() -> MultiFernet:
    return MultiFernet([Fernet(key) for _, key in key_ring()])


def encrypt(plaintext: str) -> str:
    return _primary().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _multi().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt token — none of the configured keys match. If "
            "TOKEN_ENCRYPTION_KEY was changed, put the old key in "
            "TOKEN_ENCRYPTION_KEY_PREVIOUS."
        ) from exc


def which_key(ciphertext: str) -> str | None:
    """Label of the first key in the ring that decrypts this, or None."""
    for label, key in key_ring():
        try:
            Fernet(key).decrypt(ciphertext.encode())
            return label
        except InvalidToken:
            continue
    return None


def reencrypt(ciphertext: str) -> str:
    """Decrypt with whichever key works and re-encrypt under the primary."""
    return _multi().rotate(ciphertext.encode()).decode()


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
