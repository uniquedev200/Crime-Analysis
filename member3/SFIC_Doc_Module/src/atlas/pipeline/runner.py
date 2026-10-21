"""Pipeline runner executing end-to-end evidence ingestion, extraction, and consolidation.

Implements PLAN.md Section 3, Section 5, and H3 specifications:
Stages executed in exact order:
1. Intake & integrity (detect_file_type, check_file_size, compute_sha256, store_original, write_receipt, check_synthetic)
2. Extraction (digital/scanned PDF routing via PdfExtractor, image via extract_from_image,
   text/JSON, tabular CSV/XLSX via read_csv/read_xlsx + parse_cdr/parse_bank if profile detected)
3. LLM extraction & provenance verification (chunk_units, build_prompt, execute_with_retry, verify_model_output)
4. Within-document consolidation (consolidate_within_doc)
5. Within-case consolidation (consolidate_within_case)
6. Output writing (OutputWriter.write_all)

JobState management:
- All chunks OK and no rejections/review -> completed
- Any rejections, review items or failed chunks (with >= 1 chunk OK) -> completed_with_warnings
- All chunks failed -> failed
- Final CaseResult fails Pydantic validation -> failed_validation
- Input refused -> rejected_input
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from atlas.config import AtlasSettings, get_settings
from atlas.consolidate.within_case import consolidate_within_case
from atlas.consolidate.within_doc import consolidate_within_doc
from atlas.contracts.enums import (
    DocumentStatus,
    JobState,
    PageMethod,
    ReviewItemStatus,
    ReviewKind,
    SheetState,
)
from atlas.contracts.ids import (
    make_doc_id,
    make_idempotency_key,
    make_review_id,
    make_run_id,
    validate_case_id,
)
from atlas.contracts.records import (
    Aggregate,
    CaseResult,
    DocumentRecord,
    Event,
    Mention,
    PageInfo,
    Rejection,
    Relationship,
    ReviewItem,
    RunMeta,
    SheetInfo,
)
from atlas.errors import IntegrityError, RejectedInputError
from atlas.extract.image import extract_from_image
from atlas.extract.jsonfile import extract_json_file_units
from atlas.extract.pdf import PdfExtractor
from atlas.extract.tabular_pdf_detect import is_tabular_pdf
from atlas.extract.text import extract_text_file_units
from atlas.extract.units import Unit
from atlas.ingest.detect import detect_file_type
from atlas.ingest.integrity import compute_sha256, write_receipt
from atlas.ingest.limits import check_file_size, check_image_pixels, check_pdf_pages
from atlas.ingest.originals import store_original
from atlas.ingest.synthetic_guard import check_synthetic
from atlas.llm.build_prompt import PROMPT_VERSION, build_prompt
from atlas.llm.client import get_llm_client
from atlas.llm.mock import MockProvider
from atlas.llm.retry import execute_with_retry
from atlas.output.writer import OutputWriter
from atlas.pipeline.jobs import compute_job_state
from atlas.ports.llm import LlmClientPort
from atlas.provenance.chunking import chunk_units
from atlas.provenance.verify import verify_model_output
from atlas.tabular.anpr import parse_anpr
from atlas.tabular.bank import parse_bank
from atlas.tabular.cdr import parse_cdr
from atlas.tabular.csv_reader import read_csv
from atlas.tabular.profiles import create_mapping_unconfirmed_review, detect_profile, load_profile
from atlas.tabular.tower import parse_tower
from atlas.tabular.xlsx_reader import read_xlsx
from atlas.version import (
    NORMALIZATION_VERSION,
    PIPELINE_VERSION,
    RESOLVER_VERSION,
    SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Executes the complete multi-stage ATLAS pipeline for a case."""

    def __init__(
        self,
        settings: AtlasSettings | None = None,
        llm_client: LlmClientPort | None = None,
        ocr_engine: Any = None,
        output_writer: OutputWriter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._llm_client = llm_client
        self.ocr_engine = ocr_engine
        if self.ocr_engine is None:
            try:
                from atlas.ocr.tesseract import TesseractEngine

                self.ocr_engine = TesseractEngine(
                    tesseract_cmd=self.settings.TESSERACT_CMD,
                    tessdata_prefix=self.settings.TESSDATA_PREFIX or None,
                    validate_langs=False,
                )
            except Exception:
                self.ocr_engine = None

        self.output_writer = output_writer or OutputWriter(base_output_dir=self.settings.OUTPUT_DIR)

    @property
    def llm_client(self) -> LlmClientPort:
        """Active LLM client instance."""
        if self._llm_client is None:
            self._llm_client = get_llm_client(settings=self.settings)
        return self._llm_client

    def _get_active_client(self, provider_override: str | None = None) -> LlmClientPort:
        """Resolve LLM client respecting optional per-run provider override."""
        if provider_override:
            prov = provider_override.lower().strip()
            if prov == "mock":
                return MockProvider()
            override_settings = self.settings.model_copy(update={"LLM_PROVIDER": prov})
            return get_llm_client(settings=override_settings)
        return self.llm_client

    def run(
        self,
        case_id: str,
        file_paths: Sequence[str | Path],
        provider: str | None = None,
        output_dir: Path | str | None = None,
        custom_responses: dict[str, Any] | None = None,
        prompt_version: str | None = None,
        model_version: str | None = None,
    ) -> CaseResult:
        """Execute the end-to-end pipeline on input files for a case.

        Args:
            case_id: Validated case identifier.
            file_paths: Sequence of document file paths to process.
            provider: Optional LLM provider override ('mock', 'openai', 'gemini').
            output_dir: Optional output directory override.
            custom_responses: Optional dict of scripted LLM responses for mock provider.
            prompt_version: Optional prompt version string (defaults to PROMPT_VERSION).
            model_version: Optional model version string override.

        Returns:
            Validated CaseResult object written to outputs/{case_id}/{run_id}/.
        """
        validate_case_id(case_id)
        started_at = datetime.now(UTC).isoformat()
        run_id = make_run_id()

        active_client = self._get_active_client(provider)
        if custom_responses and isinstance(active_client, MockProvider):
            for k, resp in custom_responses.items():
                if "_" in k:
                    doc_key, c_num_str = k.rsplit("_", 1)
                    active_client.register_response(doc_key, int(c_num_str), resp)

        active_provider = active_client.provider_name
        active_model = model_version or active_client.model_name
        active_prompt_ver = prompt_version or PROMPT_VERSION

        trace_entries: list[dict[str, Any]] = []
        doc_receipts: list[dict[str, Any]] = []
        documents: list[DocumentRecord] = []

        all_mentions: list[Mention] = []
        all_relationships: list[Relationship] = []
        all_events: list[Event] = []
        all_aggregates: list[Aggregate] = []
        all_review_items: list[ReviewItem] = []
        all_rejections: list[Rejection] = []
        warnings: list[str] = []

        total_chunks = 0
        failed_chunks = 0
        total_llm_calls = 0
        input_refused = False

        manifest_path = Path(self.settings.DATA_DIR) / "synthetic_manifest.json"
        if not manifest_path.is_file():
            fallback_manifest = Path("tests/fixtures/synthetic_manifest.json")
            if fallback_manifest.is_file():
                manifest_path = fallback_manifest

        # STAGE 1 & 2: Process each document
        for fpath in file_paths:
            path = Path(fpath).resolve()

            # Stage 1: Intake & Integrity
            intake_start = time.perf_counter()
            try:
                check_file_size(path, max_mb=self.settings.MAX_FILE_MB)
                detected_type = detect_file_type(path)
                sha256 = compute_sha256(path)
                doc_id = make_doc_id(sha256)

                check_synthetic(sha256, active_provider, manifest_path)
                store_original(path, sha256, Path(self.settings.DATA_DIR))
                receipt_path = write_receipt(
                    case_id=case_id,
                    filename=path.name,
                    sha256=sha256,
                    size=path.stat().st_size,
                    run_id=run_id,
                    out_dir=Path(self.settings.DATA_DIR) / "receipts" / doc_id,
                )
                doc_receipts.append(
                    {
                        "doc_id": doc_id,
                        "file_name": path.name,
                        "file_sha256": sha256,
                        "size_bytes": path.stat().st_size,
                        "receipt_path": str(receipt_path),
                    }
                )

                intake_duration = (time.perf_counter() - intake_start) * 1000
                trace_entries.append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "stage": "intake",
                        "duration_ms": round(intake_duration, 2),
                        "status": "ok",
                        "case_id": case_id,
                        "doc_id": doc_id,
                        "file_sha256": sha256,
                    }
                )
            except RejectedInputError as exc:
                input_refused = True
                intake_duration = (time.perf_counter() - intake_start) * 1000
                msg = str(exc)
                warnings.append(f"Intake rejected: {path.name}: {msg}")
                trace_entries.append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "stage": "intake",
                        "duration_ms": round(intake_duration, 2),
                        "status": "rejected_input",
                        "case_id": case_id,
                        "error_type": "RejectedInputError",
                    }
                )
                doc_rec = DocumentRecord(
                    doc_id=f"DOC-REJECTED-{path.stem[:8]}",
                    file_name=path.name,
                    file_sha256="",
                    size_bytes=path.stat().st_size if path.is_file() else 0,
                    detected_type="unknown",
                    status=DocumentStatus.REJECTED_INPUT,
                    warnings=[msg],
                    case_id=case_id,
                )
                documents.append(doc_rec)
                continue

            # Stage 2: Extraction
            extract_start = time.perf_counter()
            doc_units: list[Unit] = []
            pages_info: list[PageInfo] = []
            sheets_info: list[SheetInfo] = []
            doc_warnings: list[str] = []
            # Re-verify integrity to guarantee bytes have not been mutated since intake
            current_sha = compute_sha256(path)
            if current_sha != sha256:
                raise IntegrityError(
                    f"Evidence file was mutated during processing: expected {sha256}, got {current_sha}"
                )

            row_count: int | None = None

            try:
                if detected_type == "pdf":
                    check_pdf_pages(path, max_pages=self.settings.MAX_PDF_PAGES)
                    pdf_extractor = PdfExtractor(
                        ocr_engine=self.ocr_engine,
                        min_chars=self.settings.PDF_TEXT_MIN_CHARS,
                        dpi=self.settings.OCR_DPI,
                        ocr_langs=[self.settings.OCR_LANGS],
                    )
                    pages_info, doc_units = pdf_extractor.extract_document(path, doc_id)

                    # Check tabular PDF detection
                    combined_pdf_text = " ".join(
                        u.text for u in doc_units if ":p" in u.unit_id and ":l" not in u.unit_id
                    )
                    if is_tabular_pdf(combined_pdf_text):
                        doc_warnings.append("tabular_pdf_detected: likely tabular PDF processed as plain text")
                        tab_review = ReviewItem(
                            review_id=make_review_id(case_id, ReviewKind.TABULAR_PDF_DETECTED.value, doc_id),
                            case_id=case_id,
                            kind=ReviewKind.TABULAR_PDF_DETECTED,
                            target_ids=[doc_id],
                            detail="Likely tabular PDF detected; processed as plain text with warning",
                            status=ReviewItemStatus.OPEN,
                        )
                        all_review_items.append(tab_review)

                elif detected_type in ("png", "jpg", "jpeg", "tif", "tiff"):
                    check_image_pixels(path, max_pixels=self.settings.MAX_IMAGE_PIXELS)
                    if self.ocr_engine is None:
                        doc_warnings.append("OCR engine not available for image extraction")
                    else:
                        img_res = extract_from_image(path, self.ocr_engine, langs=[self.settings.OCR_LANGS])
                        raw_text = img_res.get("raw_text", "")
                        page_unit = Unit(
                            unit_id=f"{doc_id}:p001",
                            text=raw_text,
                            page=1,
                            method="ocr",
                            doc_id=doc_id,
                        )
                        doc_units.append(page_unit)
                        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
                        for l_idx, line in enumerate(lines, start=1):
                            doc_units.append(
                                Unit(
                                    unit_id=f"{doc_id}:p001:l{l_idx:03d}",
                                    text=line,
                                    page=1,
                                    line_start=l_idx,
                                    line_end=l_idx,
                                    method="ocr",
                                    doc_id=doc_id,
                                )
                            )
                        pages_info.append(
                            PageInfo(
                                page=1,
                                method=PageMethod.OCR,
                                chars=len(raw_text),
                                warnings=[],
                            )
                        )

                elif detected_type == "txt":
                    doc_units = extract_text_file_units(path, doc_id)
                    total_chars = sum(len(u.text) for u in doc_units)
                    pages_info.append(
                        PageInfo(
                            page=1,
                            method=PageMethod.TEXT,
                            chars=total_chars,
                            warnings=[],
                        )
                    )

                elif detected_type == "json":
                    doc_units = extract_json_file_units(path, doc_id)
                    total_chars = sum(len(u.text) for u in doc_units)
                    pages_info.append(
                        PageInfo(
                            page=1,
                            method=PageMethod.TEXT,
                            chars=total_chars,
                            warnings=[],
                        )
                    )

                elif detected_type == "csv":
                    # Tabular CSV - never goes to LLM
                    profiles_dir = Path("profiles")
                    if not profiles_dir.is_dir():
                        profiles_dir = Path(__file__).resolve().parent.parent.parent.parent / "profiles"

                    csv_res = read_csv(path)
                    headers: list[str] = list(csv_res.get("headers", []))
                    rows: list[dict[str, Any]] = list(csv_res.get("rows", []))
                    doc_warnings.extend(csv_res.get("warnings", []))
                    row_count = len(rows)

                    p_name = detect_profile(headers, profiles_dir)
                    if p_name and p_name.startswith("cdr"):
                        profile = load_profile(profiles_dir / f"{p_name}.yaml")
                        c_events, c_aggs, c_mentions = parse_cdr(
                            rows,
                            profile,
                            case_id=case_id,
                            doc_id=doc_id,
                            file_name=path.name,
                            file_sha256=sha256,
                            review_items=all_review_items,
                        )
                        all_events.extend(c_events)
                        all_aggregates.extend(c_aggs)
                        all_mentions.extend(c_mentions)
                    elif p_name and p_name.startswith("bank"):
                        profile = load_profile(profiles_dir / f"{p_name}.yaml")
                        b_events, b_aggs, b_mentions = parse_bank(
                            rows,
                            profile,
                            case_id=case_id,
                            doc_id=doc_id,
                            file_name=path.name,
                            file_sha256=sha256,
                            review_items=all_review_items,
                        )
                        all_events.extend(b_events)
                        all_aggregates.extend(b_aggs)
                        all_mentions.extend(b_mentions)
                    elif p_name and p_name.startswith("anpr"):
                        profile = load_profile(profiles_dir / f"{p_name}.yaml")
                        a_events, a_aggs, a_mentions = parse_anpr(
                            rows,
                            profile,
                            case_id=case_id,
                            doc_id=doc_id,
                            file_name=path.name,
                            file_sha256=sha256,
                            review_items=all_review_items,
                        )
                        all_events.extend(a_events)
                        all_aggregates.extend(a_aggs)
                        all_mentions.extend(a_mentions)
                    elif p_name and p_name.startswith("tower"):
                        profile = load_profile(profiles_dir / f"{p_name}.yaml")
                        t_events, t_aggs, t_mentions = parse_tower(
                            rows,
                            profile,
                            case_id=case_id,
                            doc_id=doc_id,
                            file_name=path.name,
                            file_sha256=sha256,
                            review_items=all_review_items,
                        )
                        all_events.extend(t_events)
                        all_aggregates.extend(t_aggs)
                        all_mentions.extend(t_mentions)
                    else:
                        all_review_items.append(
                            create_mapping_unconfirmed_review(
                                case_id=case_id,
                                doc_id=doc_id,
                                headers=headers,
                                detail=f"No matching confirmed profile found for CSV headers in '{path.name}'",
                            )
                        )

                elif detected_type == "xlsx":
                    # Tabular XLSX - never goes to LLM
                    profiles_dir = Path("profiles")
                    if not profiles_dir.is_dir():
                        profiles_dir = Path(__file__).resolve().parent.parent.parent.parent / "profiles"

                    xlsx_res = read_xlsx(path, max_full_load_mb=self.settings.XLSX_FULL_LOAD_MB)
                    doc_warnings.extend(xlsx_res.get("warnings", []))
                    raw_sheets = xlsx_res.get("sheets", [])
                    total_rows = 0

                    for s_idx, sh in enumerate(raw_sheets):
                        s_name = sh.get("name", f"Sheet{s_idx + 1}")
                        s_rows = sh.get("rows", [])
                        total_rows += len(s_rows)
                        s_state_str = sh.get("state", "visible")
                        s_state = SheetState.VISIBLE
                        if s_state_str == "hidden":
                            s_state = SheetState.HIDDEN
                        elif s_state_str == "veryHidden":
                            s_state = SheetState.VERY_HIDDEN

                        sheets_info.append(
                            SheetInfo(
                                name=s_name,
                                state=s_state,
                                rows=len(s_rows),
                                merged_ranges=sh.get("merged_ranges", []),
                                formula_cells=len(sh.get("formulas", [])),
                                formula_missing_cache=0,
                            )
                        )

                        # Extract sheet headers from first row
                        if s_rows:
                            first_row_vals = s_rows[0].get("values", {})
                            sheet_headers = [str(k) for k in first_row_vals]
                            p_name = detect_profile(sheet_headers, profiles_dir)
                            if p_name and p_name.startswith("cdr"):
                                profile = load_profile(profiles_dir / f"{p_name}.yaml")
                                c_events, c_aggs, c_mentions = parse_cdr(
                                    s_rows,
                                    profile,
                                    case_id=case_id,
                                    doc_id=doc_id,
                                    file_name=path.name,
                                    file_sha256=sha256,
                                    sheet_index=s_idx,
                                    sheet_name=s_name,
                                    review_items=all_review_items,
                                )
                                all_events.extend(c_events)
                                all_aggregates.extend(c_aggs)
                                all_mentions.extend(c_mentions)
                            elif p_name and p_name.startswith("bank"):
                                profile = load_profile(profiles_dir / f"{p_name}.yaml")
                                b_events, b_aggs, b_mentions = parse_bank(
                                    s_rows,
                                    profile,
                                    case_id=case_id,
                                    doc_id=doc_id,
                                    file_name=path.name,
                                    file_sha256=sha256,
                                    sheet_index=s_idx,
                                    sheet_name=s_name,
                                    review_items=all_review_items,
                                )
                                all_events.extend(b_events)
                                all_aggregates.extend(b_aggs)
                                all_mentions.extend(b_mentions)
                            elif p_name and p_name.startswith("anpr"):
                                profile = load_profile(profiles_dir / f"{p_name}.yaml")
                                a_events, a_aggs, a_mentions = parse_anpr(
                                    s_rows,
                                    profile,
                                    case_id=case_id,
                                    doc_id=doc_id,
                                    file_name=path.name,
                                    file_sha256=sha256,
                                    sheet_index=s_idx,
                                    sheet_name=s_name,
                                    review_items=all_review_items,
                                )
                                all_events.extend(a_events)
                                all_aggregates.extend(a_aggs)
                                all_mentions.extend(a_mentions)
                            elif p_name and p_name.startswith("tower"):
                                profile = load_profile(profiles_dir / f"{p_name}.yaml")
                                t_events, t_aggs, t_mentions = parse_tower(
                                    s_rows,
                                    profile,
                                    case_id=case_id,
                                    doc_id=doc_id,
                                    file_name=path.name,
                                    file_sha256=sha256,
                                    sheet_index=s_idx,
                                    sheet_name=s_name,
                                    review_items=all_review_items,
                                )
                                all_events.extend(t_events)
                                all_aggregates.extend(t_aggs)
                                all_mentions.extend(t_mentions)
                            else:
                                all_review_items.append(
                                    create_mapping_unconfirmed_review(
                                        case_id=case_id,
                                        doc_id=doc_id,
                                        headers=sheet_headers,
                                        detail=f"No matching confirmed profile found for sheet '{s_name}' in '{path.name}'",
                                    )
                                )
                    row_count = total_rows

            except Exception as exc:
                msg = f"Extraction failed for '{path.name}': {exc}"
                doc_warnings.append(msg)
                warnings.append(msg)

            extract_duration = (time.perf_counter() - extract_start) * 1000
            trace_entries.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "stage": "extraction",
                    "duration_ms": round(extract_duration, 2),
                    "status": "ok" if not doc_warnings else "completed_with_warnings",
                    "case_id": case_id,
                    "doc_id": doc_id,
                    "units_count": len(doc_units),
                }
            )

            doc_rec = DocumentRecord(
                doc_id=doc_id,
                file_name=path.name,
                file_sha256=sha256,
                size_bytes=path.stat().st_size,
                detected_type=detected_type,
                status=DocumentStatus.PROCESSED if not doc_warnings else DocumentStatus.PARTIAL,
                pages=pages_info,
                row_count=row_count,
                sheets=sheets_info if sheets_info else None,
                chunk_failures=[],
                warnings=doc_warnings,
                case_id=case_id,
            )
            documents.append(doc_rec)

            # Stage 3: LLM Extraction & Provenance (Narrative units only)
            if doc_units:
                llm_start = time.perf_counter()
                chunks = chunk_units(doc_units, max_chars=self.settings.LLM_CHUNK_CHARS)
                doc_chunk_mentions: list[Mention] = []
                doc_chunk_relationships: list[Relationship] = []
                doc_chunk_events: list[Event] = []

                for c_idx, chunk in enumerate(chunks):
                    total_chunks += 1
                    chunk_id = f"{doc_id}:chunk_{c_idx}"
                    if total_llm_calls >= self.settings.MAX_LLM_CALLS_PER_RUN:
                        failed_chunks += 1
                        doc_rec.chunk_failures.append(chunk_id)
                        chunk_err_msg = (
                            f"LLM call limit reached ({self.settings.MAX_LLM_CALLS_PER_RUN}); skipping chunk {chunk_id}"
                        )
                        warnings.append(chunk_err_msg)
                        continue

                    total_llm_calls += 1
                    try:
                        system_prompt, user_prompt, _nonce = build_prompt(chunk, case_id, doc_id)
                        raw_output = execute_with_retry(
                            active_client,
                            system=system_prompt,
                            user=user_prompt,
                            max_attempts=self.settings.LLM_MAX_ATTEMPTS,
                        )

                        m_list, r_list, e_list, rev_list, rej_list = verify_model_output(
                            model_output=raw_output,
                            chunk_units=chunk,
                            case_id=case_id,
                            doc_id=doc_id,
                            file_name=path.name,
                            file_sha256=sha256,
                        )

                        doc_chunk_mentions.extend(m_list)
                        doc_chunk_relationships.extend(r_list)
                        doc_chunk_events.extend(e_list)
                        all_review_items.extend(rev_list)
                        all_rejections.extend(rej_list)

                    except Exception as exc:
                        failed_chunks += 1
                        doc_rec.chunk_failures.append(chunk_id)
                        chunk_err_msg = f"LLM extraction failed for chunk {chunk_id}: {exc}"
                        warnings.append(chunk_err_msg)
                        all_review_items.append(
                            ReviewItem(
                                review_id=make_review_id(case_id, ReviewKind.CHUNK_FAILED.value, chunk_id),
                                case_id=case_id,
                                kind=ReviewKind.CHUNK_FAILED,
                                target_ids=[chunk_id],
                                detail=chunk_err_msg,
                                status=ReviewItemStatus.OPEN,
                            )
                        )

                llm_duration = (time.perf_counter() - llm_start) * 1000
                trace_entries.append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "stage": "llm_extraction",
                        "duration_ms": round(llm_duration, 2),
                        "status": "ok" if not doc_rec.chunk_failures else "completed_with_warnings",
                        "case_id": case_id,
                        "doc_id": doc_id,
                        "mentions_count": len(doc_chunk_mentions),
                    }
                )

                # Stage 4: Within-Document Consolidation
                within_doc_start = time.perf_counter()
                d_men, d_rel, d_ev, _clusters, d_rev = consolidate_within_doc(
                    mentions=doc_chunk_mentions,
                    relationships=doc_chunk_relationships,
                    events=doc_chunk_events,
                    case_id=case_id,
                    doc_id=doc_id,
                )
                all_mentions.extend(d_men)
                all_relationships.extend(d_rel)
                all_events.extend(d_ev)
                all_review_items.extend(d_rev)

                within_doc_duration = (time.perf_counter() - within_doc_start) * 1000
                trace_entries.append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "stage": "within_doc_consolidation",
                        "duration_ms": round(within_doc_duration, 2),
                        "status": "ok",
                        "case_id": case_id,
                        "doc_id": doc_id,
                        "mentions_count": len(d_men),
                    }
                )

        # Stage 5: Within-Case Consolidation
        within_case_start = time.perf_counter()
        c_men, c_rel, c_ev, c_agg, c_rev = consolidate_within_case(
            doc_results=documents,
            case_id=case_id,
            mentions=all_mentions,
            relationships=all_relationships,
            events=all_events,
            aggregates=all_aggregates,
            review_items=all_review_items,
        )
        within_case_duration = (time.perf_counter() - within_case_start) * 1000
        trace_entries.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "stage": "within_case_consolidation",
                "duration_ms": round(within_case_duration, 2),
                "status": "ok",
                "case_id": case_id,
                "mentions_count": len(c_men),
                "relationships_count": len(c_rel),
                "events_count": len(c_ev),
                "aggregates_count": len(c_agg),
                "review_items_count": len(c_rev),
            }
        )

        # Determine JobState
        state = compute_job_state(
            chunks_total=total_chunks,
            chunks_failed=failed_chunks,
            review_items_count=len(c_rev),
            rejections_count=len(all_rejections),
            warnings_count=len(warnings),
            input_refused=input_refused,
            validation_failed=False,
        )

        # Compute deterministic idempotency key
        doc_shas = sorted(doc.file_sha256 for doc in documents if doc.file_sha256)
        combined_file_sha = (
            doc_shas[0]
            if len(doc_shas) == 1
            else hashlib.sha256("+".join(doc_shas).encode("utf-8")).hexdigest()
            if doc_shas
            else "0" * 64
        )

        idempotency_key = make_idempotency_key(
            file_sha256=combined_file_sha,
            pipeline_version=PIPELINE_VERSION,
            ocr_engine=self.settings.OCR_ENGINE,
            ocr_version="1.0.0",
            ocr_langs=self.settings.OCR_LANGS,
            provider=active_provider,
            model=active_model,
            prompt_version=active_prompt_ver,
            schema_version=SCHEMA_VERSION,
            normalization_version=NORMALIZATION_VERSION,
        )

        finished_at = datetime.now(UTC).isoformat()
        run_meta = RunMeta(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            pipeline_version=PIPELINE_VERSION,
            schema_version=SCHEMA_VERSION,
            prompt_version=active_prompt_ver,
            provider=active_provider,
            model=active_model,
            temperature=self.settings.LLM_TEMPERATURE,
            ocr_engine=self.settings.OCR_ENGINE,
            ocr_version="1.0.0",
            ocr_langs=[self.settings.OCR_LANGS],
            normalization_version=NORMALIZATION_VERSION,
            resolver_version=RESOLVER_VERSION,
            idempotency_key=idempotency_key,
        )

        # Stage 6: Build CaseResult & Write Outputs
        try:
            case_result = CaseResult(
                schema_version=SCHEMA_VERSION,
                case_id=case_id,
                run=run_meta,
                state=state,
                documents=documents,
                mentions=c_men,
                relationships=c_rel,
                events=c_ev,
                aggregates=c_agg,
                review_items=c_rev,
                rejections=all_rejections,
                warnings=warnings,
            )
        except (ValidationError, ValueError) as v_err:
            # Final CaseResult fails Pydantic validation -> failed_validation
            validation_state = JobState.FAILED_VALIDATION
            case_result = CaseResult.model_construct(
                schema_version=SCHEMA_VERSION,
                case_id=case_id,
                run=run_meta,
                state=validation_state,
                documents=documents,
                mentions=[],
                relationships=[],
                events=[],
                aggregates=[],
                review_items=c_rev,
                rejections=all_rejections,
                warnings=[*warnings, f"Validation error: {v_err}"],
            )

        write_start = time.perf_counter()
        self.output_writer.write_all(
            case_result=case_result,
            trace_entries=trace_entries,
            receipts=doc_receipts,
            output_dir=output_dir,
        )
        write_duration = (time.perf_counter() - write_start) * 1000
        trace_entries.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "stage": "output_writing",
                "duration_ms": round(write_duration, 2),
                "status": "ok",
                "case_id": case_id,
                "run_id": run_id,
            }
        )

        return case_result


__all__ = ["PipelineRunner"]
