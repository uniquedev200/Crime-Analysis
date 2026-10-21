#!/usr/bin/env python3
"""Gate verification script for ATLAS Dev 3 pipeline.

Usage:
    python scripts/verify.py --gate <0..5>

Executes linter, formatter, type checker, and gate test suite.
Writes evidence report to outputs/gates/gate_<N>.json.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def run_cmd(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    desc: str,
) -> subprocess.CompletedProcess[str]:
    """Execute subprocess with list arguments (no shell=True) and UTF-8 encoding."""
    print(f"\n[RUN] {desc}...")
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=False,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        print(f"[ERROR] {desc} failed with exit code {proc.returncode}")
    else:
        print(f"[OK] {desc} succeeded")
    return proc


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS Dev 3 Gate Verification")
    parser.add_argument(
        "--gate",
        type=int,
        required=True,
        choices=range(0, 6),
        help="Gate number to verify (0 to 5)",
    )
    parser.add_argument(
        "--cumulative",
        action="store_true",
        help="Run cumulative verification across all gates 0 through N",
    )
    args = parser.parse_args()
    gate_num: int = args.gate
    is_cumulative: bool = args.cumulative

    worktree = Path(__file__).resolve().parent.parent
    src_dir = worktree / "src"

    # Setup environment
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_dir)
    env["PYTHONUTF8"] = "1"

    print("=" * 60)
    print(f"ATLAS Gate {gate_num} Verification")
    print(f"Worktree: {worktree}")
    print(f"Python:   {sys.executable}")
    print("=" * 60)

    # Step 1: ruff check src/
    p_ruff_check = run_cmd(
        [sys.executable, "-m", "ruff", "check", "src/"],
        cwd=worktree,
        env=env,
        desc="Step 1: ruff check src/",
    )
    if p_ruff_check.returncode != 0:
        sys.exit(1)

    # Step 2: ruff format --check src/
    p_ruff_fmt = run_cmd(
        [sys.executable, "-m", "ruff", "format", "--check", "src/"],
        cwd=worktree,
        env=env,
        desc="Step 2: ruff format --check src/",
    )
    if p_ruff_fmt.returncode != 0:
        sys.exit(1)

    # Step 3: mypy src/atlas --ignore-missing-imports
    p_mypy = run_cmd(
        [sys.executable, "-m", "mypy", "src/atlas", "--ignore-missing-imports"],
        cwd=worktree,
        env=env,
        desc="Step 3: mypy src/atlas --ignore-missing-imports",
    )
    if p_mypy.returncode != 0:
        sys.exit(1)

    # Step 5: Assert atlas.__file__ is inside the current worktree
    print("\n[RUN] Step 5: Assert atlas.__file__ inside current worktree...")
    check_code = (
        "import atlas, pathlib, sys\n"
        "atlas_path = pathlib.Path(atlas.__file__).resolve()\n"
        "worktree = pathlib.Path(sys.argv[1]).resolve()\n"
        "assert worktree in atlas_path.parents, f'{atlas_path} is not inside worktree {worktree}'\n"
        "print(f'Verified atlas location: {atlas_path}')\n"
    )
    p_assert_atlas = subprocess.run(
        [sys.executable, "-c", check_code, str(worktree)],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if p_assert_atlas.returncode != 0:
        print(f"[ERROR] atlas.__file__ assertion failed:\n{p_assert_atlas.stderr}")
        sys.exit(1)
    print(f"[OK] {p_assert_atlas.stdout.strip()}")

    # Step 4: Run pytest -m 'gateN and not optional'
    junit_dir = worktree / "outputs" / "gates"
    junit_dir.mkdir(parents=True, exist_ok=True)
    temp_junit_xml = junit_dir / f".temp_gate_{gate_num}_junit.xml"

    if is_cumulative:
        gate_filter = "(" + " or ".join(f"gate{i}" for i in range(gate_num + 1)) + ") and not optional"
    else:
        gate_filter = f"gate{gate_num} and not optional"

    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        gate_filter,
        f"--junitxml={temp_junit_xml!s}",
    ]
    p_pytest = run_cmd(
        pytest_cmd,
        cwd=worktree,
        env=env,
        desc=f"Step 4: pytest -m '{gate_filter}'",
    )

    # Step 6: Collect test results
    passed = 0
    failed = 0
    skipped = 0
    errors = 0

    if temp_junit_xml.exists():
        try:
            tree = ET.parse(temp_junit_xml)
            root = tree.getroot()
            testcases = root.findall(".//testcase")
            for tc in testcases:
                if tc.find("failure") is not None:
                    failed += 1
                elif tc.find("error") is not None:
                    errors += 1
                elif tc.find("skipped") is not None:
                    skipped += 1
                else:
                    passed += 1
        finally:
            if temp_junit_xml.exists():
                temp_junit_xml.unlink()

    if p_pytest.returncode != 0 and failed == 0 and errors == 0:
        errors = 1

    # Step 7: List optional tests (deselected) under not_run_optional
    opt_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-m",
        f"gate{gate_num} and optional",
    ]
    opt_proc = subprocess.run(
        opt_cmd,
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    not_run_optional: list[str] = []
    if opt_proc.returncode == 0:
        for line in opt_proc.stdout.splitlines():
            line = line.strip()
            if line and "::" in line and not line.startswith("no tests"):
                not_run_optional.append(line)

    # Step 8: Write outputs/gates/gate_N.json
    p_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    commit_hash = p_hash.stdout.strip() if p_hash.returncode == 0 else ""

    p_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    clean_tree = (len(p_status.stdout.strip()) == 0) if p_status.returncode == 0 else False

    timestamp = datetime.now(UTC).isoformat()

    gate_payload = {
        "commit_hash": commit_hash,
        "clean_tree": clean_tree,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "not_run_optional": not_run_optional,
        "timestamp": timestamp,
    }

    gate_file = junit_dir / f"gate_{gate_num}.json"
    with open(gate_file, "w", encoding="utf-8") as f:
        json.dump(gate_payload, f, indent=2, ensure_ascii=False)
    print(f"\n[EVIDENCE] Wrote gate report to {gate_file}")

    print("\n" + "=" * 60)
    print(f"Gate {gate_num} Summary:")
    print(f"  Passed:           {passed}")
    print(f"  Failed:           {failed}")
    print(f"  Skipped:          {skipped}")
    print(f"  Errors:           {errors}")
    print(f"  Not Run Optional: {len(not_run_optional)}")
    print(f"  Clean Tree:       {clean_tree}")
    print(f"  Commit Hash:      {commit_hash}")
    print("=" * 60)

    # Step 9: If any skipped > 0 or failed > 0: exit 1
    if skipped > 0 or failed > 0 or errors > 0:
        print(f"\n[FAIL] Gate {gate_num} failed verification (skipped={skipped}, failed={failed}, errors={errors})")
        sys.exit(1)

    print(f"\n[PASS] Gate {gate_num} verified successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
