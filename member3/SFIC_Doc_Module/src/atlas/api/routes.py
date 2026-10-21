"""FastAPI route handlers for ATLAS Dev 3 evidence processing API.

Implements PLAN.md Section 4.7 and J4 specifications:
- POST /cases/{case_id}/documents          multipart -> {doc_id, file_sha256, state}
- POST /cases/{case_id}/jobs               {doc_ids?} -> {job_id, state}
- GET  /jobs/{job_id}                      -> {state, progress, warnings}
- GET  /cases/{case_id}/results/latest     -> CaseResult
- GET  /cases/{case_id}/review-items       -> [ReviewItem]
- GET  /cases/{case_id}/suggestions        -> [ResolutionSuggestion] (auth-filtered)
- POST /review/actions                     ReviewAction body -> updated state
- GET  /cases/{case_id}/graph              -> graph payload (+ optional cypher export)
- GET  /cases/{case_id}/evidence/{mention_id} -> SourceRef + quote + origin + OCR info
- GET  /healthz                            -> status ok, version PIPELINE_VERSION

All responses expose explicit 'state'; heuristic ranks always accompanied by rank_note.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from atlas.adapters.dev4_graph import format_for_dev4
from atlas.api.auth import User, check_case_access, get_current_user
from atlas.config import get_settings
from atlas.contracts.enums import EntityType, JobState, ReviewActionType
from atlas.contracts.ids import make_action_id, make_doc_id, make_run_id
from atlas.contracts.records import CaseResult, Mention, ResolutionSuggestion, ReviewAction, ReviewItem
from atlas.ingest.originals import store_original
from atlas.output.cypher_export import export_cypher
from atlas.output.graph_payload import build_graph_payload
from atlas.pipeline.runner import PipelineRunner
from atlas.pipeline.status import load_case_result, load_review_queue
from atlas.resolve.review import apply_review_action
from atlas.resolve.store_sqlite import SqliteEntityStore
from atlas.version import PIPELINE_VERSION

router = APIRouter()

# In-memory background jobs registry
_JOBS_REGISTRY: dict[str, dict[str, Any]] = {}

# Shared entity store instance
_STORE_INSTANCE: SqliteEntityStore | None = None


def get_entity_store() -> SqliteEntityStore:
    """Return shared SqliteEntityStore instance."""
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        db_path = Path(get_settings().DATA_DIR) / "entity_store.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _STORE_INSTANCE = SqliteEntityStore(db_path)
    return _STORE_INSTANCE


# Request / Response Schemas


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str
    file_sha256: str
    state: str = "queued"


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_ids: list[str] | None = None
    file_paths: list[str] | None = None


class JobCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    state: JobState = JobState.QUEUED


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    state: JobState
    progress: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class ReviewActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str | None = None
    type: ReviewActionType
    actor: str | None = None
    at: str | None = None
    reason: str
    target_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    prev_hash: str | None = None
    entry_hash: str | None = None
    case_id: str | None = None


def _run_background_pipeline_job(
    job_id: str,
    case_id: str,
    file_paths: list[str],
) -> None:
    """Execute pipeline runner as a background task, updating job status."""
    if job_id not in _JOBS_REGISTRY:
        return

    _JOBS_REGISTRY[job_id]["state"] = JobState.RUNNING
    _JOBS_REGISTRY[job_id]["progress"] = 0.3

    try:
        runner = PipelineRunner()
        result = runner.run(case_id=case_id, file_paths=file_paths)
        _JOBS_REGISTRY[job_id]["state"] = result.state
        _JOBS_REGISTRY[job_id]["progress"] = 1.0
        _JOBS_REGISTRY[job_id]["warnings"] = result.warnings
        _JOBS_REGISTRY[job_id]["run_id"] = result.run.run_id

        # Populate SQLite store with mentions for candidate queries and evidence retrieval
        store = get_entity_store()
        store.store_mentions(case_id, result.mentions)

    except Exception as e:
        _JOBS_REGISTRY[job_id]["state"] = JobState.FAILED
        _JOBS_REGISTRY[job_id]["progress"] = 1.0
        _JOBS_REGISTRY[job_id]["warnings"].append(str(e))


# 1. POST /cases/{case_id}/documents
@router.post(
    "/cases/{case_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    case_id: str,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
) -> DocumentUploadResponse:
    """Intake multipart evidence document, compute content-addressed SHA-256 and store original."""
    check_case_access(case_id, user)

    content = await file.read()
    settings = get_settings()

    max_bytes = settings.MAX_FILE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds size limit of {settings.MAX_FILE_MB}MB",
        )

    sha256 = hashlib.sha256(content).hexdigest().lower()
    data_dir_path = Path(settings.DATA_DIR)
    target_path = data_dir_path / "originals" / sha256
    if not target_path.exists():
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            store_original(tmp_path, sha256, data_dir_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    doc_id = make_doc_id(sha256)
    return DocumentUploadResponse(
        doc_id=doc_id,
        file_sha256=sha256,
        state="queued",
    )


# 2. POST /cases/{case_id}/jobs
@router.post(
    "/cases/{case_id}/jobs",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job(
    case_id: str,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    request: JobCreateRequest | None = None,
) -> JobCreateResponse:
    """Launch evidence processing pipeline job for a case in the background."""
    check_case_access(case_id, user)

    job_id = f"JOB-{make_run_id()}"
    settings = get_settings()

    file_paths: list[str] = []
    if request and request.file_paths:
        file_paths.extend(request.file_paths)
    elif request and request.doc_ids:
        # Locate files in data/originals
        orig_dir = Path(settings.DATA_DIR) / "originals"
        for doc_id in request.doc_ids:
            prefix = doc_id.removeprefix("DOC-").lower()
            if orig_dir.is_dir():
                matches = list(orig_dir.glob(f"{prefix}*"))
                if matches:
                    file_paths.append(str(matches[0]))
    else:
        # Process all originals if none specified
        orig_dir = Path(settings.DATA_DIR) / "originals"
        if orig_dir.is_dir():
            file_paths = [str(p) for p in orig_dir.iterdir() if p.is_file()]

    _JOBS_REGISTRY[job_id] = {
        "job_id": job_id,
        "case_id": case_id,
        "state": JobState.QUEUED,
        "progress": 0.0,
        "warnings": [],
        "run_id": None,
        "created_at": datetime.now(UTC).isoformat(),
    }

    background_tasks.add_task(_run_background_pipeline_job, job_id, case_id, file_paths)

    return JobCreateResponse(
        job_id=job_id,
        state=JobState.QUEUED,
    )


# 3. GET /jobs/{job_id}
@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Retrieve execution state, progress, and warnings for a pipeline background job."""
    if job_id not in _JOBS_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    job = _JOBS_REGISTRY[job_id]
    return JobStatusResponse(
        job_id=job["job_id"],
        state=job["state"],
        progress=job["progress"],
        warnings=job["warnings"],
    )


