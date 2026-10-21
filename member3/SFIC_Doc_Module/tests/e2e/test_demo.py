"""End-to-end test for ATLAS Dev 3 Master Demonstration script.

All tests marked with @pytest.mark.gate4.
Executes scripts/demo.py with --scripted-review and verifies that
the emitted summary matches expected_demo_summary.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.gate4
def test_demo_scripted_review_reproduces_golden_summary(tmp_path: Path) -> None:
    """Run demo.py with --scripted-review and verify summary matches expected_demo_summary.json."""
    worktree = Path(__file__).resolve().parent.parent.parent
    demo_script = worktree / "scripts" / "demo.py"
    expected_file = Path(__file__).resolve().parent / "expected_demo_summary.json"

    assert demo_script.is_file(), f"Missing demo script at {demo_script}"
    assert expected_file.is_file(), f"Missing golden expected summary at {expected_file}"

    out_dir = tmp_path / "demo_outputs"
    data_dir = worktree / "data" / "synth"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(worktree / "src") + os.pathsep + str(worktree)
    env["PYTHONUTF8"] = "1"

    cmd = [
        sys.executable,
        str(demo_script),
        "--scripted-review",
        "--seed",
        "42",
        "--data-dir",
        str(data_dir),
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

    assert proc.returncode == 0, f"demo.py failed with exit code {proc.returncode}:\n{proc.stderr}"

    # Verify mock honesty banner is displayed
    assert "SCRIPTED MOCK PROVIDER: not live extraction" in proc.stdout

    # Verify summary JSON was created
    summary_file = out_dir / "demo_summary.json"
    assert summary_file.is_file(), f"Missing {summary_file}"

    # Read both actual and expected
    actual_data = json.loads(summary_file.read_text(encoding="utf-8"))
    expected_data = json.loads(expected_file.read_text(encoding="utf-8"))

    # Assert essential keys match
    assert actual_data["pipeline_version"] == expected_data["pipeline_version"]
    assert actual_data["provider"] == expected_data["provider"]
    assert actual_data["seed"] == expected_data["seed"]

    # Case A metrics
    assert actual_data["case_a"]["case_id"] == expected_data["case_a"]["case_id"]
    assert actual_data["case_a"]["documents_count"] == expected_data["case_a"]["documents_count"]
    assert actual_data["case_a"]["mentions_count"] == expected_data["case_a"]["mentions_count"]
    assert actual_data["case_a"]["events_count"] == expected_data["case_a"]["events_count"]
    assert actual_data["case_a"]["relationships_count"] == expected_data["case_a"]["relationships_count"]
    assert actual_data["case_a"]["review_items_count"] == expected_data["case_a"]["review_items_count"]
    assert actual_data["case_a"]["state"] == expected_data["case_a"]["state"]
    assert actual_data["case_a"]["ocr_phone_trust"] == expected_data["case_a"]["ocr_phone_trust"]

    # Case B metrics
    assert actual_data["case_b"]["case_id"] == expected_data["case_b"]["case_id"]
    assert actual_data["case_b"]["documents_count"] == expected_data["case_b"]["documents_count"]
    assert actual_data["case_b"]["mentions_count"] == expected_data["case_b"]["mentions_count"]
    assert actual_data["case_b"]["events_count"] == expected_data["case_b"]["events_count"]
    assert actual_data["case_b"]["relationships_count"] == expected_data["case_b"]["relationships_count"]
    assert actual_data["case_b"]["review_items_count"] == expected_data["case_b"]["review_items_count"]
    assert actual_data["case_b"]["state"] == expected_data["case_b"]["state"]

    # Cross-case resolution
    assert (
        actual_data["cross_case_resolution"]["vicky_status"] == expected_data["cross_case_resolution"]["vicky_status"]
    )
    assert (
        actual_data["cross_case_resolution"]["hard_negative_status"]
        == expected_data["cross_case_resolution"]["hard_negative_status"]
    )
    assert actual_data["cross_case_resolution"]["rank_note"] == expected_data["cross_case_resolution"]["rank_note"]

    # Review workflow
    assert actual_data["review_workflow"]["confirm_identifier_success"] is True
    assert actual_data["review_workflow"]["approve_match_success"] is True
    assert actual_data["review_workflow"]["audit_chain_verified_after_merge"] is True
    assert actual_data["review_workflow"]["split_success"] is True
    assert actual_data["review_workflow"]["audit_chain_verified_after_split"] is True
    assert actual_data["review_workflow"]["total_audit_actions"] == 3

    # Audit trail
    assert actual_data["audit_trail"]["chain_verified"] is True
    assert actual_data["audit_trail"]["genesis_hash"] == expected_data["audit_trail"]["genesis_hash"]

    # Byte-for-byte matching of canonically serialized summary
    actual_text = summary_file.read_text(encoding="utf-8").strip()
    expected_text = expected_file.read_text(encoding="utf-8").strip()
    assert actual_text == expected_text

    # Verify HTML reports were generated
    assert (out_dir / "CASE-A-001" / "report.html").is_file()
    assert (out_dir / "CASE-B-002" / "report.html").is_file()
