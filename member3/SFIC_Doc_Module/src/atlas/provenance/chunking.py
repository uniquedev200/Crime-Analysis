"""Unit chunking and pagination for LLM extraction prompts.

Implements Section 5.6 chunking rules:
- Groups units by page/document up to max_chars (LLM_CHUNK_CHARS).
- Splits oversized single pages/units on line boundaries with configurable line overlap.
- Guarantees every input unit appears in at least one chunk.
"""

from __future__ import annotations

from atlas.extract.units import Unit


def split_large_unit(
    unit: Unit,
    max_chars: int = 4000,
    overlap_lines: int = 3,
) -> list[Unit]:
    """Split an oversized Unit into smaller Units with overlapping line boundaries.

    Args:
        unit: Source Unit exceeding max_chars.
        max_chars: Maximum character capacity per chunk.
        overlap_lines: Number of overlapping lines between consecutive sub-units.

    Returns:
        List of sub-units with preserved unit_id, page, doc_id, and updated line ranges.
    """
    lines = unit.text.splitlines()
    if not lines:
        return [unit]

    base_line = unit.line_start if unit.line_start is not None else 1

    # If single line without newlines exceeds max_chars, slice characters
    if len(lines) == 1:
        text = lines[0]
        step = max(1, max_chars - 50)
        sub_units: list[Unit] = []
        for start in range(0, len(text), step):
            sub_text = text[start : start + max_chars]
            sub_units.append(
                Unit(
                    unit_id=unit.unit_id,
                    text=sub_text,
                    page=unit.page,
                    line_start=base_line,
                    line_end=base_line,
                    method=unit.method,
                    doc_id=unit.doc_id,
                )
            )
        return sub_units

    sub_units = []
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        curr_chars = len(lines[i])
        j = i + 1
        while j < total_lines:
            add_len = 1 + len(lines[j])  # 1 for newline separator
            if curr_chars + add_len > max_chars:
                break
            curr_chars += add_len
            j += 1

        sub_text = "\n".join(lines[i:j])
        sub_line_start = base_line + i
        sub_line_end = base_line + (j - 1)

        sub_units.append(
            Unit(
                unit_id=unit.unit_id,
                text=sub_text,
                page=unit.page,
                line_start=sub_line_start,
                line_end=sub_line_end,
                method=unit.method,
                doc_id=unit.doc_id,
            )
        )

        if j >= total_lines:
            break

        # Step back by overlap_lines, ensuring forward progress
        i = max(i + 1, j - overlap_lines)

    return sub_units


def chunk_units(
    units: list[Unit],
    max_chars: int = 4000,
    overlap_lines: int = 3,
) -> list[list[Unit]]:
    """Group units into prompt chunks respecting max_chars and line overlap.

    Args:
        units: Sequence of extracted textual units.
        max_chars: Maximum characters per chunk (default 4000).
        overlap_lines: Number of overlapping lines when splitting huge pages (default 3).

    Returns:
        List of chunks, where each chunk is a list of Unit objects.
    """
    if not units:
        return []

    chunks: list[list[Unit]] = []
    current_chunk: list[Unit] = []
    current_chars = 0

    for u in units:
        u_len = len(u.text)
        if u_len > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_chars = 0
            sub_units = split_large_unit(u, max_chars=max_chars, overlap_lines=overlap_lines)
            for su in sub_units:
                chunks.append([su])
        else:
            if current_chunk and (current_chars + u_len > max_chars):
                chunks.append(current_chunk)
                current_chunk = [u]
                current_chars = u_len
            else:
                current_chunk.append(u)
                current_chars += u_len

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


__all__ = ["chunk_units", "split_large_unit"]
