"""Deterministic name normalization and key generation.

Implements Indian personal name key generation (name_key),
honorific stripping, patronymic/relative relation parsing,
script preservation, and configuration-driven person-name validation.

The person-name filter lexicons (generic phrases, unnamed roles, transaction
narrations, function words) live in ``config/entity_filters.yaml`` and are loaded
at runtime. No entity strings are hardcoded in this module.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

# Common Indian and English honorifics (case-insensitive)
_HONORIFICS_RE = re.compile(
    r"\b(?:shri|shree|sri|smt|shrimati|mr|mrs|ms|miss|dr|prof|adv|kumari|km|master|late)\b\.?\s*",
    re.IGNORECASE,
)

# Common Indian patronymic / relative relation patterns (S/o, D/o, W/o, father)
_PATRONYMIC_RE = re.compile(
    r"[\s,]+(?:s/o|d/o|w/o|c/o|s\.o\.|d\.o\.|w\.o\.|c\.o\.|"
    r"son\s+of|daughter\s+of|wife\s+of|care\s+of|"
    r"father(?:'s)?(?:\s+name)?(?:\s*[:=-]|\s+is)?|"
    r"husband(?:'s)?(?:\s+name)?(?:\s*[:=-]|\s+is)?)\s*[:=-]?\s*",
    re.IGNORECASE,
)

_DEFAULT_FILTER_FILENAME = "entity_filters.yaml"
_ENTITY_FILTER_CONFIG_ENV = "ENTITY_FILTER_CONFIG"


@dataclass(frozen=True)
class PersonNameFilter:
    """Runtime lexicon used to decide whether a surface text is a person's name.

    All fields are loaded from a YAML file so behaviour can be tuned without
    modifying code. Matching is case-insensitive and whitespace/punctuation
    insensitive.
    """

    min_letters: int = 2
    max_tokens: int = 8
    function_words: frozenset[str] = frozenset()
    generic_terms: frozenset[str] = frozenset()
    role_terms: frozenset[str] = frozenset()
    narration_terms: frozenset[str] = frozenset()
    narration_phrases: frozenset[str] = frozenset()
    generic_prefixes: frozenset[str] = frozenset()

    @property
    def non_name_words(self) -> frozenset[str]:
        """Union of generic, role and narration tokens."""
        return self.generic_terms | self.role_terms | self.narration_terms

    @property
    def reject_phrases(self) -> frozenset[str]:
        """Whole phrases that always indicate a non-person string."""
        return self.generic_terms | self.role_terms | self.narration_phrases


def _remove_punctuation(text: str) -> str:
    """Replace Unicode punctuation and symbols with spaces, preserving letters/marks."""
    chars: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith(("P", "S")):
            chars.append(" ")
        else:
            chars.append(ch)
    return "".join(chars)


def _normalize_phrase(text: str) -> str:
    """Casefold and collapse a phrase for lexicon matching (punctuation removed)."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    normalized = _remove_punctuation(normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().casefold()


def _lexicon(entries: object) -> frozenset[str]:
    """Parse a YAML list into a normalized frozenset of phrases."""
    if not isinstance(entries, list):
        return frozenset()
    values: set[str] = set()
    for entry in entries:
        if entry is None:
            continue
        normalized = _normalize_phrase(str(entry))
        if normalized:
            values.add(normalized)
    return frozenset(values)


def _candidate_filter_paths(explicit: Path | None) -> Iterator[Path]:
    """Yield candidate config paths in priority order."""
    if explicit is not None:
        yield explicit
    env_path = os.environ.get(_ENTITY_FILTER_CONFIG_ENV, "").strip()
    if env_path:
        yield Path(env_path)
    yield Path("config") / _DEFAULT_FILTER_FILENAME
    yield Path(__file__).resolve().parents[3] / "config" / _DEFAULT_FILTER_FILENAME


