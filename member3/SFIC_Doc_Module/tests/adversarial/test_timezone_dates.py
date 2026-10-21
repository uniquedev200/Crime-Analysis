"""Adversarial test suite: Date ambiguity and unstated timezone handling.

Tests coverage:
1. Ambiguous dd/mm date (e.g. 05/06/2023 without profile) -> normalized_iso is None, ambiguity='dmy_mdy'.
2. Ambiguous dates with profile format specified resolve to deterministic ISO dates.
3. Unambiguous dates without profile format resolve properly when day > 12.
4. Unstated timezone -> timezone is strictly None (never silently assumed IST or Asia/Kolkata).
5. Explicit timezones (IST, +05:30, UTC, Z) are assigned accurately when stated.
"""

from __future__ import annotations

import pytest

from atlas.contracts.enums import TimeAmbiguity
from atlas.normalize.dates import normalize_date
from atlas.tabular.dates import parse_date_with_profile

pytestmark = pytest.mark.gate5


@pytest.mark.gate5
@pytest.mark.parametrize(
    "ambiguous_date_str",
    [
        "05/06/2023",
        "05-06-2023",
        "01/02/2024",
        "12/11/2021",
        "07/08/2022 14:30:00",
        "03/04/2020",
    ],
)
def test_ambiguous_dd_mm_date_without_profile_sets_dmy_mdy(ambiguous_date_str: str) -> None:
    """When day <= 12 and month <= 12 and no profile is provided, ambiguity must be dmy_mdy and normalized_iso None."""
    # 1. Test tabular parse_date_with_profile
    res_tabular = parse_date_with_profile(ambiguous_date_str)
    assert res_tabular["normalized_iso"] is None
    assert res_tabular["ambiguity"] == TimeAmbiguity.DMY_MDY
    assert res_tabular["timezone"] is None

    # 2. Test normalize_date
    res_norm = normalize_date(ambiguous_date_str)
    assert res_norm["normalized_iso"] is None
    assert res_norm["ambiguity"] == "dmy_mdy"
    assert res_norm["timezone"] is None


@pytest.mark.gate5
def test_ambiguous_date_resolved_when_profile_format_provided() -> None:
    """When a profile format is provided, ambiguous day/month order is resolved deterministically."""
    sample = "05/06/2023"

    # Profile says DMY
    dmy_res = parse_date_with_profile(sample, profile_format="%d/%m/%Y")
    assert dmy_res["normalized_iso"] == "2023-06-05T00:00:00"
    assert dmy_res["ambiguity"] == TimeAmbiguity.NONE

    # Profile says MDY
    mdy_res = parse_date_with_profile(sample, profile_format="%m/%d/%Y")
    assert mdy_res["normalized_iso"] == "2023-05-06T00:00:00"
    assert mdy_res["ambiguity"] == TimeAmbiguity.NONE

    # Test with normalize_date
    dmy_norm = normalize_date(sample, profile_format="%d/%m/%Y")
    assert dmy_norm["normalized_iso"] == "2023-06-05"
    assert dmy_norm["ambiguity"] == "none"


@pytest.mark.gate5
def test_unambiguous_date_without_profile_resolves() -> None:
    """When day > 12, ordering is unambiguous even without profile format."""
    sample = "25/06/2023"

    res_tabular = parse_date_with_profile(sample)
    assert res_tabular["normalized_iso"] == "2023-06-25T00:00:00"
    assert res_tabular["ambiguity"] == TimeAmbiguity.NONE

    res_norm = normalize_date(sample)
    assert res_norm["normalized_iso"] == "2023-06-25"
    assert res_norm["ambiguity"] == "none"


@pytest.mark.gate5
@pytest.mark.parametrize(
    "date_without_tz",
    [
        "2023-05-01 10:00:00",
        "25/06/2023",
        "2023-01-15T08:30:00",
        "15-08-2022 19:45:00",
        "2024-02-29",
    ],
)
def test_unstated_timezone_never_silently_assumed_ist(date_without_tz: str) -> None:
    """Unstated timezone must remain None and NEVER be defaulted to Asia/Kolkata or IST."""
    res_tabular = parse_date_with_profile(date_without_tz)
    assert res_tabular["timezone"] is None

    res_norm = normalize_date(date_without_tz)
    assert res_norm["timezone"] is None


@pytest.mark.gate5
@pytest.mark.parametrize(
    "date_with_tz,expected_tz",
    [
        ("2023-05-01 10:00:00 IST", "Asia/Kolkata"),
        ("2023-05-01 10:00:00 +05:30", "Asia/Kolkata"),
        ("2023-05-01 10:00:00 UTC", "UTC"),
        ("2023-05-01T10:00:00Z", "UTC"),
    ],
)
def test_explicit_timezone_assigned_only_when_stated(date_with_tz: str, expected_tz: str) -> None:
    """Explicit timezone tokens in the source text are accurately mapped."""
    res_tabular = parse_date_with_profile(date_with_tz)
    assert res_tabular["timezone"] == expected_tz

    if "IST" in date_with_tz or "+05:30" in date_with_tz:
        res_norm = normalize_date(date_with_tz)
        assert res_norm["timezone"] == "Asia/Kolkata"
