"""End-to-end smoke test through the HTTP API (SQLite-backed)."""
from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_requires_token(client):
    assert client.get("/api/brands").status_code == 401


def test_full_flow_create_brand_and_report(auth_client):
    # Create a brand
    r = auth_client.post("/api/brands", json={"name": "Covera", "industry": "Fashion"})
    assert r.status_code == 201
    brand = r.json()
    assert brand["name"] == "Covera"
    assert len(brand["integrations"]) >= 5  # pre-seeded integration rows

    brand_id = brand["id"]

    # It shows up in the list
    listed = auth_client.get("/api/brands").json()
    assert any(b["id"] == brand_id for b in listed)

    # Generate a Money Flow report (runs full pipeline on sample data)
    r = auth_client.post(
        f"/api/brands/{brand_id}/reports",
        json={
            "type": "money_flow",
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-06T00:00:00Z",
        },
    )
    assert r.status_code == 201, r.text
    report = r.json()
    assert report["status"] == "ready", report.get("error")
    assert report["computed_metrics"]["money_in"]["total_orders"] == 6
    assert "roas" in report["narrative_md"].lower()

    # Fetch it back
    got = auth_client.get(f"/api/brands/{brand_id}/reports/{report['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == report["id"]


def test_tenancy_isolation(auth_client):
    """A brand id from one client must 404 for another client."""
    mine = auth_client.post("/api/brands", json={"name": "Mine"}).json()

    # Second, separate user/client
    issued = auth_client.post("/api/auth/magic-link", json={"email": "other@x.com"}).json()
    token = issued["dev_login_url"].split("token=", 1)[1]
    session = auth_client.get(f"/api/auth/verify?token={token}").json()

    r = auth_client.get(
        f"/api/brands/{mine['id']}",
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    assert r.status_code == 404
