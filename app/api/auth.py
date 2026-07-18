"""Auth routes: request magic link, verify, get current user."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import issue_magic_link, verify_magic_link
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import MagicLinkIssued, MagicLinkRequest, SessionOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/magic-link", response_model=MagicLinkIssued)
def request_magic_link(body: MagicLinkRequest, db: Session = Depends(get_db)):
    login_url = issue_magic_link(db, body.email)
    # In local dev, hand back the URL directly (no email service required).
    return MagicLinkIssued(sent=True, dev_login_url=login_url if settings.is_local else None)


@router.get("/verify", response_model=SessionOut)
def verify(token: str, db: Session = Depends(get_db)):
    result = verify_magic_link(db, token)
    if not result:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired link")
    user, session = result
    return SessionOut(token=session, user_id=user.id, client_id=user.client_id, email=user.email)


@router.get("/me", response_model=SessionOut)
def me(user: User = Depends(get_current_user)):
    return SessionOut(token="", user_id=user.id, client_id=user.client_id, email=user.email)
