"""Unit tests for ingestion integrity, immutable store, receipts, and synthetic guard.

All tests are marked @pytest.mark.gate1 and use UTF-8 encoding.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from atlas.contracts.ids import make_run_id
from atlas.errors import IntegrityError, RejectedInputError
from atlas.ingest.integrity import compute_sha256, verify_hash, write_receipt
from atlas.ingest.originals import store_original
from atlas.ingest.synthetic_guard import check_synthetic


@pytest.mark.gate1
def test_sha256_stability_and_sensitivity(tmp_path: Path) -> None:
    """Hash must be stable across multiple reads, match hashlib, and change when content changes."""
    file_path = tmp_path / "test_data.txt"
    content_a = b"Synthetic evidence line for Case-001.\n"
    file_path.write_bytes(content_a)

    expected_hash = hashlib.sha256(content_a).hexdigest()
    hash_1 = compute_sha256(file_path)
    hash_2 = compute_sha256(file_path)

    assert hash_1 == expected_hash
    assert hash_2 == expected_hash

    # Modify single byte
    content_b = b"Synthetic evidence line for Case-002.\n"
    file_path.write_bytes(content_b)
    hash_3 = compute_sha256(file_path)
    assert hash_3 != hash_1
    assert hash_3 == hashlib.sha256(content_b).hexdigest()


@pytest.mark.gate1
def test_verify_hash_success_and_failure(tmp_path: Path) -> None:
    """verify_hash passes on exact match and raises IntegrityError on corruption or mismatch."""
    sample = tmp_path / "verify.txt"
    sample.write_text("Integrity content test", encoding="utf-8")
    actual_sha = compute_sha256(sample)

    # Success case
    verify_hash(sample, actual_sha)
    verify_hash(sample, actual_sha.upper())  # case-insensitive check

    # Failure case
    wrong_sha = "0" * 64
    with pytest.raises(IntegrityError) as exc_info:
        verify_hash(sample, wrong_sha)
    assert "mismatch" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_write_receipt_fields_and_utf8(tmp_path: Path) -> None:
    """write_receipt generates receipt.json with all required metadata and UTF-8 encoding."""
    out_dir = tmp_path / "case_output"
    case_id = "CASE_SYNTH_001"
    run_id = make_run_id()
    sha256 = "a" * 64
    size = 4096
    filename = "document_01.pdf"

    receipt_file = write_receipt(
        case_id=case_id,
        filename=filename,
        sha256=sha256,
        size=size,
        run_id=run_id,
        out_dir=out_dir,
    )

    assert receipt_file.is_file()
    assert receipt_file.name == "receipt.json"

    data = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert data["case_id"] == case_id
    assert data["filename"] == filename
    assert data["original_filename"] == filename
    assert data["sha256"] == sha256
    assert data["size"] == size
    assert data["run_id"] == run_id
    assert "received_at" in data


@pytest.mark.gate1
def test_write_receipt_case_id_validation(tmp_path: Path) -> None:
    """write_receipt rejects invalid case_ids (path traversal, illegal characters)."""
    out_dir = tmp_path / "case_output"
    run_id = make_run_id()

    # Path traversal attempt
    with pytest.raises(ValueError):
        write_receipt(
            case_id="../traversal_case",
            filename="file.txt",
            sha256="b" * 64,
            size=10,
            run_id=run_id,
            out_dir=out_dir,
        )

    # Colon not allowed
    with pytest.raises(ValueError):
        write_receipt(
            case_id="case:invalid",
            filename="file.txt",
            sha256="b" * 64,
            size=10,
            run_id=run_id,
            out_dir=out_dir,
        )


@pytest.mark.gate1
def test_immutable_store_original_and_write_denial(tmp_path: Path) -> None:
    """store_original stores file content-addressed, verifies hash, and enforces read-only access."""
    data_dir = tmp_path / "data"
    src_file = tmp_path / "original_source.txt"
    src_content = "Immutable original text content.\n"
    src_file.write_text(src_content, encoding="utf-8")
    src_sha = compute_sha256(src_file)

    initial_stat = src_file.stat()
    initial_mtime = initial_stat.st_mtime
    initial_bytes = src_file.read_bytes()

    stored_path = store_original(src_file, src_sha, data_dir)

    assert stored_path.is_file()
    assert stored_path.name == src_sha
    assert stored_path.parent == data_dir / "originals"
    assert stored_path.read_text(encoding="utf-8") == src_content

    # Hard Rule 6: Write denial test via PermissionError or os.access
    assert not os.access(stored_path, os.W_OK)
    with pytest.raises(PermissionError), stored_path.open("wb") as f:
        f.write(b"tamper attempt")

    # Reusing already stored original
    reused_path = store_original(src_file, src_sha, data_dir)
    assert reused_path == stored_path

    # Source file original bytes and mtime must remain unchanged
    after_stat = src_file.stat()
    assert src_file.read_bytes() == initial_bytes
    assert after_stat.st_mtime == initial_mtime

    # Cleanup permission for tmp_path deletion on Windows
    os.chmod(stored_path, stat.S_IWRITE)


@pytest.mark.gate1
def test_synthetic_guard_blocks_live_provider_without_manifest(tmp_path: Path) -> None:
    """Synthetic guard blocks live LLM providers when SHA-256 is missing from manifest."""
    manifest_path = tmp_path / "synthetic_manifest.json"
    known_sha = "1" * 64
    manifest_path.write_text(
        json.dumps({"files": [{"sha256": known_sha, "name": "sample.pdf"}]}),
        encoding="utf-8",
    )

    unknown_sha = "2" * 64

    # Non-mock provider (e.g. openai or gemini) with unknown hash must be rejected
    with pytest.raises(RejectedInputError) as exc_info:
        check_synthetic(unknown_sha, provider="openai", manifest_path=manifest_path)
    assert "refused" in str(exc_info.value).lower()
    assert unknown_sha in str(exc_info.value)

    # Non-mock provider with known hash succeeds
    check_synthetic(known_sha, provider="openai", manifest_path=manifest_path)

    # Mock provider always succeeds regardless of manifest presence
    check_synthetic(unknown_sha, provider="mock", manifest_path=manifest_path)


@pytest.mark.gate1
def test_synthetic_guard_missing_manifest_file(tmp_path: Path) -> None:
    """Missing manifest file must cause live providers to be refused."""
    non_existent = tmp_path / "missing_manifest.json"
    some_sha = "3" * 64

    # Live provider rejected when manifest is missing
    with pytest.raises(RejectedInputError) as exc_info:
        check_synthetic(some_sha, provider="gemini", manifest_path=non_existent)
    assert "not found" in str(exc_info.value).lower()

    # Mock provider succeeds even if manifest does not exist
    check_synthetic(some_sha, provider="mock", manifest_path=non_existent)


@pytest.mark.gate1
def test_synthetic_guard_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When ATLAS_SYNTHETIC_ONLY=false, synthetic guard allows unverified hashes."""
    monkeypatch.setenv("ATLAS_SYNTHETIC_ONLY", "false")
    non_existent = tmp_path / "non_existent.json"
    unverified_sha = "4" * 64

    # Should not raise
    check_synthetic(unverified_sha, provider="openai", manifest_path=non_existent)


@pytest.mark.gate1
def test_integrity_file_not_found_handling(tmp_path: Path) -> None:
    """Non-existent files raise FileNotFoundError in compute_sha256 and store_original."""
    missing = tmp_path / "not_found.bin"
    with pytest.raises(FileNotFoundError):
        compute_sha256(missing)
    with pytest.raises(FileNotFoundError):
        store_original(missing, "0" * 64, tmp_path / "data")
