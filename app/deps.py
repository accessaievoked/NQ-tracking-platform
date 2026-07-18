"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import user_from_session
from app.db import get_db
from app.models import Brand, User


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = user_from_session(db, token)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return user


def get_owned_brand(
    brand_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Brand:
    """Fetch a brand and enforce it belongs to the caller's client (tenancy)."""
    brand = db.get(Brand, brand_id)
    if not brand or brand.client_id != user.client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")
    return brand
