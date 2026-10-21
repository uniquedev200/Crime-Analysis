"""Contract tests for Dev2Client HTTP adapter using respx.

Simulates Dev 2 responses, network errors, auth errors, and verifies explicit failure reporting.
All tests marked with @pytest.mark.gate4.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from atlas.adapters.dev2_http import Dev2Client
from atlas.contracts.enums import ReviewActionType
from atlas.contracts.records import ReviewAction
from atlas.errors import AuthorizationError, ProviderError

pytestmark = pytest.mark.gate4


@respx.mock
def test_get_case_permissions_success():
    """dev2_client.get_case_permissions returns user permissions successfully."""
    base_url = "https://dev2.police.gov.in"
    respx.get(f"{base_url}/users/analyst_1/permissions").respond(
        status_code=200,
        json={"user": "analyst_1", "allowed_cases": ["CASE-A-001", "CASE-B-002"], "state": "ok"},
    )

    with Dev2Client(base_url=base_url, token="secret_token") as client:
        result = client.get_case_permissions("analyst_1")

    assert result["user"] == "analyst_1"
    assert "CASE-A-001" in result["allowed_cases"]


@respx.mock
def test_get_case_permissions_auth_failure():
    """dev2_client.get_case_permissions raises AuthorizationError on 401 or 403."""
    base_url = "https://dev2.police.gov.in"
    respx.get(f"{base_url}/users/unauthorized_user/permissions").respond(
        status_code=403,
        text="Forbidden: Token expired or invalid scope",
    )

    with Dev2Client(base_url=base_url) as client, pytest.raises(AuthorizationError, match="Dev 2 authorization failed"):
        client.get_case_permissions("unauthorized_user")


@respx.mock
def test_get_case_permissions_server_error():
    """dev2_client.get_case_permissions raises ProviderError on 500 error."""
    base_url = "https://dev2.police.gov.in"
    respx.get(f"{base_url}/users/analyst_1/permissions").respond(
        status_code=500,
        text="Internal Server Error",
    )

    with Dev2Client(base_url=base_url) as client, pytest.raises(ProviderError, match="Dev 2 provider error"):
        client.get_case_permissions("analyst_1")


@respx.mock
def test_notify_review_action_success():
    """dev2_client.notify_review_action transmits review action audit record."""
    base_url = "https://dev2.police.gov.in"
    respx.post(f"{base_url}/review/actions/notify").respond(
        status_code=200,
        json={"status": "delivered", "action_id": "ACT-1234567890ab", "state": "ok"},
    )

    action = ReviewAction(
        action_id="ACT-1234567890ab",
        type=ReviewActionType.CONFIRM_IDENTIFIER,
        actor="demo_analyst",
        at="2026-10-16T12:00:00Z",
        reason="Visual confirmation on FIR page 1",
        target_ids=["M-1"],
        payload={"trust": "strong"},
        prev_hash="0000000000000000000000000000000000000000000000000000000000000000",
        entry_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        case_id="CASE-A-001",
    )

    with Dev2Client(base_url=base_url) as client:
        result = client.notify_review_action(action)

    assert result["status"] == "delivered"
    assert result["action_id"] == "ACT-1234567890ab"


@respx.mock
def test_notify_review_action_explicit_failure_rejection():
    """Dev 2 returning success: false raises ProviderError and prevents partial writes from claiming success."""
    base_url = "https://dev2.police.gov.in"
    respx.post(f"{base_url}/review/actions/notify").respond(
        status_code=200,
        json={"success": False, "error": "Audit persistence conflict: duplicate action_id"},
    )

    with (
        Dev2Client(base_url=base_url) as client,
        pytest.raises(ProviderError, match="Dev 2 rejected notify_review_action"),
    ):
        client.notify_review_action({"action_id": "ACT-DUP", "type": "MERGE"})


@respx.mock
def test_sync_evidence_network_error():
    """Network connection timeout raises ProviderError."""
    base_url = "https://dev2.police.gov.in"
    respx.post(f"{base_url}/cases/CASE-A-001/evidence/sync").mock(
        side_effect=httpx.ConnectTimeout("Connection timed out")
    )

    with Dev2Client(base_url=base_url) as client, pytest.raises(ProviderError, match="Network error syncing evidence"):
        client.sync_evidence("CASE-A-001", {"mentions": []})
