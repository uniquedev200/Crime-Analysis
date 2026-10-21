"""Header mapping suggestion generator using schema-constrained LLM.

Implements PLAN.md section 5.7:
- suggest_mapping(headers: list[str], llm_client: Any) -> dict:
- Sends HEADERS ONLY to the LLM (never row values).
- Writes draft profile to profiles/pending/ for human audit and CLI confirmation.
- Output requires confirmation before use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from atlas.contracts.ids import safe_filename
from atlas.tabular.profiles import normalize_header

SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "profile_family": {"type": "string"},
        "suggested_profile_name": {"type": "string"},
        "mappings": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "reasoning": {"type": "string"},
    },
    "required": ["profile_family", "suggested_profile_name", "mappings"],
    "additionalProperties": False,
}


def suggest_mapping(
    headers: list[str],
    llm_client: Any = None,
    pending_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Analyze column headers (never row data) and write a draft pending profile.

    Requires confirmation (e.g. `python -m atlas confirm-profile <name>`) before application.
    """
    clean_headers = [str(h).strip() for h in headers if str(h).strip()]
    if not clean_headers:
        raise ValueError("Cannot suggest mapping for empty headers list")

    # Guard: Ensure no rows or multiline text are inadvertently passed
    for h in clean_headers:
        if "\n" in h or len(h) > 200:
            raise ValueError(f"Header value appears to contain row data or multiline text: {h[:50]}...")

    family = "cdr"
    suggested_name = "suggested_profile"
    mappings: dict[str, str] = {}

    if llm_client is not None and hasattr(llm_client, "extract"):
        system_prompt = (
            "You are a schema mapping assistant. Given a list of table column headers (never row data), "
            "determine if they represent CDR (call records) or Bank transactions, and suggest canonical mappings."
        )
        user_prompt = f"Column headers:\n{clean_headers}\nMap each header to a standard schema field."
        try:
            llm_result = llm_client.extract(system_prompt, user_prompt, SUGGESTION_SCHEMA)
            family = str(llm_result.get("profile_family", "cdr")).lower()
            suggested_name = str(llm_result.get("suggested_profile_name", f"{family}_suggested"))
            mappings = llm_result.get("mappings", {})
        except Exception:
            # Fallback to heuristic mapping if LLM fails
            llm_result = None

    if not mappings:
        # Heuristic fallback
        norm_map = {normalize_header(h): h for h in clean_headers}
        is_cdr = any(k in norm_map for k in ["calling_number", "called_number", "a_party", "b_party", "duration"])
        family = "cdr" if is_cdr else "bank"
        suggested_name = f"{family}_pending_draft"

        if family == "cdr":
            cdr_targets = {
                "calling_number": "a_party",
                "called_number": "b_party",
                "source": "a_party",
                "destination": "b_party",
                "duration": "duration_s",
                "call_duration": "duration_s",
                "type": "call_type",
                "call_type": "call_type",
                "time": "start_time",
                "datetime": "start_time",
                "imei": "imei",
                "cell_id": "cell_id",
            }
            for norm_h, orig_h in norm_map.items():
                if norm_h in cdr_targets:
                    mappings[orig_h] = cdr_targets[norm_h]
        else:
            bank_targets = {
                "transaction_id": "txn_id",
                "txnid": "txn_id",
                "date": "txn_date",
                "transaction_date": "txn_date",
                "debit_account": "from_account",
                "credit_account": "to_account",
                "from_acc": "from_account",
                "to_acc": "to_account",
                "amount": "amount",
                "txn_amount": "amount",
            }
            for norm_h, orig_h in norm_map.items():
                if norm_h in bank_targets:
                    mappings[orig_h] = bank_targets[norm_h]

    clean_name = safe_filename(suggested_name)
    draft_profile: dict[str, Any] = {
        "name": clean_name,
        "version": "1.0",
        "status": "pending_confirmation",
        "requires_confirmation": True,
        "profile_family": family,
        "original_headers": clean_headers,
        "header_aliases": mappings,
        "required_headers": (
            ["a_party", "b_party", "start_time", "duration_s", "call_type"]
            if family == "cdr"
            else ["txn_id", "txn_date", "from_account", "to_account", "amount"]
        ),
        "date_format": "%Y-%m-%d %H:%M:%S" if family == "cdr" else "%d/%m/%Y",
        "timezone": None,
    }

    p_dir = Path(pending_dir) if pending_dir else Path("profiles/pending")
    p_dir.mkdir(parents=True, exist_ok=True)
    out_file = p_dir / f"{clean_name}.yaml"

    with open(out_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(draft_profile, f, sort_keys=True, allow_unicode=True)

    return {
        "profile_name": clean_name,
        "pending_path": str(out_file),
        "status": "pending_confirmation",
        "requires_confirmation": True,
        "mappings": mappings,
        "profile_data": draft_profile,
    }


__all__ = ["suggest_mapping"]
