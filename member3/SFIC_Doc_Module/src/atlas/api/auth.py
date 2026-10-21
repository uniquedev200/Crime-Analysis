"""Stub authentication and authorization layer for ATLAS Dev 3 API.

Implements PLAN.md Section 4.7 and J4 specifications:
- Reads X-Atlas-User header; defaults to 'demo_analyst'.
- Validates user and checks allowed_cases against config/demo_users.yaml.
- Unauthorized user gets 403 or empty response without existence leak.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import Header, HTTPException, status

from atlas.contracts.ids import validate_case_id


@dataclass
class User:
    """Authenticated user profile and authorization scope."""

    name: str
    allowed_cases: list[str]

    def can_access_case(self, case_id: str) -> bool:
        """Return True if user is authorized to access the given case."""
        return case_id in self.allowed_cases


def load_demo_users(config_path: Path | str = "config/demo_users.yaml") -> dict[str, User]:
    """Load authorized demo users and allowed_cases from YAML configuration."""
    path = Path(config_path)
    users: dict[str, User] = {}
    if path.is_file():
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "users" in data:
                for entry in data["users"]:
                    if isinstance(entry, dict) and "name" in entry:
                        u_name = str(entry["name"]).strip()
                        allowed = [str(c).strip() for c in entry.get("allowed_cases", [])]
                        users[u_name] = User(name=u_name, allowed_cases=allowed)
        except Exception:
            pass

    # Ensure demo_analyst default fallback exists
    if "demo_analyst" not in users:
        users["demo_analyst"] = User(
            name="demo_analyst",
            allowed_cases=["CASE-A-001", "CASE-B-002"],
        )
    return users


def get_current_user(x_atlas_user: Annotated[str | None, Header(alias="X-Atlas-User")] = None) -> User:
    """FastAPI dependency to extract and authenticate current user from X-Atlas-User header."""
    user_name = x_atlas_user.strip() if x_atlas_user and x_atlas_user.strip() else "demo_analyst"
    users = load_demo_users()

    if user_name in users:
        return users[user_name]

    # Unknown user: has no allowed cases
    return User(name=user_name, allowed_cases=[])


def check_case_access(case_id: str, user: User) -> None:
    """Assert user is authorized for case_id without leaking whether case exists.

    Raises:
        HTTPException 403: If user is unauthorized for case_id.
        HTTPException 400: If case_id violates regex rules.
    """
    # 1. Authorization check first — never leak case existence to unauthorized users
    if not user.can_access_case(case_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: user '{user.name}' is not authorized for case '{case_id}'",
        )

    # 2. Case ID regex validation
    try:
        validate_case_id(case_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid case identifier: {e}",
        ) from e


__all__ = ["User", "check_case_access", "get_current_user", "load_demo_users"]
