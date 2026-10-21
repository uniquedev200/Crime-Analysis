from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from atlas.errors import OcrLanguageUnavailable

logger = logging.getLogger(__name__)


def get_available_languages(tesseract_cmd: str) -> set[str]:
    """Retrieve installed language codes from Tesseract binary.

    Args:
        tesseract_cmd: Path to the Tesseract executable.

    Returns:
        Set of installed language codes (e.g. {'eng', 'osd', 'hin'}).
    """
    cmd_path = Path(tesseract_cmd)
    if not cmd_path.is_file() and not shutil.which(tesseract_cmd):
        logger.warning("Tesseract binary not found at '%s'", tesseract_cmd)
        return set()

    env = os.environ.copy()
    try:
        proc = subprocess.run(
            [tesseract_cmd, "--list-langs"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Failed executing tesseract --list-langs: %s", exc)
        return set()

    if proc.returncode != 0:
        logger.warning(
            "tesseract --list-langs exited with code %d: %s",
            proc.returncode,
            proc.stderr.strip() if proc.stderr else "",
        )
        return set()

    available: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of") or line.endswith(":"):
            continue
        available.add(line)
    return available


def check_languages(langs: list[str], tesseract_cmd: str) -> None:
    """Validate that all requested OCR language packs are available.

    Args:
        langs: List of language codes, e.g. ['eng'] or ['eng', 'hin'] or ['eng+hin'].
        tesseract_cmd: Path to the Tesseract executable.

    Raises:
        OcrLanguageUnavailable: If any requested language pack is missing.
    """
    if not langs:
        return

    # Normalize language list (split compounds like 'eng+hin')
    requested: list[str] = []
    for lang in langs:
        for part in lang.split("+"):
            part = part.strip()
            if part and part not in requested:
                requested.append(part)

    available = get_available_languages(tesseract_cmd)

    for lang in requested:
        if lang not in available:
            logger.error(
                "OCR language pack '%s' is unavailable. Installed languages: %s. "
                "Download '%s.traineddata' from https://github.com/tesseract-ocr/tessdata "
                "and place it in your TESSDATA_PREFIX directory.",
                lang,
                sorted(available),
                lang,
            )
            raise OcrLanguageUnavailable(lang)


__all__ = ["check_languages", "get_available_languages"]
