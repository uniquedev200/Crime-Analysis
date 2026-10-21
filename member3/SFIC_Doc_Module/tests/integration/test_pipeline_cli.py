"""Integration tests for ATLAS Dev 3 CLI commands.

Test requirements (PLAN.md Section 8 H3 task card & Gate 3):
- CLI python -m atlas run creates output folder, returns exit 0
- CLI python -m atlas status prints run state
- CLI python -m atlas results outputs valid JSON
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atlas.cli import cli_main


@pytest.mark.gate3
def test_cli_run_creates_output_and_exits_zero(tmp_path: Path) -> None:
    """CLI run creates output folder and returns exit 0."""
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text("Case report facts line.", encoding="utf-8")
    out_dir = tmp_path / "cli_outputs"

    exit_code = cli_main(
        [
            "run",
            "--case",
            "CASE-CLI-001",
            "--files",
            str(txt_file),
            "--provider",
            "mock",
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    case_dir = out_dir / "CASE-CLI-001"
    assert case_dir.is_dir()
    runs = list(case_dir.glob("RUN-*"))
    assert len(runs) == 1
    assert (runs[0] / "result.json").is_file()


@pytest.mark.gate3
def test_cli_status_prints_state(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI status displays correct run state for a case."""
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text("Case statement content.", encoding="utf-8")
    out_dir = tmp_path / "cli_outputs"

    # First run the case
    cli_main(
        [
            "run",
            "--case",
            "CASE-CLI-STATUS",
            "--files",
            str(txt_file),
            "--provider",
            "mock",
            "--out",
            str(out_dir),
        ]
    )

    capsys.readouterr()  # Clear stdout

    # Now query status
    status_code = cli_main(
        [
            "status",
            "--case",
            "CASE-CLI-STATUS",
            "--out",
            str(out_dir),
        ]
    )

    assert status_code == 0
    captured = capsys.readouterr()
    assert "CASE-CLI-STATUS" in captured.out
    assert "RUN-" in captured.out
    assert "Status:" in captured.out


@pytest.mark.gate3
def test_cli_results_outputs_valid_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI results outputs valid JSON matching CaseResult schema."""
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text("Evidence note content for json check.", encoding="utf-8")
    out_dir = tmp_path / "cli_outputs"

    # First run the case
    cli_main(
        [
            "run",
            "--case",
            "CASE-CLI-RESULTS",
            "--files",
            str(txt_file),
            "--provider",
            "mock",
            "--out",
            str(out_dir),
        ]
    )

    capsys.readouterr()  # Clear stdout

    # Query results
    res_code = cli_main(
        [
            "results",
            "--case",
            "CASE-CLI-RESULTS",
            "--out",
            str(out_dir),
        ]
    )

    assert res_code == 0
    captured = capsys.readouterr()
    # Output must parse as valid JSON
    data = json.loads(captured.out)
    assert isinstance(data, dict)
    assert data.get("schema_version") == "1.0.0"
    assert data.get("case_id") == "CASE-CLI-RESULTS"
    assert "state" in data
    assert "documents" in data


@pytest.mark.gate3
def test_cli_subprocess_invocation(tmp_path: Path) -> None:
    """Invoke CLI as python -m atlas in a separate process."""
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text("Subprocess invocation test evidence.", encoding="utf-8")
    out_dir = tmp_path / "subp_outputs"

    worktree = Path(__file__).resolve().parent.parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(worktree / "src")
    env["PYTHONUTF8"] = "1"

    cmd = [
        sys.executable,
        "-m",
        "atlas",
        "run",
        "--case",
        "CASE-SUBP-001",
        "--files",
        str(txt_file),
        "--provider",
        "mock",
        "--out",
        str(out_dir),
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert proc.returncode == 0
    assert "Run ID:" in proc.stdout
    assert (out_dir / "CASE-SUBP-001").is_dir()


@pytest.mark.gate3
def test_cli_inspect_displays_entities_and_connections(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI inspect formats and displays entities and connections in human-readable form."""
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text("Case inspection facts line.", encoding="utf-8")
    out_dir = tmp_path / "cli_outputs"

    # First run the case
    cli_main(
        [
            "run",
            "--case",
            "CASE-CLI-INSPECT",
            "--files",
            str(txt_file),
            "--provider",
            "mock",
            "--out",
            str(out_dir),
        ]
    )

    capsys.readouterr()  # Clear stdout

    # Inspect the case
    inspect_code = cli_main(
        [
            "inspect",
            "--case",
            "CASE-CLI-INSPECT",
            "--out",
            str(out_dir),
        ]
    )

    assert inspect_code == 0
    captured = capsys.readouterr()
    assert "ATLAS EXTRACTION INSPECTOR - CASE: CASE-CLI-INSPECT" in captured.out
    assert "[1] DOCUMENTS PROCESSED" in captured.out
    assert "[2] EXTRACTED ENTITIES" in captured.out
    assert "[3] GRAPH CONNECTIONS & RELATIONSHIPS" in captured.out
