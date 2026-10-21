#!/usr/bin/env python3
"""Environment diagnostic check for ATLAS Dev 3 pipeline."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def check_python() -> bool:
    """Verify Python version is 3.11 or 3.12."""
    version = sys.version.split()[0]
    major, minor = sys.version_info.major, sys.version_info.minor

    if (major, minor) in ((3, 11), (3, 12)):
        print(f"[OK] Python version: {version} (3.11/3.12 compatible)")
        return True
    else:
        print(
            f"[WARN] Python version: {version} (WARNING: ATLAS strictly requires Python 3.11 or 3.12; Python 3.14 is unsupported)"
        )
        return False


def check_tesseract() -> bool:
    """Check Tesseract binary, version, and installed languages."""
    tesseract_cmd = os.environ.get("TESSERACT_CMD")
    if not tesseract_cmd:
        dotenv_path = Path(".env")
        if dotenv_path.is_file():
            for line in dotenv_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("TESSERACT_CMD="):
                    tesseract_cmd = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    candidates: list[str] = []
    if tesseract_cmd:
        candidates.append(tesseract_cmd)
    candidates.append(str(Path.home() / "tools" / "tesseract" / "tesseract.exe"))

    # Windows standard paths
    candidates.extend(
        [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
    )

    which_path = shutil.which("tesseract")
    if which_path:
        candidates.append(which_path)

    found_binary: str | None = None
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            found_binary = candidate
            break

    if not found_binary:
        print("[WARN] Tesseract OCR: Not found.")
        print("       Windows Installation Guidance:")
        print("       - Run: winget install UB-Mannheim.TesseractOCR")
        print("       - Or download from: https://github.com/UB-Mannheim/tesseract/wiki")
        print(r"       - Default install path: C:\Program Files\Tesseract-OCR\tesseract.exe")
        print(r"       - Set environment variable: $env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'")
        return False

    print(f"[OK] Tesseract binary: {found_binary}")

    # Version check
    try:
        ver_proc = subprocess.run(
            [found_binary, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        version_line = ver_proc.stdout.splitlines()[0] if ver_proc.stdout else "unknown"
        print(f"     Version: {version_line.strip()}")
    except Exception as exc:
        print(f"     [WARN] Could not determine Tesseract version: {exc}")

    # Languages check
    try:
        lang_proc = subprocess.run(
            [found_binary, "--list-langs"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        langs = [
            line.strip() for line in lang_proc.stdout.splitlines() if line.strip() and not line.startswith("List of")
        ]
        print(f"     Languages ({len(langs)}): {', '.join(langs)}")
    except Exception as exc:
        print(f"     [WARN] Could not retrieve language packs: {exc}")

    return True


def check_tool(tool_name: str, module_name: str) -> bool:
    """Check availability of a developer CLI tool."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", module_name, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        if proc.returncode == 0:
            version_str = (proc.stdout or proc.stderr).strip().splitlines()[0]
            print(f"[OK] {tool_name}: {version_str}")
            return True
        else:
            print(f"[WARN] {tool_name}: returned error code {proc.returncode}")
            return False
    except Exception as exc:
        print(f"[WARN] {tool_name} not available: {exc}")
        return False


def main() -> None:
    print("=" * 60)
    print("ATLAS Dev 3 Environment Diagnostic Check")
    print("=" * 60)

    check_python()
    check_tesseract()

    print("-" * 60)
    print("Developer Tools:")
    check_tool("Ruff", "ruff")
    check_tool("Mypy", "mypy")
    check_tool("Pytest", "pytest")

    print("=" * 60)


if __name__ == "__main__":
    main()
