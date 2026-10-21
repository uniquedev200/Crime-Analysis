"""Gate 1 unit tests proving the person-name filter is configuration-driven.

These tests demonstrate that filtering behaviour can be changed purely by editing
a YAML lexicon (or pointing ENTITY_FILTER_CONFIG elsewhere) with no code change.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.normalize import names as names_mod
from atlas.normalize.names import PersonNameFilter, is_valid_person_name, load_person_name_filter


@pytest.fixture(autouse=True)
def _clear_filter_cache() -> None:
    """Ensure each test reloads configuration rather than reusing a cached file."""
    names_mod._load_filter_file.cache_clear()


@pytest.mark.gate1
def test_custom_lexicon_changes_behaviour_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A term rejected only via a custom config proves the lexicon is not hardcoded."""
    # Baseline: this invented phrase is not in the shipped lexicon.
    assert is_valid_person_name("Zarnov Qelth") is True

    custom = tmp_path / "filters.yaml"
    custom.write_text(
        "person:\n"
        "  generic_terms:\n"
        "    - zarnov qelth\n"
        "  role_terms: []\n"
        "  narration_terms: []\n"
        "  function_words: []\n"
        "  narration_phrases: []\n"
        "  generic_prefixes: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENTITY_FILTER_CONFIG", str(custom))
    names_mod._load_filter_file.cache_clear()

    assert is_valid_person_name("Zarnov Qelth") is False
    assert is_valid_person_name("Vikram Singh") is True


@pytest.mark.gate1
def test_explicit_config_path_argument(tmp_path: Path) -> None:
    """An explicit config path is honoured over the environment/default."""
    custom = tmp_path / "explicit.yaml"
    custom.write_text(
        "person:\n  min_letters: 5\n",
        encoding="utf-8",
    )
    spec = load_person_name_filter(custom)
    assert spec.min_letters == 5
    # "Ram" has 3 letters and must now be rejected by the custom minimum.
    assert is_valid_person_name("Ram", spec) is False


@pytest.mark.gate1
def test_structural_rules_do_not_need_a_lexicon_entry() -> None:
    """Grammar function words are rejected structurally, not by an entity blacklist."""
    spec = PersonNameFilter(function_words=frozenset({"the"}), min_letters=2, max_tokens=8)
    assert is_valid_person_name("The Person", spec) is False
    assert is_valid_person_name("Vikram Singh", spec) is True


@pytest.mark.gate1
def test_shipped_config_rejects_generic_and_narration_terms() -> None:
    """Default shipped lexicon catches generic phrases, roles and narrations."""
    for invalid in ("The Person", "Unknown Person", "Complainant", "Service Reversal", "Ordinary course of business"):
        assert is_valid_person_name(invalid) is False, invalid
    for valid in ("Vikram Singh", "Pooja Sharma", "Mohammad Ali", "विक्रम सिंह"):
        assert is_valid_person_name(valid) is True, valid