# 4. GET /cases/{case_id}/results/latest
@router.get("/cases/{case_id}/results/latest", response_model=CaseResult)
def get_latest_results(
    case_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> CaseResult:
    """Load latest validated CaseResult output for an authorized case."""
    check_case_access(case_id, user)

    result = load_case_result(case_id, output_dir=get_settings().OUTPUT_DIR)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No results found for case '{case_id}'",
        )
    return result


# 5. GET /cases/{case_id}/review-items
@router.get("/cases/{case_id}/review-items", response_model=list[ReviewItem])
def get_case_review_items(
    case_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> list[ReviewItem]:
    """Retrieve list of actionable review queue items for an authorized case."""
    check_case_access(case_id, user)

    items = load_review_queue(case_id, output_dir=get_settings().OUTPUT_DIR)
    if not items:
        # Fallback to loading latest CaseResult
        result = load_case_result(case_id, output_dir=get_settings().OUTPUT_DIR)
        if result:
            items = list(result.review_items)
    return items


# 6. GET /cases/{case_id}/suggestions
@router.get("/cases/{case_id}/suggestions", response_model=list[ResolutionSuggestion])
def get_case_suggestions(
    case_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> list[ResolutionSuggestion]:
    """Retrieve authorization-filtered cross-case resolution suggestions."""
    check_case_access(case_id, user)

    store = get_entity_store()
    raw_suggestions = store.get_suggestions(case_id, auth={"allowed_cases": user.allowed_cases})

    suggestions: list[ResolutionSuggestion] = []
    for s in raw_suggestions:
        # Strip candidate_case_id if not authorized
        cand_case = s.get("candidate_case_id")
        if cand_case and cand_case not in user.allowed_cases:
            s["candidate_case_id"] = None
        s_copy = dict(s)
        s_copy.pop("created_at", None)
        suggestions.append(ResolutionSuggestion.model_validate(s_copy))

    return suggestions


# 7. POST /review/actions
@router.post("/review/actions")
def submit_review_action(
    action_in: ReviewActionInput,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Apply an audited, hash-chained review decision performed by an authorized human."""
    if action_in.case_id:
        check_case_access(action_in.case_id, user)

    store = get_entity_store()

    # Build validated ReviewAction model
    action_id = action_in.action_id or make_action_id()
    actor = action_in.actor or user.name
    at_str = action_in.at or datetime.now(UTC).isoformat()
    prev_hash = action_in.prev_hash or store.get_latest_audit_hash()
    entry_hash = action_in.entry_hash or ""

    action = ReviewAction(
        action_id=action_id,
        type=action_in.type,
        actor=actor,
        at=at_str,
        reason=action_in.reason,
        target_ids=action_in.target_ids,
        payload=action_in.payload,
        before_state=action_in.before_state,
        after_state=action_in.after_state,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        case_id=action_in.case_id,
    )

    success, msg = apply_review_action(store, action, auth={"allowed_cases": user.allowed_cases})
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Review action rejected: {msg}",
        )

    return {
        "state": "applied",
        "success": True,
        "action_id": action.action_id,
        "message": msg,
    }


# 8. GET /cases/{case_id}/graph
@router.get("/cases/{case_id}/graph")
def get_case_graph(
    case_id: str,
    user: Annotated[User, Depends(get_current_user)],
    format: Annotated[str, Query(description="Dev 4 graph schema format")] = "generic",
    export_cypher_flag: Annotated[bool, Query(alias="export_cypher", description="Include Cypher script")] = False,
) -> dict[str, Any]:
    """Generate graph payload and optional Neo4j Cypher script for an authorized case."""
    check_case_access(case_id, user)

    result = load_case_result(case_id, output_dir=get_settings().OUTPUT_DIR)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No results found for case '{case_id}'",
        )

    store = get_entity_store()
    raw_suggestions = store.get_suggestions(case_id, auth={"allowed_cases": user.allowed_cases})
    suggestions = []
    for s in raw_suggestions:
        s_copy = dict(s)
        s_copy.pop("created_at", None)
        suggestions.append(ResolutionSuggestion.model_validate(s_copy))
    approved_merges = store.get_merge_links(case_id=case_id)

    payload = build_graph_payload(
        case_id=case_id,
        mentions=result.mentions,
        relationships=result.relationships,
        events=result.events,
        suggestions=suggestions,
        approved_merges=approved_merges,
    )

    formatted = format_for_dev4(payload, format_name=format)

    if export_cypher_flag:
        cypher_script = export_cypher(payload)
        formatted["cypher"] = cypher_script

    return formatted


# 9. GET /cases/{case_id}/evidence/{mention_id}
@router.get("/cases/{case_id}/evidence/{mention_id}")
def get_evidence_mention(
    case_id: str,
    mention_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Retrieve verbatim quote, computed transcript location, origin, and OCR scoring for a mention."""
    check_case_access(case_id, user)

    target_mention: Mention | None = None

    # 1. Search latest case result
    result = load_case_result(case_id, output_dir=get_settings().OUTPUT_DIR)
    if result:
        for m in result.mentions:
            if m.mention_id == mention_id:
                target_mention = m
                break

    # 2. Fallback to SQLite store mentions table
    if target_mention is None:
        store = get_entity_store()
        cursor = store._conn.cursor()
        cursor.execute(
            "SELECT data_json FROM mentions WHERE mention_id = ? AND case_id = ?",
            (mention_id, case_id),
        )
        row = cursor.fetchone()
        if row:
            with contextlib.suppress(Exception):
                target_mention = Mention.model_validate(json.loads(row["data_json"]))

    if target_mention is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence mention '{mention_id}' not found in case '{case_id}'",
        )

    # Allowed actions
    allowed_actions = []
    if target_mention.type in (EntityType.PHONE, EntityType.IMEI, EntityType.VEHICLE, EntityType.ACCOUNT):
        allowed_actions = ["CONFIRM_IDENTIFIER", "CORRECT_IDENTIFIER"]

    return {
        "mention_id": target_mention.mention_id,
        "case_id": target_mention.case_id,
        "doc_id": target_mention.doc_id,
        "type": target_mention.type.value if hasattr(target_mention.type, "value") else str(target_mention.type),
        "surface_text": target_mention.surface_text,
        "normalized_value": target_mention.normalized_value,
        "normalization_status": (
            target_mention.normalization_status.value
            if hasattr(target_mention.normalization_status, "value")
            else str(target_mention.normalization_status)
        ),
        "origin": target_mention.origin.value
        if hasattr(target_mention.origin, "value")
        else str(target_mention.origin),
        "ocr": target_mention.ocr.model_dump(mode="json") if target_mention.ocr else None,
        "identifier_trust": (
            target_mention.identifier_trust.value
            if hasattr(target_mention.identifier_trust, "value")
            else str(target_mention.identifier_trust)
        ),
        "confirmed_by": target_mention.confirmed_by,
        "quote": target_mention.source.quote,
        "quote_status": (
            target_mention.source.quote_status.value
            if hasattr(target_mention.source.quote_status, "value")
            else str(target_mention.source.quote_status)
        ),
        "source": target_mention.source.model_dump(mode="json"),
        "review_flags": [f.value if hasattr(f, "value") else str(f) for f in target_mention.review_flags],
        "attributes": [a.model_dump(mode="json") for a in target_mention.attributes],
        "state": "available",
        "allowed_actions": allowed_actions,
    }


# 10. GET /healthz
@router.get("/healthz")
def healthz() -> dict[str, Any]:
    """Service liveness and readiness probe."""
    return {
        "status": "ok",
        "version": PIPELINE_VERSION,
        "state": "healthy",
    }


__all__ = ["get_entity_store", "router"]
