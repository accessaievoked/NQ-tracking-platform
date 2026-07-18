"""Magic-link auth: issue a signed short-lived link, exchange it for a session."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Client, User
from app.security import make_token, read_token

MAGIC_SALT = "magic-link"
SESSION_SALT = "session"


def issue_magic_link(db: Session, email: str) -> str:
    """Create the user (and a client) on first sight, return a login URL.

    For an in-house tool this "just works": the first time a client email is
    used, we provision it. Tighten this to an allow-list before go-live.
    """
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        client = Client(name=email.split("@")[0])
        db.add(client)
        db.flush()
        user = User(client_id=client.id, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

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
