#!/usr/bin/env python3
"""ATLAS Dev 3 Master Demonstration Script.

Usage:
    python scripts/demo.py [--scripted-review] [--seed 42] [--data-dir data/synth] [--out outputs]

Demonstrates end-to-end capabilities:
Step 1: Intake & synthetic evidence verification for Case A & Case B.
Step 2: Processing Case A evidence pipeline (FIR, IO Report, CDR, Bank, Surveillance).
Step 3: Fact extraction, provenance alignment, and OCR uncertainty routing.
Step 4: Processing Case B evidence pipeline (FIR, CDR) with strict case isolation.
Step 5: Suggestion-only cross-case resolution (Vicky <-> Vikram Singh needs_review, hard negative ambiguous).
Step 6: Reviewer lifecycle: Confirm OCR -> Re-run resolver -> Approve/Merge -> Hash Chain Audit -> Reversible Split.
Writes summary to outputs/demo_summary.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from synth.generate import generate_all
from synth.names import (
    ARJUN_VERMA_A,
    POOJA_SHARMA_B,
    RAJESH_SHARMA_A,
    SUNITA_SHARMA_B,
    VICKY_B,
    VIKRAM_SINGH_A,
    VIKRAM_SINGH_HARD_NEG,
)

from atlas.contracts.enums import (
    EntityType,
    IdentifierTrust,
    ReviewActionType,
)
from atlas.contracts.records import CaseResult, ReviewAction
from atlas.output.report_html import write_report_html
from atlas.pipeline.runner import PipelineRunner
from atlas.resolve.audit import GENESIS_HASH
from atlas.resolve.candidates import generate_suggestions
from atlas.resolve.review import apply_review_action
from atlas.resolve.store_sqlite import SqliteEntityStore

MOCK_BANNER = """================================================================================
SCRIPTED MOCK PROVIDER: not live extraction
================================================================================
"""


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def run_demo(
    scripted_review: bool = False,
    seed: int = 42,
    data_dir_path: Path | str = "data/synth",
    out_dir_path: Path | str = "outputs",
) -> dict[str, Any]:
    """Execute master demonstration workflow."""
    data_dir = Path(data_dir_path).resolve()
    out_dir = Path(out_dir_path).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Mock provider honesty banner
    print(MOCK_BANNER)

    print("=" * 80)
    print("ATLAS Dev 3 — Multi-Source Evidence Ingestion & Resolution Demo")
    print(f"Random Seed:        {seed}")
    print(f"Data Directory:     {data_dir}")
    print(f"Output Directory:   {out_dir}")
    print(f"Scripted Review:    {scripted_review}")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # STEP 1: Generate or load synthetic dataset
    # -------------------------------------------------------------------------
    print("\n[STEP 1] Generating / Loading Synthetic Benchmark Dataset...")
    manifest_path = data_dir / "synthetic_manifest.json"
    if not manifest_path.is_file():
        print(f"  Generating synthetic documents into {data_dir} (seed={seed})...")
        generate_all(data_dir, seed=seed)
    else:
        print(f"  Existing synthetic dataset found at {data_dir}")

    case_a_files = [
        data_dir / "FIR_A.pdf",
        data_dir / "IO_REPORT_A.pdf",
        data_dir / "CDR_A.xlsx",
        data_dir / "BANK_A.csv",
        data_dir / "SURVEILLANCE_A.txt",
    ]
    case_b_files = [
        data_dir / "FIR_B.pdf",
        data_dir / "CDR_B.xlsx",
    ]

    for f in case_a_files + case_b_files:
        if not f.is_file():
            print(f"  [WARN] Missing expected file {f.name}, regenerating...")
            generate_all(data_dir, seed=seed)
            break

    print(f"  [OK] Verified {len(case_a_files)} Case A files and {len(case_b_files)} Case B files.")

    # -------------------------------------------------------------------------
    # STEP 2: Run Case A Pipeline
    # -------------------------------------------------------------------------
    case_a_id = "CASE-A-001"
    print(f"\n[STEP 2] Executing Case A Pipeline ({case_a_id})...")
    runner = PipelineRunner()
    result_a: CaseResult = runner.run(
        case_id=case_a_id,
        file_paths=case_a_files,
        provider="mock",
        output_dir=out_dir,
    )

    print(f"  Run ID:        {result_a.run.run_id}")
    print(f"  State:         {result_a.state.value}")
    print(f"  Documents:     {len(result_a.documents)}")
    print(f"  Mentions:      {len(result_a.mentions)}")
    print(f"  Relationships: {len(result_a.relationships)}")
    print(f"  Events:        {len(result_a.events)}")
    print(f"  Review Items:  {len(result_a.review_items)}")

    # -------------------------------------------------------------------------
    # STEP 3: Display Case A Facts & OCR Uncertainty Flag
    # -------------------------------------------------------------------------
    print("\n[STEP 3] Inspecting Case A Provenance & Uncertainty Flag...")
    # Find OCR phone mention in Case A
    phone_mentions = [m for m in result_a.mentions if m.type == EntityType.PHONE]
    ocr_phone = None
    for m_phone in phone_mentions:
        if m_phone.origin.value == "ocr" or m_phone.identifier_trust == IdentifierTrust.REVIEW_REQUIRED:
            ocr_phone = m_phone
            break

    if ocr_phone:
        print(f"  Detected OCR Phone:      {ocr_phone.surface_text}")
        print(f"  Normalized Value:        {ocr_phone.normalized_value}")
        print(f"  Origin:                  {ocr_phone.origin.value}")
        print(f"  Identifier Trust:        {ocr_phone.identifier_trust.value} (UNCONFIRMED)")
        print(f"  Source Document:         {ocr_phone.source.file_name} ({ocr_phone.source.doc_id})")
        print(f'  Verified Quote:          "{ocr_phone.source.quote}"')
        print("  Notice: Identifier is flagged 'review_required' — will not automatically link to entities.")
    else:
        print("  [WARN] OCR phone mention not found in Case A mentions list.")

    # -------------------------------------------------------------------------
    # STEP 4: Run Case B Pipeline (Case Isolation)
    # -------------------------------------------------------------------------
    case_b_id = "CASE-B-002"
    print(f"\n[STEP 4] Executing Case B Pipeline ({case_b_id})...")
    result_b: CaseResult = runner.run(
        case_id=case_b_id,
        file_paths=case_b_files,
        provider="mock",
        output_dir=out_dir,
    )

    print(f"  Run ID:        {result_b.run.run_id}")
    print(f"  State:         {result_b.state.value}")
    print(f"  Documents:     {len(result_b.documents)}")
    print(f"  Mentions:      {len(result_b.mentions)}")
    print(f"  Relationships: {len(result_b.relationships)}")
    print(f"  Events:        {len(result_b.events)}")
    print(f"  Review Items:  {len(result_b.review_items)}")

    # -------------------------------------------------------------------------
    # STEP 5: Cross-Case Resolution Suggestions
    # -------------------------------------------------------------------------
    print("\n[STEP 5] Generating Cross-Case Entity Resolution Suggestions...")
    db_path = out_dir / "entity_store.db"
    if db_path.exists():
        db_path.unlink()  # Clean run
    store = SqliteEntityStore(db_path)

    auth = {
        "user": "demo_analyst",
        "allowed_cases": [case_a_id, case_b_id],
    }

    # Populate Case A entities
    phone_id_a = ocr_phone.mention_id if ocr_phone else "M-PHONE-FIR-A"
    vikram_a: dict[str, Any] = {
        "person_id": f"PERSON:{case_a_id}:vikram",
        "case_id": case_a_id,
        "cluster_id": "c_vikram_a",
        "canonical_name": VIKRAM_SINGH_A.name,
        "name_key": "vikram singh",
        "name_variants": list(VIKRAM_SINGH_A.name_variants),
        "aliases": list(VIKRAM_SINGH_A.aliases),
        "attributes": {
            "father_name": VIKRAM_SINGH_A.father_name,
            "age": VIKRAM_SINGH_A.age,
            "address": VIKRAM_SINGH_A.address,
        },
        "mention_ids": [phone_id_a],
        "identifiers": [
            {
                "type": "phone",
                "value": VIKRAM_SINGH_A.phone,
                "trust": IdentifierTrust.REVIEW_REQUIRED.value,  # Unconfirmed OCR phone
                "confirmed_by": None,
            },
            {"type": "imei", "value": VIKRAM_SINGH_A.imei, "trust": IdentifierTrust.STRONG.value},
            {"type": "vehicle", "value": VIKRAM_SINGH_A.vehicle, "trust": IdentifierTrust.STRONG.value},
        ],
        "co_occurrences": ["ORG:DelhiTransCorp"],
    }

    case_a_persons: list[dict[str, Any]] = [
        vikram_a,
        {
            "person_id": f"PERSON:{case_a_id}:rajesh",
            "case_id": case_a_id,
            "cluster_id": "c_rajesh_a",
            "canonical_name": RAJESH_SHARMA_A.name,
            "name_key": "rajesh kumar sharma",
            "name_variants": list(RAJESH_SHARMA_A.name_variants),
            "aliases": [],
            "attributes": {
                "father_name": RAJESH_SHARMA_A.father_name,
                "age": RAJESH_SHARMA_A.age,
            },
            "mention_ids": ["M-A-RAJESH"],
            "identifiers": [
                {"type": "phone", "value": RAJESH_SHARMA_A.phone, "trust": IdentifierTrust.STRONG.value},
            ],
            "co_occurrences": [],
        },
        {
            "person_id": f"PERSON:{case_a_id}:arjun",
            "case_id": case_a_id,
            "cluster_id": "c_arjun_a",
            "canonical_name": ARJUN_VERMA_A.name,
            "name_key": "arjun verma",
            "name_variants": [],
            "aliases": [],
            "attributes": {"father_name": ARJUN_VERMA_A.father_name, "age": ARJUN_VERMA_A.age},
            "mention_ids": ["M-A-ARJUN"],
            "identifiers": [
                {"type": "phone", "value": ARJUN_VERMA_A.phone, "trust": IdentifierTrust.STRONG.value},
            ],
            "co_occurrences": [],
        },
    ]

    for p_dict in case_a_persons:
        store.store_case_person(p_dict)

    # Case B entities: Vicky, Hard Negative, Family Shared Phone
    vicky_b = {
        "person_id": f"PERSON:{case_b_id}:vicky",
        "case_id": case_b_id,
        "cluster_id": "c_vicky_b",
        "canonical_name": "Vicky",
        "name_key": "vicky",
        "name_variants": [],
        "aliases": [],
        "attributes": {
            "father_name": VICKY_B.father_name,
            "age": VICKY_B.age,
            "address": VICKY_B.address,
        },
        "mention_ids": ["M-B-VICKY"],
        "identifiers": [
            {"type": "phone", "value": VICKY_B.phone, "trust": IdentifierTrust.STRONG.value},
        ],
        "co_occurrences": ["ORG:DelhiTransCorp"],
    }

    hard_neg_b = {
        "person_id": f"PERSON:{case_b_id}:hard_neg",
        "case_id": case_b_id,
        "cluster_id": "c_hard_neg",
        "canonical_name": VIKRAM_SINGH_HARD_NEG.name,
        "name_key": "vikram singh",
        "name_variants": [],
        "aliases": [],
        "attributes": {
            "father_name": VIKRAM_SINGH_HARD_NEG.father_name,  # Mohan Singh vs Harbans Singh
            "age": VIKRAM_SINGH_HARD_NEG.age,  # 48 vs 32
            "address": VIKRAM_SINGH_HARD_NEG.address,
        },
        "mention_ids": ["M-B-HARD-NEG"],
        "identifiers": [
            {"type": "phone", "value": VIKRAM_SINGH_HARD_NEG.phone, "trust": IdentifierTrust.STRONG.value},
        ],
        "co_occurrences": [],
    }

    pooja_b = {
        "person_id": f"PERSON:{case_b_id}:pooja",
        "case_id": case_b_id,
        "canonical_name": POOJA_SHARMA_B.name,
        "name_key": "pooja sharma",
        "identifiers": [
            {"type": "phone", "value": POOJA_SHARMA_B.phone, "trust": IdentifierTrust.STRONG.value},
        ],
        "attributes": {"age": POOJA_SHARMA_B.age},
    }

    sunita_b = {
        "person_id": f"PERSON:{case_b_id}:sunita",
        "case_id": case_b_id,
        "canonical_name": SUNITA_SHARMA_B.name,
        "name_key": "sunita sharma",
        "identifiers": [
            {"type": "phone", "value": SUNITA_SHARMA_B.phone, "trust": IdentifierTrust.STRONG.value},
        ],
        "attributes": {"age": SUNITA_SHARMA_B.age},
    }

    case_b_persons = [vicky_b, hard_neg_b, pooja_b, sunita_b]

    # Generate cross-case suggestions
    suggestions_initial = generate_suggestions(
        store=store,
        current_case_id=case_b_id,
        new_persons=case_b_persons,
        auth=auth,
    )

    vicky_sug_init = next((s for s in suggestions_initial if s.mention_id == "M-B-VICKY"), None)
    hard_neg_sug_init = next((s for s in suggestions_initial if s.mention_id == "M-B-HARD-NEG"), None)

    vicky_status = vicky_sug_init.status.value if vicky_sug_init else "none"
    hard_neg_status = hard_neg_sug_init.status.value if hard_neg_sug_init else "no_match"
    rank_note_str = vicky_sug_init.rank_note if vicky_sug_init else "heuristic ordering, not a probability"

    print(f"  Vicky(B) <-> Vikram Singh(A) Status: {vicky_status} (Suggestion only; no auto-merge)")
    print(f"  Rank Note:                           '{rank_note_str}'")
    print(f"  Hard Negative Vikram Singh(B) Status:{hard_neg_status} (Contradiction detected in father/age)")

    # -------------------------------------------------------------------------
    # STEP 6: Reviewer Lifecycle Workflow
    # -------------------------------------------------------------------------
    confirm_ok = False
    approve_ok = False
    chain_after_merge_ok = False
    split_ok = False
    chain_after_split_ok = False
    total_actions = 0
    all_audit_actions: list[ReviewAction] = []

    if scripted_review:
        print("\n[STEP 6] Executing Scripted Reviewer Lifecycle Workflow...")

        # 6a. Reviewer confirms Case A OCR phone
        print("  [Action 1/3] CONFIRM_IDENTIFIER: Reviewer verifies OCR phone digits on FIR_A...")
        confirm_action = ReviewAction(
            action_id="ACT-DEMO-CONFIRM-01",
            type=ReviewActionType.CONFIRM_IDENTIFIER,
            actor="senior_investigator",
            at="2026-10-16T12:00:00Z",
            reason="Visual inspection of scanned FIR_A page 1 confirms phone +919876543210",
            target_ids=[phone_id_a],
            case_id=case_a_id,
            prev_hash=GENESIS_HASH,
            entry_hash="",
        )
        confirm_ok, msg1 = apply_review_action(store, confirm_action, auth=auth)
        all_audit_actions.append(confirm_action)
        print(f"    Result: {confirm_ok} ({msg1})")

        # Update person A's identifier in store to strong
        vikram_a["identifiers"][0]["trust"] = IdentifierTrust.STRONG.value
        vikram_a["identifiers"][0]["confirmed_by"] = "senior_investigator"
        store.store_case_person(vikram_a)

        # 6b. Re-run resolver with confirmed phone
        print("  Re-running Resolver: Phone is now confirmed eligible identifier...")
        suggestions_post_confirm = generate_suggestions(
            store=store,
            current_case_id=case_b_id,
            new_persons=case_b_persons,
            auth=auth,
        )
        vicky_sug_post = next((s for s in suggestions_post_confirm if s.mention_id == "M-B-VICKY"), None)
        re_resolved_status = vicky_sug_post.status.value if vicky_sug_post else "none"
        print(f"    Post-Confirmation Status: {re_resolved_status}")

        # 6c. Approve Match / Merge
        print("  [Action 2/3] APPROVE_MATCH: Investigator approves candidate merge link...")
        approve_action = ReviewAction(
            action_id="ACT-DEMO-APPROVE-02",
            type=ReviewActionType.APPROVE_MATCH,
            actor="senior_investigator",
            at="2026-10-16T12:05:00Z",
            reason="Alias 'Vicky' stated in FIR_A and verified shared telephone confirms person identity",
            target_ids=[str(vicky_b["person_id"]), str(vikram_a["person_id"])],
            case_id=case_b_id,
            prev_hash="",
            entry_hash="",
        )
        approve_ok, msg2 = apply_review_action(store, approve_action, auth=auth)
        all_audit_actions.append(approve_action)
        print(f"    Result: {approve_ok} ({msg2})")

        chain_after_merge_ok = store.verify_chain()
        print(f"    Cryptographic Audit Chain Integrity: {chain_after_merge_ok}")

        # 6d. Split (Reversibility)
        print("  [Action 3/3] SPLIT: Supervisor directive reverses merge to restore prior states...")
        split_action = ReviewAction(
            action_id="ACT-DEMO-SPLIT-03",
            type=ReviewActionType.SPLIT,
            actor="senior_investigator",
            at="2026-10-16T12:10:00Z",
            reason="Supervisor directive: maintain separate person records pending further corroboration",
            target_ids=[str(vicky_b["person_id"]), str(vikram_a["person_id"])],
            case_id=case_b_id,
            prev_hash="",
            entry_hash="",
        )
        split_ok, msg3 = apply_review_action(store, split_action, auth=auth)
        all_audit_actions.append(split_action)
        print(f"    Result: {split_ok} ({msg3})")

        chain_after_split_ok = store.verify_chain()
        print(f"    Cryptographic Audit Chain Integrity: {chain_after_split_ok}")

        total_actions = len(store.get_audit_entries())
        print(f"    Total Hash-Chained Audit Entries:    {total_actions}")
    else:
        print("\n[STEP 6] Reviewer Lifecycle (Interactive Mode):")
        if sys.stdin.isatty():
            try:
                user_input = input("  Confirm OCR phone digits +919876543210 for Case A? [y/N]: ")
                if user_input.strip().lower() == "y":
                    confirm_ok = True
                    print("  [OK] OCR Phone confirmed interactively.")
            except EOFError:
                pass
        else:
            print("  Running non-interactively; pass --scripted-review to execute full automated review lifecycle.")
        re_resolved_status = vicky_status

    # -------------------------------------------------------------------------
    # Render & Write HTML Reports
    # -------------------------------------------------------------------------
    print("\n[REPORT] Generating Standalone Self-Contained HTML Reports...")
    raw_texts_a: dict[str, str | dict[int, str]] = {
        f.name: f.read_text(encoding="utf-8", errors="replace") for f in case_a_files if f.suffix in (".txt", ".csv")
    }
    raw_texts_b: dict[str, str | dict[int, str]] = {
        f.name: f.read_text(encoding="utf-8", errors="replace") for f in case_b_files if f.suffix in (".txt", ".csv")
    }

    report_a_path = out_dir / case_a_id / "report.html"
    report_b_path = out_dir / case_b_id / "report.html"

    write_report_html(
        case_result=result_a,
        output_path=report_a_path,
        suggestions=suggestions_initial,
        audit_entries=all_audit_actions,
        raw_texts=raw_texts_a,
        data_dir=data_dir,
    )
    write_report_html(
        case_result=result_b,
        output_path=report_b_path,
        suggestions=suggestions_initial,
        audit_entries=all_audit_actions,
        raw_texts=raw_texts_b,
        data_dir=data_dir,
    )
    print(f"  [OK] Case A Report: {report_a_path}")
    print(f"  [OK] Case B Report: {report_b_path}")

    # -------------------------------------------------------------------------
    # Build & Write Deterministic Summary
    # -------------------------------------------------------------------------
    summary = {
        "pipeline_version": "3.3.0",
        "provider": "mock",
        "seed": seed,
        "case_a": {
            "case_id": case_a_id,
            "documents_count": len(result_a.documents),
            "mentions_count": len(result_a.mentions),
            "relationships_count": len(result_a.relationships),
            "events_count": len(result_a.events),
            "review_items_count": len(result_a.review_items),
            "state": result_a.state.value,
            "ocr_phone_trust": ocr_phone.identifier_trust.value if ocr_phone else "unknown",
        },
        "case_b": {
            "case_id": case_b_id,
            "documents_count": len(result_b.documents),
            "mentions_count": len(result_b.mentions),
            "relationships_count": len(result_b.relationships),
            "events_count": len(result_b.events),
            "review_items_count": len(result_b.review_items),
            "state": result_b.state.value,
        },
        "cross_case_resolution": {
            "vicky_candidate_id": f"PERSON:{case_a_id}:vikram",
            "vicky_status": vicky_status,
            "hard_negative_status": hard_neg_status,
            "rank_note": rank_note_str,
        },
        "review_workflow": {
            "confirm_identifier_success": confirm_ok,
            "re_resolved_status": re_resolved_status,
            "approve_match_success": approve_ok,
            "audit_chain_verified_after_merge": chain_after_merge_ok,
            "split_success": split_ok,
            "audit_chain_verified_after_split": chain_after_split_ok,
            "total_audit_actions": total_actions,
        },
        "audit_trail": {
            "genesis_hash": GENESIS_HASH,
            "chain_verified": store.verify_chain() if scripted_review else True,
        },
    }

    summary_path = out_dir / "demo_summary.json"
    summary_json = json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True)
    summary_path.write_text(summary_json, encoding="utf-8")
    print(f"\n[SUMMARY] Wrote deterministic demo summary to {summary_path}")

    store.close()
    return summary


def main() -> int:
    """CLI entrypoint for demo script."""
    parser = argparse.ArgumentParser(description="ATLAS Dev 3 Master Demonstration")
    parser.add_argument(
        "--scripted-review",
        action="store_true",
        help="Execute full scripted reviewer lifecycle (confirm, merge, audit, split)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed for deterministic dataset generation (default: 42)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/synth"),
        help="Directory containing synthetic evidence files (default: data/synth)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs"),
        help="Directory for pipeline run outputs (default: outputs)",
    )

    args = parser.parse_args()
    run_demo(
        scripted_review=args.scripted_review,
        seed=args.seed,
        data_dir_path=args.data_dir,
        out_dir_path=args.out,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
