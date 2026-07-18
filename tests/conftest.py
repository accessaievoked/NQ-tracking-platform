"""Pytest fixtures: in-memory SQLite DB + FastAPI TestClient.

No external Postgres needed for the test suite; JSON columns fall back to
SQLite JSON via the JSONType variant defined on the models.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(client):
    """A TestClient carrying a valid session token (magic-link flow)."""
    issued = client.post("/api/auth/magic-link", json={"email": "owner@brand.com"}).json()
    token = _token_from_url(issued["dev_login_url"])
    session = client.get(f"/api/auth/verify?token={token}").json()
    client.headers.update({"Authorization": f"Bearer {session['token']}"})
    return client


def _token_from_url(url: str) -> str:
    return url.split("token=", 1)[1]
