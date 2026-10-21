"""Authorization and authentication contract tests for ATLAS Dev 3 API.

Verifies:
- Allowed case access succeeds.
- Unauthorized case access returns HTTP 403 Forbidden without existence leak.
- Missing X-Atlas-User defaults to demo_analyst.
- Unknown users are denied access to case endpoints.

All tests marked with @pytest.mark.gate4.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from atlas.api.app import app
from atlas.api.auth import load_demo_users

pytestmark = pytest.mark.gate4


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_load_demo_users():
    """Verify demo_users.yaml loads correctly with defined permissions."""
    users = load_demo_users()
    assert "demo_analyst" in users
    assert "restricted_user" in users

    analyst = users["demo_analyst"]
    assert analyst.can_access_case("CASE-A-001")
    assert analyst.can_access_case("CASE-B-002")
    assert not analyst.can_access_case("CASE-SECRET")

    restricted = users["restricted_user"]
    assert restricted.can_access_case("CASE-A-001")
    assert not restricted.can_access_case("CASE-B-002")


def test_default_user_header_fallback(client: TestClient):
    """When X-Atlas-User header is omitted, default demo_analyst identity is assumed."""
    # /healthz is public
    resp = client.get("/healthz")
    assert resp.status_code == 200

    # CASE-A-001 access should succeed auth check (returns 404 if no results run yet, NOT 403)
    resp = client.get("/cases/CASE-A-001/results/latest")
    assert resp.status_code != 403


def test_unauthorized_case_returns_403_without_existence_leak(client: TestClient):
    """Restricted user accessing existing vs non-existing unauthorized case both return 403 without existence leak."""
    headers = {"X-Atlas-User": "restricted_user"}

    # Existing case that restricted_user cannot access -> 403
    resp_existing = client.get("/cases/CASE-B-002/results/latest", headers=headers)
    assert resp_existing.status_code == 403
    assert "not authorized" in resp_existing.json()["detail"]

    # Completely non-existent case that restricted_user cannot access -> also 403 (zero existence leak)
    resp_nonexistent = client.get("/cases/CASE-NONEXISTENT-999/results/latest", headers=headers)
    assert resp_nonexistent.status_code == 403
    assert "not authorized" in resp_nonexistent.json()["detail"]

    # Graph endpoint also denies unauthorized case with 403
    resp_graph = client.get("/cases/CASE-B-002/graph", headers=headers)
    assert resp_graph.status_code == 403

    # Document upload denies unauthorized case with 403
    resp_upload = client.post(
        "/cases/CASE-B-002/documents",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers=headers,
    )
    assert resp_upload.status_code == 403


def test_unknown_user_denied_access(client: TestClient):
    """An unknown user header is recognized as unprivileged and denied access with 403."""
    headers = {"X-Atlas-User": "unregistered_external_user"}
    resp = client.get("/cases/CASE-A-001/results/latest", headers=headers)
    assert resp.status_code == 403
