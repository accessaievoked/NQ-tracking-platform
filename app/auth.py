"""Magic-link auth: issue a signed short-lived link, exchange it for a session."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Brand, Client, User
from app.security import make_token, read_token

MAGIC_SALT = "magic-link"
SESSION_SALT = "session"


def register_user(db: Session, email: str, name: str | None = None) -> User:
    """Whitelist an email so it can sign in (admin action). On first registration
    it provisions the whole account — client, user, and a first brand — all named
    after ``name`` (falling back to the email prefix). No brand-creation UI is
    needed: every account starts with one ready to connect."""
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        display = name or email.split("@")[0]
        client = Client(name=display)
        db.add(client)
        db.flush()
        user = User(client_id=client.id, email=email, name=display)
        db.add(user)
        db.add(Brand(client_id=client.id, name=display))  # first brand = same name
        db.commit()
        db.refresh(user)
    return user


def issue_magic_link(db: Session, email: str) -> str | None:
    """Return a login URL ONLY for a pre-registered, active email; else None.

    Accounts are no longer auto-provisioned on login — an admin must register
    the email first (see scripts/register_user.py). This is the allow-list.
    """
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        return None
    token = make_token({"uid": user.id}, salt=MAGIC_SALT)
    return f"{settings.app_base_url}/api/auth/verify?token={token}"


def verify_magic_link(db: Session, token: str) -> tuple[User, str] | None:
    data = read_token(token, salt=MAGIC_SALT, max_age_seconds=settings.magic_link_ttl_minutes * 60)
    if not data:
        return None
    user = db.get(User, data["uid"])
    if not user or not user.is_active:
        return None
    session = make_token({"uid": user.id}, salt=SESSION_SALT)
    return user, session


def user_from_session(db: Session, token: str) -> User | None:
    data = read_token(token, salt=SESSION_SALT, max_age_seconds=settings.session_ttl_hours * 3600)
    if not data:
        return None
    user = db.get(User, data["uid"])
    return user if (user and user.is_active) else None
