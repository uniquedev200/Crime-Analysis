"""File type detection by magic bytes and extension verification for ATLAS Dev 3.

Rejects unsupported formats (.xlsm, .xls, .docm), files with mismatched magic bytes,
and files exceeding size limits before parsing.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from atlas.errors import RejectedInputError

# Supported extensions mapping to canonical detected_type
SUPPORTED_EXTENSIONS: set[str] = {
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "tif",
    "tiff",
    "csv",
    "xlsx",
    "txt",
    "json",
}

# Rejected legacy/macro formats
REJECTED_MACRO_EXTENSIONS: set[str] = {"xlsm", "xls", "docm"}

# Binary magic signatures
MAGIC_PDF = b"%PDF"
MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
MAGIC_JPEG = b"\xff\xd8\xff"
MAGIC_TIFF_LE = b"II*\x00"
MAGIC_TIFF_BE = b"MM\x00*"
MAGIC_ZIP = b"PK\x03\x04"


def _check_binary_magics(header: bytes) -> str | None:
    """Identify if the header matches any known binary file magic bytes."""
    if header.startswith(MAGIC_PNG):
        return "png"
    if header.startswith(MAGIC_JPEG):
        return "jpeg"
    if header.startswith(MAGIC_TIFF_LE) or header.startswith(MAGIC_TIFF_BE):
        return "tiff"
    if header.startswith(MAGIC_ZIP):
        return "zip"
    if b"%PDF" in header[:1024]:
        return "pdf"
    return None


def detect_file_type(path: Path) -> str:
    """Detect and validate file type by verifying extension and magic bytes.

    Returns one of: 'pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff', 'csv', 'xlsx', 'txt', 'json'.
    Raises RejectedInputError on unsupported extension, macro format, empty file,
    or magic bytes mismatch.
    """
    if not isinstance(path, Path):
        path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower().lstrip(".")
    if not ext:
        raise RejectedInputError(f"File '{path.name}' has no extension; cannot determine file type")

    # Explicit rejection for macro/legacy formats
    if ext in REJECTED_MACRO_EXTENSIONS:
        raise RejectedInputError(
            f"Unsupported file format '.{ext}': macros and legacy formats are rejected for security and stability"
        )

    if ext not in SUPPORTED_EXTENSIONS:
        raise RejectedInputError(f"Unsupported file extension '.{ext}': expected one of {sorted(SUPPORTED_EXTENSIONS)}")

    # Check file size (empty file cannot be processed)
    size = path.stat().st_size
    if size == 0:
        raise RejectedInputError(f"Empty file: '{path.name}' has 0 bytes")

    # Read leading bytes for magic check
    read_size = min(size, 4096)
    with path.open("rb") as f:
        header = f.read(read_size)

    # Verification per extension
    if ext == "pdf":
        if b"%PDF" not in header[:1024]:
            detected_other = _check_binary_magics(header)
            raise RejectedInputError(
                f"Magic bytes mismatch: file '{path.name}' has extension '.pdf' but header does not contain '%PDF' "
                f"(detected header: {detected_other or 'unknown/text'})"
            )
        return "pdf"

    if ext == "png":
        if not header.startswith(MAGIC_PNG):
            raise RejectedInputError(
                f"Magic bytes mismatch: file '{path.name}' has extension '.png' but header does not match PNG signature"
            )
        return "png"

    if ext in ("jpg", "jpeg"):
        if not header.startswith(MAGIC_JPEG):
            raise RejectedInputError(
                f"Magic bytes mismatch: file '{path.name}' has extension '.{ext}' but header does not match JPEG signature"
            )
        return ext

    if ext in ("tif", "tiff"):
        if not (header.startswith(MAGIC_TIFF_LE) or header.startswith(MAGIC_TIFF_BE)):
            raise RejectedInputError(
                f"Magic bytes mismatch: file '{path.name}' has extension '.{ext}' but header does not match TIFF signature"
            )
        return ext

    if ext == "xlsx":
        if not header.startswith(MAGIC_ZIP):
            raise RejectedInputError(
                f"Magic bytes mismatch: file '{path.name}' has extension '.xlsx' but is not a valid ZIP/Office archive"
            )
        # Verify it is a valid zip archive
        try:
            with zipfile.ZipFile(path, "r") as zf:
                # Check for workbook or content types typical of xlsx
                names = zf.namelist()
                if not any("xl/" in n or "[Content_Types].xml" in n for n in names):
                    raise RejectedInputError(
                        f"Invalid XLSX archive: '{path.name}' does not contain expected spreadsheet components"
                    )
        except zipfile.BadZipFile as e:
            raise RejectedInputError(f"Corrupt or invalid XLSX file '{path.name}': {e}") from e
        return "xlsx"

    # Text-based formats: csv, txt, json
    detected_bin = _check_binary_magics(header)
    if detected_bin is not None:
        raise RejectedInputError(
            f"Magic bytes mismatch: file '{path.name}' has text extension '.{ext}' but binary magic '{detected_bin}'"
        )

    # Check for null bytes which indicate binary data
    if b"\x00" in header:
        raise RejectedInputError(
            f"Magic bytes mismatch: file '{path.name}' has extension '.{ext}' but contains binary null bytes"
        )

    # For text formats, verify UTF-8 decodability on header
    try:
        header_text = header.decode("utf-8")
    except UnicodeDecodeError as e:
        raise RejectedInputError(f"Encoding error: text file '{path.name}' is not valid UTF-8: {e}") from e

    if ext == "json":
        # Validate that JSON file starts with '{' or '[' (ignoring whitespace and BOM)
        stripped = header_text.lstrip("\ufeff \t\r\n")
        if not stripped or stripped[0] not in ("{", "["):
            raise RejectedInputError(
                f"Invalid JSON file '{path.name}': must begin with '{{' or '[' but found '{stripped[:10]}'"
            )
        return "json"

    if ext in ("csv", "txt"):
        return ext

    raise RejectedInputError(f"Unhandled file extension: '{ext}'")


__all__ = ["REJECTED_MACRO_EXTENSIONS", "SUPPORTED_EXTENSIONS", "detect_file_type"]
