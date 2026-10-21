"""Synthetic data guard enforcing synthetic manifest verification for live providers.

Hard Rule 1: Synthetic data only. The live LLM client refuses any file whose SHA-256
is not in data/synthetic_manifest.json while ATLAS_SYNTHETIC_ONLY=true.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from atlas.errors import RejectedInputError


def _hash_in_manifest(target_hash: str, data: Any) -> bool:
    """Check if target_hash exists anywhere in arbitrary manifest JSON structure."""
    target_hash = target_hash.lower().strip()

    if isinstance(data, list):
        for item in data:
            if isinstance(item, str) and item.lower().strip() == target_hash:
                return True
            if isinstance(item, dict):
                # Check sha256 / hash / file_sha256 keys
                for key in ("sha256", "hash", "file_sha256", "id"):
                    val = item.get(key)
                    if isinstance(val, str) and val.lower().strip() == target_hash:
                        return True
        return False

    if isinstance(data, dict):
        # Direct key lookup
        lowered_keys = {str(k).lower().strip() for k in data}
        if target_hash in lowered_keys:
            return True

        # Check common collection keys: files, hashes, records, items
        for key in ("files", "hashes", "records", "items", "manifest"):
            if key in data and _hash_in_manifest(target_hash, data[key]):
                return True

        # Check values
        for val in data.values():
            if isinstance(val, (dict, list)) and _hash_in_manifest(target_hash, val):
                return True

    return False


def check_synthetic(sha256: str, provider: str, manifest_path: Path) -> None:
    """Enforce that files processed with non-mock providers are present in the synthetic manifest.

    If ATLAS_SYNTHETIC_ONLY is true and provider != "mock", raises RejectedInputError
    if the file's SHA-256 hash cannot be verified against the manifest.
    """
    env_synthetic_only = os.getenv("ATLAS_SYNTHETIC_ONLY", "true").strip().lower()
    is_synthetic_only = env_synthetic_only in ("true", "1", "yes")

    if not is_synthetic_only:
        return

    # Mock provider is exempt from synthetic manifest enforcement
    if provider.lower().strip() == "mock":
        return

    if not isinstance(manifest_path, Path):
        manifest_path = Path(manifest_path)

    if not manifest_path.is_file():
        raise RejectedInputError(
            f"Synthetic data guard violation: synthetic manifest file not found at '{manifest_path}'. "
            f"Non-mock provider '{provider}' cannot process unverified input."
        )

    try:
        content = manifest_path.read_text(encoding="utf-8")
        manifest_data = json.loads(content)
    except Exception as exc:
        raise RejectedInputError(
            f"Synthetic data guard violation: failed to read synthetic manifest '{manifest_path}': {exc}"
        ) from exc

    clean_sha = sha256.lower().strip()
    if not _hash_in_manifest(clean_sha, manifest_data):
        raise RejectedInputError(
            f"Synthetic data guard refused file: SHA-256 '{clean_sha}' is not present in "
            f"synthetic manifest '{manifest_path.name}'. Live provider '{provider}' requires verified synthetic data."
        )


def register_synthetic_files(paths: Iterable[Path | str], manifest_path: Path) -> int:
    """Add the SHA-256 of each existing file to the synthetic manifest.

    Registering is the explicit human attestation required by Hard Rule 1: a file
    becomes eligible for live providers only after a person declares it synthetic
    by recording its hash here. The manifest format matches
    ``python -m atlas register-synthetic`` (a JSON object mapping sha256 -> name).

    Args:
        paths: Files to register. Missing paths are skipped.
        manifest_path: Manifest JSON to create or extend.

    Returns:
        int: Number of files whose hash was written to the manifest.
    """
    manifest = Path(manifest_path)
    data: dict[str, str] = {}
    if manifest.is_file():
        try:
            loaded = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        if isinstance(loaded, dict):
            data = {str(k): str(v) for k, v in loaded.items()}

    added = 0
    for item in paths:
        candidate = Path(item)
        if not candidate.is_file():
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        data[digest] = candidate.name
        added += 1

    manifest.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
    return added


__all__ = ["check_synthetic", "register_synthetic_files"]
