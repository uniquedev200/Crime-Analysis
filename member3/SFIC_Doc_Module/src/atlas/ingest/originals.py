"""Content-addressed immutable store for ATLAS Dev 3 evidence originals.

Stores files at data/originals/{sha256} and enforces read-only mode.
On Windows, write denial is enforced and tested via PermissionError/os.access.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path

from atlas.ingest.integrity import verify_hash

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def store_original(path: Path, sha256: str, data_dir: Path) -> Path:
    """Store input file into content-addressed immutable storage at data_dir/originals/{sha256}.

    If the file already exists in storage, verifies its hash and reuses it without rewriting.
    Sets read-only file permissions to guarantee original bytes remain immutable.
    """
    if not isinstance(path, Path):
        path = Path(path)
    if not isinstance(data_dir, Path):
        data_dir = Path(data_dir)

    if not path.is_file():
        raise FileNotFoundError(f"Source file not found: {path}")

    clean_sha = sha256.lower().strip()
    if not _SHA256_HEX_PATTERN.match(clean_sha):
        raise ValueError(f"Invalid SHA-256 digest format: {sha256}")

    originals_dir = (data_dir / "originals").resolve()
    target_path = (originals_dir / clean_sha).resolve()

    if not target_path.is_relative_to(originals_dir):
        raise ValueError(f"Path traversal detected in SHA-256 destination: {sha256}")

    if target_path.exists():
        # Verify existing file content matches expected hash
        verify_hash(target_path, clean_sha)
        return target_path

    originals_dir.mkdir(parents=True, exist_ok=True)

    # Copy bytes directly to destination
    shutil.copyfile(path, target_path)

    # Verify integrity of written file before making read-only
    verify_hash(target_path, clean_sha)

    # Enforce read-only access (Windows FILE_ATTRIBUTE_READONLY via stat.S_IREAD)
    os.chmod(target_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    return target_path


__all__ = ["store_original"]
