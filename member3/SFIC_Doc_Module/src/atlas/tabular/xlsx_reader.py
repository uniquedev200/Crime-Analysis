"""Deterministic XLSX reader for tabular evidence.

Implements PLAN.md section 5.7:
- Openpyxl loaded twice for files <= max_full_load_mb (data_only=False for formulas, data_only=True for cached).
- Above threshold: read_only=True with warning 'merged_cells_not_inspected'.
- Hidden sheets included with their state (visible, hidden, veryHidden).
- Merged cells: value belongs to top-left cell only; other merged cells get null with in_merged_range=True.
- Formula without cached value emits 'formula_missing_cache' warning; never evaluates formulas.
- Identifier-like cells read from number-format text, preserving leading zeros, never emitting floats.
- Malformed workbooks raise RejectedInputError.
- Returns {sheets: [{name, state, rows, merged_ranges, formulas}], warnings}.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

from atlas.contracts.enums import SheetState
from atlas.errors import RejectedInputError


def _format_cell_value(val: Any, num_format: str | None) -> Any:
    """Format cell value: preserve strings, format integer-like floats, apply leading zeros."""
    if val is None:
        return None

    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val

    if isinstance(val, str):
        return val

    # Clean format string
    fmt = num_format.strip() if num_format else ""

    # Check for leading zero format like '0000000000' or '000000000000000' (15 zeros)
    zero_match = re.match(r"^0+$", fmt)
    required_width = len(fmt) if zero_match else 0

    if isinstance(val, int):
        if required_width > 0:
            return f"{val:0{required_width}d}"
        return str(val)

    if isinstance(val, float):
        if val.is_integer() or abs(val - round(val)) < 1e-6:
            int_val = round(val)
            if required_width > 0:
                return f"{int_val:0{required_width}d}"
            return str(int_val)
        return val

    return val


def read_xlsx(path: Path | str, max_full_load_mb: int = 15) -> dict[str, Any]:
    """Read an XLSX workbook deterministically into sheets and warnings."""
    file_path = Path(path)
    warnings: list[str] = []

    if not file_path.exists():
        raise RejectedInputError(f"XLSX file not found: {file_path}")

    size_bytes = file_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)

    if size_mb > max_full_load_mb:
        warnings.append("merged_cells_not_inspected: file size exceeds full load limit")
        return _read_xlsx_readonly(file_path, warnings)

    wb_formula = None
    wb_data = None
    try:
        try:
            wb_formula = openpyxl.load_workbook(file_path, data_only=False)
            wb_data = openpyxl.load_workbook(file_path, data_only=True)
        except Exception as e:
            raise RejectedInputError(f"Malformed workbook: {e}") from e

        sheets: list[dict[str, Any]] = []

        for sheet_name in wb_formula.sheetnames:
            ws_formula = wb_formula[sheet_name]
            ws_data = wb_data[sheet_name]

            raw_state = ws_formula.sheet_state or "visible"
            # Normalize state to SheetState
            state = SheetState.VISIBLE.value
            if raw_state == "hidden":
                state = SheetState.HIDDEN.value
            elif raw_state == "veryHidden":
                state = SheetState.VERY_HIDDEN.value

            # Extract merged ranges
            merged_ranges: list[str] = [str(rng) for rng in ws_formula.merged_cells.ranges]

            # Map coordinates in merged ranges
            # top_left -> True, non_top_left -> False
            merged_other_coords: set[tuple[int, int]] = set()
            merged_top_left_coords: set[tuple[int, int]] = set()

            for rng in ws_formula.merged_cells.ranges:
                top_r, top_c = rng.min_row, rng.min_col
                merged_top_left_coords.add((top_r, top_c))
                for r in range(rng.min_row, rng.max_row + 1):
                    for c in range(rng.min_col, rng.max_col + 1):
                        if (r, c) != (top_r, top_c):
                            merged_other_coords.add((r, c))

            formulas: list[dict[str, Any]] = []

            # Determine bounds
            max_r = max(ws_formula.max_row or 0, ws_data.max_row or 0)
            max_c = max(ws_formula.max_column or 0, ws_data.max_column or 0)

            if max_r == 0 or max_c == 0:
                sheets.append(
                    {
                        "name": sheet_name,
                        "state": state,
                        "rows": [],
                        "merged_ranges": merged_ranges,
                        "formulas": [],
                    }
                )
                continue

            # Header row (row 1)
            headers: list[str] = []
            for col_idx in range(1, max_c + 1):
                c_formula = ws_formula.cell(row=1, column=col_idx)
                c_data = ws_data.cell(row=1, column=col_idx)
                val = c_data.value if c_data.value is not None else c_formula.value
                headers.append(str(val).strip() if val is not None else f"col_{col_idx}")

            sheet_rows: list[dict[str, Any]] = []

            for r_idx in range(2, max_r + 1):
                row_values: dict[str, Any] = {}
                raw_cells: list[Any] = []
                is_blank = True

                for c_idx in range(1, max_c + 1):
                    cell_coord = f"{get_column_letter(c_idx)}{r_idx}"
                    cell_formula = ws_formula.cell(row=r_idx, column=c_idx)
                    cell_data = ws_data.cell(row=r_idx, column=c_idx)

                    # Formula inspection
                    is_formula = cell_formula.data_type == "f" or (
                        isinstance(cell_formula.value, str) and cell_formula.value.startswith("=")
                    )
                    formula_str: str | None = None
                    cached_val: Any = None

                    if is_formula:
                        formula_str = str(cell_formula.value)
                        cached_val = cell_data.value
                        formulas.append(
                            {
                                "cell": cell_coord,
                                "formula": formula_str,
                                "cached_value": cached_val,
                            }
                        )
                        if cached_val is None:
                            warnings.append(
                                f"formula_missing_cache: sheet '{sheet_name}', cell '{cell_coord}' "
                                f"has formula '{formula_str}' with no cached value"
                            )

                    # Determine effective cell value
                    in_merged_other = (r_idx, c_idx) in merged_other_coords
                    if in_merged_other:
                        # Non-top-left merged cell gets null with in_merged_range=True
                        eff_val = None
                    elif is_formula:
                        # Never evaluate formulas; use cached value or None
                        eff_val = cached_val
                    else:
                        eff_val = cell_data.value if cell_data.value is not None else cell_formula.value

                    # Format value
                    formatted_val = _format_cell_value(eff_val, cell_formula.number_format)
                    if formatted_val is not None and str(formatted_val).strip() != "":
                        is_blank = False

                    raw_cells.append(formatted_val)
                    h_name = headers[c_idx - 1] if c_idx - 1 < len(headers) else f"col_{c_idx}"
                    row_values[h_name] = formatted_val

                row_dict: dict[str, Any] = {
                    "row_num": r_idx,
                    "is_blank": is_blank,
                    "values": row_values,
                    "raw": raw_cells,
                }
                for k, v in row_values.items():
                    if k not in row_dict:
                        row_dict[k] = v

                sheet_rows.append(row_dict)

            sheets.append(
                {
                    "name": sheet_name,
                    "state": state,
                    "rows": sheet_rows,
                    "merged_ranges": merged_ranges,
                    "formulas": formulas,
                }
            )

        return {
            "sheets": sheets,
            "warnings": warnings,
        }
    finally:
        if wb_formula is not None:
            wb_formula.close()
        if wb_data is not None:
            wb_data.close()


def _read_xlsx_readonly(file_path: Path, warnings: list[str]) -> dict[str, Any]:
    """Fallback reader for large workbooks using read_only=True."""
    wb = None
    try:
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        except Exception as e:
            raise RejectedInputError(f"Malformed workbook: {e}") from e

        sheets: list[dict[str, Any]] = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            raw_state = ws.sheet_state or "visible"
            state = SheetState.VISIBLE.value
            if raw_state == "hidden":
                state = SheetState.HIDDEN.value
            elif raw_state == "veryHidden":
                state = SheetState.VERY_HIDDEN.value

            sheet_rows: list[dict[str, Any]] = []
            headers: list[str] = []

            for r_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
                if r_idx == 1:
                    headers = [
                        str(cell.value).strip() if cell.value is not None else f"col_{c_idx}"
                        for c_idx, cell in enumerate(row, start=1)
                    ]
                    continue

                row_values: dict[str, Any] = {}
                raw_cells: list[Any] = []
                is_blank = True

                for c_idx, cell in enumerate(row):
                    val = _format_cell_value(cell.value, cell.number_format)
                    if val is not None and str(val).strip() != "":
                        is_blank = False
                    raw_cells.append(val)
                    h_name = headers[c_idx] if c_idx < len(headers) else f"col_{c_idx + 1}"
                    row_values[h_name] = val

                row_dict: dict[str, Any] = {
                    "row_num": r_idx,
                    "is_blank": is_blank,
                    "values": row_values,
                    "raw": raw_cells,
                }
                for k, v in row_values.items():
                    if k not in row_dict:
                        row_dict[k] = v

                sheet_rows.append(row_dict)

            sheets.append(
                {
                    "name": sheet_name,
                    "state": state,
                    "rows": sheet_rows,
                    "merged_ranges": [],
                    "formulas": [],
                }
            )

        return {
            "sheets": sheets,
            "warnings": warnings,
        }
    finally:
        if wb is not None:
            wb.close()


__all__ = ["read_xlsx"]
