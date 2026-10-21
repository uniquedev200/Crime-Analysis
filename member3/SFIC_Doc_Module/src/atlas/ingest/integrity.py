"""Integrity verification, cryptographic hashing, and receipt generation for ATLAS Dev 3.

All file operations use UTF-8 encoding and streaming SHA-256 calculation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from atlas.contracts.ids import validate_case_id
from atlas.errors import IntegrityError

_CHUNK_SIZE: int = 65536  # 64 KB streaming buffer


def compute_sha256(path: Path) -> str:
    """Compute lowercase 64-hex SHA-256 hash by streaming file contents."""
    if not isinstance(path, Path):
        path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found for hash calculation: {path}")

    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def write_receipt(
    case_id: str,
    filename: str,
    sha256: str,
    size: int,
    run_id: str,
    out_dir: Path,
) -> Path:
    """Write receipt.json containing intake verification metadata.

    Validates case_id, writes JSON with UTF-8 encoding and ensure_ascii=False,
    and returns the Path to the written receipt.
    """
    validate_case_id(case_id)

    if not isinstance(out_dir, Path):
        out_dir = Path(out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / "receipt.json"

    clean_sha = sha256.lower().strip()
    received_at = datetime.now(UTC).isoformat()

    receipt_data = {
        "case_id": case_id,
        "filename": filename,
        "original_filename": filename,
        "sha256": clean_sha,
        "size": size,
        "size_bytes": size,
        "run_id": run_id,
        "received_at": received_at,
    }

    with receipt_path.open("w", encoding="utf-8") as f:
        json.dump(receipt_data, f, indent=2, ensure_ascii=False)

    return receipt_path


def verify_hash(path: Path, expected_sha256: str) -> None:
    """Verify that file's SHA-256 hash matches the expected hash.

    Raises IntegrityError on hash mismatch.
    """
    actual_hash = compute_sha256(path)
    clean_expected = expected_sha256.lower().strip()
    if actual_hash != clean_expected:
        raise IntegrityError(
            f"File hash mismatch for '{path.name}': expected SHA-256 '{clean_expected}', got '{actual_hash}'"
        )


__all__ = ["compute_sha256", "verify_hash", "write_receipt"]