@lru_cache(maxsize=8)
def _load_filter_file(resolved_path: str) -> PersonNameFilter:
    """Load and cache a PersonNameFilter from an absolute file path."""
    text = Path(resolved_path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    person = data.get("person", {}) if isinstance(data, dict) else {}
    if not isinstance(person, dict):
        person = {}

    def _coerce_int(value: object, fallback: int) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return fallback
        return fallback

    return PersonNameFilter(
        min_letters=_coerce_int(person.get("min_letters"), 2),
        max_tokens=_coerce_int(person.get("max_tokens"), 8),
        function_words=_lexicon(person.get("function_words")),
        generic_terms=_lexicon(person.get("generic_terms")),
        role_terms=_lexicon(person.get("role_terms")),
        narration_terms=_lexicon(person.get("narration_terms")),
        narration_phrases=_lexicon(person.get("narration_phrases")),
        generic_prefixes=_lexicon(person.get("generic_prefixes")),
    )


def load_person_name_filter(config_path: Path | str | None = None) -> PersonNameFilter:
    """Load the person-name filter lexicon from configuration.

    Resolution order: an explicit ``config_path`` argument, the
    ``ENTITY_FILTER_CONFIG`` environment variable, ``config/entity_filters.yaml``
    relative to the current directory, then the packaged repository default.

    If no configuration is found an empty (permissive) filter is returned so the
    pipeline keeps running; the caller should treat a missing lexicon as a
    configuration problem rather than as silent name approval.
    """
    explicit = Path(config_path) if config_path is not None else None
    for candidate in _candidate_filter_paths(explicit):
        try:
            if candidate.is_file():
                return _load_filter_file(str(candidate.resolve()))
        except (OSError, yaml.YAMLError):
            continue
    return PersonNameFilter()


def is_valid_person_name(name: str, name_filter: PersonNameFilter | None = None) -> bool:
    """Validate whether an extracted surface text represents a genuine person name.

    Rejects generic noun phrases ('The Person', 'Unknown Person'), bare legal
    roles ('Accused', 'Complainant', 'Investigating Officer') and transaction
    narrations ('Service Reversal', 'Ordinary course of business') using the
    externalized lexicon in ``config/entity_filters.yaml`` plus structural rules.

    Args:
        name: Raw surface text extracted for a PERSON entity.
        name_filter: Optional pre-loaded filter lexicon (avoids re-reading config).

    Returns:
        bool: True if the string is plausible as an individual's name, False otherwise.
    """
    if not name or not isinstance(name, str):
        return False

    spec = name_filter or load_person_name_filter()

    raw_clean = name.strip(" \t\n\r\"'.,;:()[]{}")
    if not raw_clean:
        return False

    # Must contain at least `min_letters` alphabetic characters across all scripts
    letters = [ch for ch in raw_clean if unicodedata.category(ch).startswith("L")]
    if len(letters) < spec.min_letters:
        return False

    normalized = _normalize_phrase(raw_clean)
    if not normalized:
        return False

    # Strip honorifics (Dr., Shri, Smt., ...) before structural checks.
    stripped = _normalize_phrase(strip_honorifics(raw_clean))
    if not stripped:
        return False

    tokens = stripped.split()
    if not tokens or len(tokens) > spec.max_tokens:
        return False

    # Whole-phrase rejections (generic placeholders, roles, narrations).
    if normalized in spec.reject_phrases or stripped in spec.reject_phrases:
        return False

    # Grammar function words never occur inside a personal name.
    if any(token in spec.function_words for token in tokens):
        return False

    # Modifier prefix on a short generic phrase ("unknown male", "said person").
    if tokens[0] in spec.generic_prefixes and len(tokens) <= 2:
        return False

    # Transaction / banking narration vocabulary never occurs inside a personal name,
    # even when other tokens are present ("Ordinary c.", "NEFT reversal charges").
    if any(token in spec.narration_terms for token in tokens):
        return False

    # A role word disqualifies the phrase only when no genuine name token remains:
    # "Investigating Officer" and "Inspector K" are bare roles, while
    # "Sub-Inspector K. Rathore" or "Officer Ramesh Kumar" name a real person and
    # must be kept (the role itself is captured separately in `stated_role`).
    if any(token in spec.role_terms for token in tokens):
        name_tokens = [token for token in tokens if token not in spec.non_name_words]
        if not any(len(token) > 1 for token in name_tokens):
            return False

    # A phrase made entirely of generic words is not a name.
    return not all(token in spec.non_name_words for token in tokens)


def strip_honorifics(name: str) -> str:
    """Remove honorific prefixes and titles from a personal name.

    Handles titles such as Shri, Smt, Mr, Mrs, Ms, Dr, Sri, Prof, Adv, Kumari, Late, etc.,
    preserving internal name parts that contain those letters (e.g. Sridhar, Mridula).

    Args:
        name: Raw person name.

    Returns:
        str: Name with honorific prefixes stripped.
    """
    if not name:
        return ""
    cleaned = _HONORIFICS_RE.sub("", name).strip()
    return cleaned


def parse_patronymic(name: str) -> tuple[str, str | None]:
    """Parse patronymic, marital, or care-of relative relations from a person name.

    Recognizes patterns such as S/o (son of), D/o (daughter of), W/o (wife of),
    C/o (care of), and explicit father name declarations.

    Args:
        name: Full raw name string (e.g. 'Vikram Singh S/o Ramesh Singh').

    Returns:
        tuple[str, str | None]: (primary_person_name, relative_name_or_none)
    """
    if not name or not name.strip():
        return "", None

    match = _PATRONYMIC_RE.search(name)
    if not match:
        return name.strip(), None

    primary = name[: match.start()].strip(" ,;:-")
    relative = name[match.end() :].strip(" ,;:-")
    return primary, (relative if relative else None)


def name_key(name: str) -> str:
    """Generate a deterministic normalized key for candidate name matching.

    Rules applied:
    1. Unicode NFC normalization.
    2. Strip honorifics (shri, smt, mr, mrs, ms, dr, sri, etc.).
    3. Casefold.
    4. Remove punctuation (Unicode-safe).
    5. Normalize consonant variants: w -> v, ph -> f.
    6. Collapse repeated characters (aa -> a, oo -> o, mm -> m).
    7. Trailing 'h' drop on tokens of length > 1.
    8. u/a vowel folding (initial u folds to a; non-initial u and a are dropped).
    9. Separate initials from full words and sort initials deterministically.
    10. Mixed-script and non-Latin scripts are preserved.

    Args:
        name: Input person name.

    Returns:
        str: Deterministic name key.
    """
    if not name or not name.strip():
        return ""

    # 1. Unicode NFC
    s = unicodedata.normalize("NFC", name)

    # 2. Strip honorifics
    s = strip_honorifics(s)

    # 3. Casefold
    s = s.casefold()

    # 4. Remove punctuation
    s = _remove_punctuation(s)

    # 5. Normalize common consonant variants: ph -> f, w -> v
    s = re.sub(r"ph", "f", s)
    s = re.sub(r"w", "v", s)

    # 6. Collapse consecutive repeated characters
    s = re.sub(r"(.)\1+", r"\1", s)

    tokens = s.split()
    if not tokens:
        return ""

    words: list[str] = []
    initials: list[str] = []

    for token in tokens:
        # 7. Trailing h drop on words
        if len(token) > 1 and token.endswith("h"):
            token = token[:-1]

        # 8. u/a vowel folding
        if len(token) > 0:
            first_char = "a" if token[0] in ("u", "a") else token[0]
            rest = re.sub(r"[ua]", "", token[1:])
            token = first_char + rest

        if len(token) == 1:
            initials.append(token)
        elif len(token) > 1:
            words.append(token)

    # 9. Sort initials separately
    initials.sort()

    # Join words followed by sorted initials
    return " ".join(words + initials)


__all__ = [
    "PersonNameFilter",
    "is_valid_person_name",
    "load_person_name_filter",
    "name_key",
    "parse_patronymic",
    "strip_honorifics",
]
