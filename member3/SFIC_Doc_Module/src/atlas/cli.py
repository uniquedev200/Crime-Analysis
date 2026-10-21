"""Command-line interface handlers for ATLAS Dev 3.

Implements CLI commands:
- python -m atlas run --case <case_id> --files <file1> [<file2> ...]
- python -m atlas status --case <case_id>
- python -m atlas results --case <case_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from atlas.config import get_settings
from atlas.pipeline.runner import PipelineRunner
from atlas.pipeline.status import get_case_status, get_latest_run_id, load_case_result


def handle_run(args: argparse.Namespace) -> int:
    """Execute pipeline run command."""
    case_id: str = args.case
    files: list[str] = args.files
    provider: str = args.provider or get_settings().LLM_PROVIDER
    out_dir: str = args.out or "./outputs"

    runner = PipelineRunner()
    result = runner.run(
        case_id=case_id,
        file_paths=files,
        provider=provider,
        output_dir=out_dir,
    )

    if provider.lower() == "mock":
        print("SCRIPTED MOCK PROVIDER: not live extraction")
        if not result.mentions and not result.events and not result.relationships:
            print(
                "WARNING: Zero extractions produced by mock provider. The mock provider has no scripted fixture for these file(s). Use a live provider (e.g. --provider groq or --provider openai) for unscripted files."
            )

    print(f"Run ID:        {result.run.run_id}")
    print(f"Case ID:       {result.case_id}")
    print(f"State:         {result.state.value}")
    print(f"Documents:     {len(result.documents)}")
    print(f"Mentions:      {len(result.mentions)}")
    print(f"Relationships: {len(result.relationships)}")
    print(f"Events:        {len(result.events)}")
    print(f"Review Items:  {len(result.review_items)}")
    print(f"Output Dir:    {Path(out_dir) / case_id / result.run.run_id}")

    return 0


def handle_status(args: argparse.Namespace) -> int:
    """Display latest run status for a case."""
    case_id: str = args.case
    run_id: str | None = getattr(args, "run_id", None)
    out_dir: str = args.out or "./outputs"

    latest_run = run_id or get_latest_run_id(case_id, output_dir=out_dir)
    if not latest_run:
        print(f"No runs found for case '{case_id}' in '{out_dir}'", file=sys.stderr)
        return 1

    status = get_case_status(case_id, run_id=latest_run, output_dir=out_dir)
    if status is None:
        print(f"Run '{latest_run}' found but could not determine status", file=sys.stderr)
        return 1

    print(f"Case ID: {case_id}")
    print(f"Run ID:  {latest_run}")
    print(f"Status:  {status.value}")
    return 0


def handle_results(args: argparse.Namespace) -> int:
    """Output valid JSON of CaseResult to stdout."""
    case_id: str = args.case
    run_id: str | None = getattr(args, "run_id", None)
    out_dir: str = args.out or "./outputs"

    result = load_case_result(case_id, run_id=run_id, output_dir=out_dir)
    if not result:
        print(f"No results found for case '{case_id}'", file=sys.stderr)
        return 1

    result_dict = result.model_dump(mode="json")
    json_output = json.dumps(result_dict, indent=2, ensure_ascii=False)
    sys.stdout.write(json_output + "\n")
    return 0


def handle_inspect(args: argparse.Namespace) -> int:
    """Display human-readable terminal summary of extracted entities and connections."""
    case_id: str = args.case
    run_id: str | None = getattr(args, "run_id", None)
    out_dir: str = args.out or "./outputs"

    result = load_case_result(case_id, run_id=run_id, output_dir=out_dir)
    if not result:
        print(f"No results found for case '{case_id}' in '{out_dir}'", file=sys.stderr)
        return 1

    print("=" * 80)
    print(f" ATLAS EXTRACTION INSPECTOR - CASE: {result.case_id}")
    print(f" Run ID:    {result.run.run_id}")
    print(f" Provider:  {result.run.provider} ({result.run.model})")
    print(f" Status:    {result.state.value.upper()}")
    print("=" * 80)

    # 1. Documents Summary
    print(f"\n[1] DOCUMENTS PROCESSED ({len(result.documents)}):")
    for doc in result.documents:
        print(
            f"  * {doc.file_name:<30} [ID: {doc.doc_id}] ({doc.detected_type.upper()}, {doc.size_bytes} bytes, Status: {doc.status.value})"
        )

    # 2. Extracted Mentions (Entities)
    print(f"\n[2] EXTRACTED ENTITIES ({len(result.mentions)}):")
    if not result.mentions:
        print("  (No entities extracted)")
    else:
        by_type: dict[str, list] = {}
        for m in result.mentions:
            by_type.setdefault(m.type.value, []).append(m)

        for etype in sorted(by_type.keys()):
            items = by_type[etype]
            print(f"\n  --- {etype} ({len(items)}) ---")
            for m in items:
                role_str = f" [Role: {m.stated_role.value}]" if m.stated_role else ""
                norm_str = f" -> Normalized: '{m.normalized_value}'" if m.normalized_value else ""
                trust_str = (
                    f" [Trust: {m.identifier_trust.value}]" if m.identifier_trust.value != "not_applicable" else ""
                )
                src_str = f" (Unit: {m.source.unit_id})" if m.source else ""
                print(f"  * {m.surface_text:<25}{role_str}{norm_str}{trust_str}{src_str}")
                if m.attributes:
                    for attr in m.attributes:
                        print(f"      - {attr.name.value}: {attr.value_text}")
                if m.source and m.source.quote:
                    print(f'      Quote: "{m.source.quote.strip()}"')

    # 3. Connections / Relationships
    print(f"\n[3] GRAPH CONNECTIONS & RELATIONSHIPS ({len(result.relationships)}):")
    if not result.relationships:
        print("  (No connections identified)")
    else:
        mentions_by_id = {m.mention_id: m for m in result.mentions}
        for rel in result.relationships:
            subj = mentions_by_id.get(rel.subject_mention_id)
            obj = mentions_by_id.get(rel.object_mention_id)
            subj_name = f"{subj.surface_text} ({subj.type.value})" if subj else rel.subject_mention_id
            obj_name = f"{obj.surface_text} ({obj.type.value})" if obj else rel.object_mention_id
            assertion_str = f" [{rel.assertion.value}]"
            print(f"  * {subj_name}  ---[{rel.type.value}]--->  {obj_name}{assertion_str}")
            if rel.source and rel.source.quote:
                print(f'      Evidence: "{rel.source.quote.strip()}"')

    # 4. Events & Timeline
    print(f"\n[4] EVENTS & TIMELINE ({len(result.events)}):")
    if not result.events:
        print("  (No events recorded)")
    else:
        for ev in result.events:
            t_str = f" @ {ev.time.original_text}" if ev.time and ev.time.original_text else ""
            print(f"  * [{ev.type.value}] {ev.description}{t_str}")

    # 5. Human Review Items
    print(f"\n[5] AUDIT & HUMAN REVIEW QUEUE ({len(result.review_items)}):")
    if not result.review_items:
        print("  (No items flagged for review)")
    else:
        for rev in result.review_items:
            print(f"  * [{rev.kind.value}] {rev.detail} (Status: {rev.status.value})")

    # 6. Rejections (Model outputs rejected by verification)
    if result.rejections:
        print(f"\n[6] REJECTIONS / INVALID EXTRACTS FILTERED OUT ({len(result.rejections)}):")
        for rej in result.rejections:
            excerpt_str = f" | Excerpt: '{rej.model_item_excerpt}'" if rej.model_item_excerpt else ""
            print(f"  * [{rej.kind.value}] {rej.reason}{excerpt_str}")

    print("\n" + "=" * 80 + "\n")
    return 0


def handle_demo(args: argparse.Namespace) -> int:
    """Execute master demo workflow."""
    from scripts.demo import run_demo

    scripted_review: bool = getattr(args, "scripted_review", False)
    seed: int = getattr(args, "seed", 42)
    data_dir = Path(getattr(args, "data_dir", "data/synth"))
    out_dir = Path(getattr(args, "out", "outputs"))

    run_demo(
        scripted_review=scripted_review,
        seed=seed,
        data_dir_path=data_dir,
        out_dir_path=out_dir,
    )
    return 0


def handle_eval(args: argparse.Namespace) -> int:
    """Execute evaluation comparing extraction outputs against ground truth."""
    from atlas.eval.runner import EvalRunner
    from atlas.pipeline.status import load_case_result

    out_dir = Path(getattr(args, "out", "./outputs"))
    truth_dir = Path(getattr(args, "truth_dir", "./tests/fixtures"))
    runner = EvalRunner(truth_dir=truth_dir)

    print("Running ATLAS Pipeline Evaluation...")
    cases = ["CASE-A-001", "CASE-B-002"]
    metrics_by_case = {}

    for case_id in cases:
        result = load_case_result(case_id, output_dir=str(out_dir))
        truth = runner.load_truth_for_case(case_id)
        if result:
            eval_res = runner.evaluate_case(result.model_dump(mode="json"), truth)
            metrics_by_case[case_id] = eval_res
            m_overall = eval_res["mentions"]["overall"]
            print(
                f"[{case_id}] Mentions Precision: {m_overall['precision']:.2f}, Recall: {m_overall['recall']:.2f}, F1: {m_overall['f1']:.2f}"
            )

    eval_md = Path("docs/EVALUATION.md")
    eval_text = "# Evaluation Report (Measured Pipeline Accuracy)\n\n"
    eval_text += "> **Provider**: Scripted Mock Provider (Baseline Measurement)\n"
    eval_text += "> **Fixture Set**: Synthetic test cases (`tests/fixtures/*.truth.json`)\n\n"
    eval_text += "Metrics measured comparing pipeline outputs against synthetic ground truth fixtures under deterministic review rules:\n\n"
    eval_text += "| Case ID | Mentions Precision | Mentions Recall | Mentions F1 | Exact Match ID Acc | Quote Rejection Rate | OCR ID Review Rate |\n"
    eval_text += "|---|---|---|---|---|---|---|\n"
    for cid, m in metrics_by_case.items():
        m_prec = m["mentions"]["overall"]["precision"]
        m_rec = m["mentions"]["overall"]["recall"]
        m_f1 = m["mentions"]["overall"]["f1"]
        eval_text += f"| {cid} | {m_prec:.2f} | {m_rec:.2f} | {m_f1:.2f} | {m['identifier_exact_match_accuracy']:.2f} | {m['quote_rejection_rate']:.2f} | {m['ocr_identifier_review_rate']:.2f} |\n"
    eval_text += "\n### Audit & Integrity Observations\n"
    eval_text += (
        "- **Mock Provider Honesty**: Baseline metrics reflect the deterministic scripted mock provider responses.\n"
    )
    eval_text += "- **Quote Rejection**: Quotes not precisely locatable in unit text are strictly rejected by the validator to prevent hallucinated citations.\n"
    eval_text += "- **Review Queue Routing**: Unconfirmed table headers, low-confidence OCR digits, and inferred roles are automatically routed to human review.\n"
    eval_text += "\n*Note: Quality numbers are measured against synthetic fixtures and never claimed for real unmeasured handwriting/Indic data.*\n"
    eval_md.write_text(eval_text, encoding="utf-8")
    print(f"Wrote evaluation report to {eval_md}")
    return 0


def handle_llm_smoke(args: argparse.Namespace) -> int:
    """Smoke test LLM client on a single synthetic chunk."""
    from atlas.config import get_settings
    from atlas.contracts.model_schema import MODEL_SCHEMA, validate_model_output
    from atlas.llm.client import get_llm_client

    settings = get_settings()
    is_live = getattr(args, "live", False)
    if is_live:
        print(f"Executing LIVE LLM smoke test on provider: {settings.LLM_PROVIDER}")
        client = get_llm_client(settings)
    else:
        print("Executing MOCK LLM smoke test (offline)")
        from atlas.llm.mock import MockProvider

        client = MockProvider()

    system_prompt = "You extract structured facts. Return data matching the schema."
    user_prompt = "Case documents follow. [UNIT DOC-1:p001] FIR No: 123/2023. Complainant: Rajesh Sharma."
    raw = client.extract(system_prompt, user_prompt, MODEL_SCHEMA)
    validated = validate_model_output(raw)
    print(f"Smoke test SUCCESS! Validated output with {len(validated.get('mentions', []))} mentions.")
    return 0


def handle_confirm_profile(args: argparse.Namespace) -> int:
    """Promote a pending header mapping profile to active profiles."""
    name: str = args.name
    pending_file = Path("profiles/pending") / f"{name}.yaml"
    target_file = Path("profiles") / f"{name}.yaml"

    if not pending_file.is_file():
        print(f"Error: pending profile '{pending_file}' not found.", file=sys.stderr)
        return 1

    import shutil

    shutil.copy2(pending_file, target_file)
    print(f"Confirmed and activated profile: {target_file}")
    return 0


def handle_register_synthetic(args: argparse.Namespace) -> int:
    """Register synthetic evidence file(s) into synthetic manifest."""
    import hashlib

    target_path = Path(args.path)
    manifest_path = Path(args.manifest)
    if not target_path.exists():
        print(f"Error: target path does not exist: {target_path}", file=sys.stderr)
        return 1

    files = [target_path] if target_path.is_file() else list(target_path.rglob("*.*"))
    if not files:
        print(f"No files found under: {target_path}")
        return 0

    manifest_data: dict[str, str] = {}
    if manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest_data = {}

    added = 0
    for f in files:
        if f.is_file():
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            manifest_data[h] = f.name
            added += 1

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(manifest_data, fp, indent=2, ensure_ascii=False)

    print(f"Registered {added} synthetic files into {manifest_path} (total: {len(manifest_data)})")
    return 0


def handle_ui(args: argparse.Namespace) -> int:
    """Launch the local web UI (FastAPI + uvicorn) for upload/inspection testing."""
    import uvicorn

    from atlas.api.app import app

    host: str = getattr(args, "host", "127.0.0.1")
    port: int = getattr(args, "port", 8000)
    cfg = get_settings()

    print("=" * 72)
    print("ATLAS Entity Extraction Inspector")
    print(f"  URL:      http://{host}:{port}/")
    print(f"  Provider: {cfg.LLM_PROVIDER}")
    if cfg.LLM_PROVIDER.lower().strip() == "mock":
        print("  SCRIPTED MOCK PROVIDER: not live extraction")
    print("  Press Ctrl+C to stop.")
    print("=" * 72)

    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build root CLI argument parser with subparsers."""
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="ATLAS Dev 3 — Document-to-JSON evidence pipeline",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Subcommand: run
    run_parser = subparsers.add_parser("run", help="Run pipeline on input files for a case")
    run_parser.add_argument("--case", required=True, help="Case identifier (^[A-Za-z0-9_-]{1,64}$)")
    run_parser.add_argument("--files", nargs="+", required=True, help="One or more input evidence file paths")
    run_parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider: mock, groq, openai, gemini (default: LLM_PROVIDER from configuration)",
    )
    run_parser.add_argument("--out", default="./outputs", help="Base output directory (default: ./outputs)")

    # Subcommand: status
    status_parser = subparsers.add_parser("status", help="Query latest pipeline run status for a case")
    status_parser.add_argument("--case", required=True, help="Case identifier")
    status_parser.add_argument("--run-id", default=None, help="Specific run ID (default: latest run)")
    status_parser.add_argument("--out", default="./outputs", help="Base output directory (default: ./outputs)")

    # Subcommand: results
    results_parser = subparsers.add_parser("results", help="Print CaseResult JSON for a case")
    results_parser.add_argument("--case", required=True, help="Case identifier")
    results_parser.add_argument("--run-id", default=None, help="Specific run ID (default: latest run)")
    results_parser.add_argument("--out", default="./outputs", help="Base output directory (default: ./outputs)")

    # Subcommand: demo
    demo_parser = subparsers.add_parser("demo", help="Run master end-to-end pipeline demonstration")
    demo_parser.add_argument("--scripted-review", action="store_true", help="Execute scripted reviewer actions")
    demo_parser.add_argument("--seed", type=int, default=42, help="Seed for synthetic generation (default: 42)")
    demo_parser.add_argument("--data-dir", default="data/synth", help="Data directory (default: data/synth)")
    demo_parser.add_argument("--out", default="outputs", help="Output directory (default: outputs)")

    # Subcommand: eval
    eval_parser = subparsers.add_parser("eval", help="Run evaluation metrics against ground truth")
    eval_parser.add_argument("--out", default="./outputs", help="Base output directory")
    eval_parser.add_argument("--truth-dir", default="./tests/fixtures", help="Ground truth fixtures directory")

    # Subcommand: llm-smoke
    smoke_parser = subparsers.add_parser("llm-smoke", help="Run LLM client smoke test")
    smoke_parser.add_argument("--live", action="store_true", help="Run against live configured provider")

    # Subcommand: confirm-profile
    profile_parser = subparsers.add_parser("confirm-profile", help="Confirm and activate a pending tabular profile")
    profile_parser.add_argument("name", help="Profile name to confirm (from profiles/pending/<name>.yaml)")

    # Subcommand: register-synthetic
    register_parser = subparsers.add_parser(
        "register-synthetic", help="Register synthetic evidence file(s) into synthetic manifest"
    )
    register_parser.add_argument("path", help="File or directory of files to register")
    register_parser.add_argument(
        "--manifest",
        default="data/synthetic_manifest.json",
        help="Manifest path (default: data/synthetic_manifest.json)",
    )

    # Subcommand: inspect
    inspect_parser = subparsers.add_parser(
        "inspect", help="Display human-readable terminal report of entities and connections"
    )
    inspect_parser.add_argument("--case", required=True, help="Case identifier")
    inspect_parser.add_argument("--run-id", default=None, help="Specific run ID (default: latest run)")
    inspect_parser.add_argument("--out", default="./outputs", help="Base output directory (default: ./outputs)")

    # Subcommand: ui
    ui_parser = subparsers.add_parser("ui", help="Launch the local upload/inspection web UI")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    ui_parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")

    return parser


def cli_main(argv: Sequence[str] | None = None) -> int:
    """Entry point for atlas CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand == "run":
        return handle_run(args)
    if args.subcommand == "status":
        return handle_status(args)
    if args.subcommand == "results":
        return handle_results(args)
    if args.subcommand == "inspect":
        return handle_inspect(args)
    if args.subcommand == "ui":
        return handle_ui(args)
    if args.subcommand == "demo":
        return handle_demo(args)
    if args.subcommand == "eval":
        return handle_eval(args)
    if args.subcommand == "llm-smoke":
        return handle_llm_smoke(args)
    if args.subcommand == "confirm-profile":
        return handle_confirm_profile(args)
    if args.subcommand == "register-synthetic":
        return handle_register_synthetic(args)

    print(f"Not yet implemented: {args.subcommand}")
    return 0


__all__ = [
    "build_parser",
    "cli_main",
    "handle_confirm_profile",
    "handle_demo",
    "handle_eval",
    "handle_inspect",
    "handle_llm_smoke",
    "handle_register_synthetic",
    "handle_results",
    "handle_run",
    "handle_status",
    "handle_ui",
]
