"""Adversarial test suite: Path traversal prevention and filesystem boundary isolation.

Tests coverage:
1. Case ID with path traversal (../etc, ..\\..\\windows, /tmp, case/sub, etc.) -> validate_case_id raises ValueError.
2. Boundary and character limits for case_id.
3. System components enforcing validate_case_id (prompt builder, verifier, receipt writer, pipeline runner).
4. Uploaded filename with path traversal (../../evil.pdf, C:\\Windows\\cmd.exe) -> safe_filename / content-addressed.
5. Ingestion immutable store (store_original) content-addressed by SHA-256 hash.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from atlas.contracts.ids import safe_filename, validate_case_id
from atlas.ingest.integrity import write_receipt
from atlas.ingest.originals import store_original
from atlas.llm.build_prompt import build_prompt
from atlas.pipeline.jobs import list_runs
from atlas.provenance.verify import verify_model_output

pytestmark = pytest.mark.gate5


@pytest.mark.gate5
@pytest.mark.parametrize(
    "traversal_vector",
    [
        "../etc",
        "../../etc/passwd",
        r"..\..\windows",
        r"..\..\windows\system32\cmd.exe",
        "/tmp",
        "/var/log",
        "case/sub",
        "case\\sub",
        "case/../evil",
        "case\\..\\evil",
        "~/.ssh/id_rsa",
        "case;rm -rf /",
        "case\x00evil",
        "case|pipe",
        "case>output",
        "../",
        "..",
        ".",
    ],
)
def test_validate_case_id_path_traversal_vectors_rejected(traversal_vector: str) -> None:
    """All path traversal and injection strings in case_id must raise ValueError."""
    with pytest.raises(ValueError, match="must match regex"):
        validate_case_id(traversal_vector)


@pytest.mark.gate5
def test_validate_case_id_length_and_type_boundaries() -> None:
    """case_id must be non-empty string between 1 and 64 characters matching regex."""
    # Empty string
    with pytest.raises(ValueError):
        validate_case_id("")

    # 65 characters (exceeds max length of 64)
    with pytest.raises(ValueError):
        validate_case_id("A" * 65)

    # Non-string input
    with pytest.raises(ValueError):
        validate_case_id(12345)  # type: ignore[arg-type]

    # Valid boundaries
    assert validate_case_id("A") == "A"
    assert validate_case_id("A" * 64) == "A" * 64
    assert validate_case_id("CASE-2026_alpha-01") == "CASE-2026_alpha-01"


@pytest.mark.gate5
def test_pipeline_components_enforce_case_id_validation(tmp_path: Path) -> None:
    """Core components must invoke validate_case_id to prevent directory escape."""
    bad_case = "../escape_dir"

    # 1. build_prompt
    with pytest.raises(ValueError):
        build_prompt([], case_id=bad_case, doc_id="DOC-1")

    # 2. verify_model_output
    with pytest.raises(ValueError):
        verify_model_output({}, chunk_units=[], case_id=bad_case, doc_id="DOC-1")

    # 3. write_receipt
    with pytest.raises(ValueError):
        write_receipt(
            case_id=bad_case,
            filename="test.pdf",
            sha256="0" * 64,
            size=100,
            run_id="RUN-1",
            out_dir=tmp_path,
        )

    # 4. list_runs
    with pytest.raises(ValueError):
        list_runs(case_id=bad_case, output_dir=tmp_path)


@pytest.mark.gate5
@pytest.mark.parametrize(
    "raw_filename,expected_sanitized_substring",
    [
        ("../../evil.pdf", "evil.pdf"),
        (r"C:\Windows\cmd.exe", "cmd.exe"),
        ("/etc/shadow.pdf", "shadow.pdf"),
        (r"..\..\..\..\boot.ini", "boot.ini"),
    ],
)
def test_safe_filename_sanitizes_path_traversal(raw_filename: str, expected_sanitized_substring: str) -> None:
    """safe_filename strips path delimiters (: / \\) to neutralize directory traversal."""
    sanitized = safe_filename(raw_filename)
    assert "/" not in sanitized
    assert "\\" not in sanitized
    assert ":" not in sanitized
    assert expected_sanitized_substring in sanitized


@pytest.mark.gate5
def test_store_original_content_addressed_ignores_filename_path_traversal(tmp_path: Path) -> None:
    """Original files are stored strictly by content-hash (SHA-256), completely ignoring source filenames."""
    source_file = tmp_path / "normal_temp.pdf"
    content = b"%PDF-1.4 test original content for hash storage"
    source_file.write_bytes(content)
    file_sha256 = hashlib.sha256(content).hexdigest().lower()

    data_dir = tmp_path / "data"
    stored_path = store_original(source_file, file_sha256, data_dir)

    # Stored file name is strictly the 64-hex sha256
    assert stored_path.name == file_sha256
    assert stored_path.parent == data_dir / "originals"
    assert stored_path.is_file()
    assert stored_path.read_bytes() == content
