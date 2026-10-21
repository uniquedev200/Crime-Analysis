"""Dev 2 HTTP REST client adapter for permissions, review notifications, and evidence sync.

Implements PLAN.md Section 4.7, 5.10 and J4 specifications:
- Uses httpx.Client with configurable timeout from config/defaults.yaml.
- Endpoints: get_case_permissions, notify_review_action, sync_evidence.
- Robust error handling: maps HTTP 401/403 to AuthorizationError,
  5xx and network failures to ProviderError with explicit error states.
- No partial writes reported as success.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml

from atlas.contracts.records import ReviewAction
from atlas.errors import AuthorizationError, ProviderError


def _load_dev2_defaults() -> tuple[str, float]:
    """Load default Dev 2 base URL and timeout from config/defaults.yaml."""
    base_url = ""
    timeout_s = 30.0
    defaults_path = Path("config/defaults.yaml")
    if defaults_path.is_file():
        try:
            content = defaults_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                base_url = str(data.get("dev2_base_url", "")).strip()
                if "dev2_timeout_s" in data:
                    timeout_s = float(data["dev2_timeout_s"])
        except Exception:
            pass
    return base_url, timeout_s


class Dev2Client:
    """HTTP client for Dev 2 platform integration."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        default_url, default_timeout = _load_dev2_defaults()
        self.base_url = (base_url if base_url is not None else default_url).rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else default_timeout
        self.token = token

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._client = httpx.Client(
            base_url=self.base_url if self.base_url else "http://localhost",
            timeout=self.timeout_s,
            headers=headers,
        )

    def __enter__(self) -> Dev2Client:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close underlying httpx client transport."""
        self._client.close()

    def _handle_response(self, response: httpx.Response, action_desc: str) -> dict[str, Any]:
        """Validate response status and parse JSON, mapping failures to ATLAS domain errors."""
        if response.status_code in (401, 403):
            raise AuthorizationError(
                f"Dev 2 authorization failed ({response.status_code}) during {action_desc}: {response.text}"
            )

        if response.status_code >= 400:
            raise ProviderError(f"Dev 2 provider error ({response.status_code}) during {action_desc}: {response.text}")

        try:
            data = response.json()
        except Exception as e:
            raise ProviderError(f"Dev 2 returned non-JSON response during {action_desc}: {e}") from e

        if isinstance(data, dict) and data.get("success") is False:
            err_msg = data.get("error") or data.get("message") or "Operation reported failure"
            raise ProviderError(f"Dev 2 rejected {action_desc}: {err_msg}")

        return data if isinstance(data, dict) else {"data": data, "state": "ok"}

    def get_case_permissions(self, user_name: str) -> dict[str, Any]:
        """Query case permissions for a given user from Dev 2.

        Args:
            user_name: Username to query.

        Returns:
            Dict containing user details and allowed_cases.

        Raises:
            AuthorizationError: On 401 or 403 HTTP response.
            ProviderError: On network or server failure.
        """
        url = f"/users/{user_name}/permissions"
        try:
            resp = self._client.get(url)
            return self._handle_response(resp, f"get_case_permissions for '{user_name}'")
        except httpx.RequestError as e:
            raise ProviderError(f"Network error querying Dev 2 case permissions: {e}") from e

    def notify_review_action(self, action: ReviewAction | dict[str, Any]) -> dict[str, Any]:
        """Notify Dev 2 of a completed human review decision.

        Args:
            action: ReviewAction record or equivalent dictionary.

        Returns:
            Delivery receipt dictionary from Dev 2.

        Raises:
            AuthorizationError: On 401 or 403 HTTP response.
            ProviderError: On network, server, or validation failure.
        """
        payload = action.model_dump(mode="json") if isinstance(action, ReviewAction) else dict(action)
        url = "/review/actions/notify"
        try:
            resp = self._client.post(url, json=payload)
            result = self._handle_response(resp, f"notify_review_action for '{payload.get('action_id')}'")
            return result
        except httpx.RequestError as e:
            raise ProviderError(f"Network error notifying Dev 2 of review action: {e}") from e

    def sync_evidence(self, case_id: str, evidence_payload: dict[str, Any]) -> dict[str, Any]:
        """Synchronize evidence facts and metadata for a case with Dev 2.

        Args:
            case_id: Target case identifier.
            evidence_payload: Evidence facts payload.

        Returns:
            Sync confirmation dictionary from Dev 2.

        Raises:
            AuthorizationError: On 401 or 403 HTTP response.
            ProviderError: On network, server, or validation failure.
        """
        url = f"/cases/{case_id}/evidence/sync"
        try:
            resp = self._client.post(url, json=evidence_payload)
            result = self._handle_response(resp, f"sync_evidence for case '{case_id}'")
            return result
        except httpx.RequestError as e:
            raise ProviderError(f"Network error syncing evidence with Dev 2: {e}") from e


__all__ = ["Dev2Client"]
