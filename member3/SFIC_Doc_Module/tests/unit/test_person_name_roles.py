"""Gate 1 unit tests: role words must not swallow genuinely named persons.

Police documents routinely write "Sub-Inspector K. Rathore" or "Officer Ramesh
Kumar": the person is named, so the mention must survive. Bare roles with no name
token ("Investigating Officer", "Accused") and narration phrases must still be
rejected. The lexicons themselves live in ``config/entity_filters.yaml``.
"""

from __future__ import annotations

import pytest

from atlas.normalize.names import is_valid_person_name

pytestmark = pytest.mark.gate1


@pytest.mark.parametrize(
    "name_with_rank",
    [
        "Sub-Inspector K. Rathore",
        "Sub Inspector K. Rathore",
        "Officer Ramesh Kumar",
        "Inspector Rajesh Sharma",
        "Constable Suresh Yadav",
        "SHO Balbir Singh",
        "Complainant Vikram Singh",
        "Accused Pooja Sharma",
        "Witness Sunita Devi",
    ],
)
def test_rank_prefixes_with_a_real_name_are_kept(name_with_rank: str) -> None:
    """A rank/role prefix followed by a genuine name token is still a person."""
    assert is_valid_person_name(name_with_rank) is True


@pytest.mark.parametrize(
    "bare_role",
    [
        "Inspector",
        "Inspector K",
        "Sub-Inspector",
        "Officer",
        "Investigating Officer",
        "Constable",
        "The officer",
    ],
)
def test_bare_roles_remain_rejected(bare_role: str) -> None:
    """Without a name token the role phrase stays a non-person."""
    assert is_valid_person_name(bare_role) is False, bare_role


@pytest.mark.parametrize(
    "narration",
    [
        "Ordinary c.",
        "Service Reversal",
        "NEFT Reversal",
        "Cash Deposit Charges",
        "Bank charges reversal",
    ],
)
def test_narration_vocabulary_stays_rejected(narration: str) -> None:
    """Narration words disqualify a phrase regardless of other tokens."""
    assert is_valid_person_name(narration) is False, narration
