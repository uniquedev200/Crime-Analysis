"""Development/testing web UI for ATLAS Dev 3.

A deliberately small, dependency-free page for uploading a document and inspecting
the extracted entities and their connections. It does not require the API auth
layer, so any case_id can be used for ad-hoc testing.

Endpoints:
- GET  /                  -> the single-page UI
- GET  /ui/config         -> available providers + enum values (nothing hardcoded client-side)
- POST /ui/run            -> multipart upload -> run pipeline -> entities/connections/graph JSON
- GET  /ui/runs/{case_id}/{run_id}/{artifact} -> download a run artifact file (result.json, ...)

The mock-provider honesty banner is enforced in the UI when ``provider == "mock"``.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import SecretStr

from atlas.config import AtlasSettings, get_settings
from atlas.contracts.enums import EntityType, EventType, RelType
from atlas.contracts.ids import validate_case_id
from atlas.errors import ConfigError, RejectedInputError
from atlas.ingest.synthetic_guard import register_synthetic_files
from atlas.output.graph_payload import build_graph_payload
from atlas.pipeline.runner import PipelineRunner

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "ui.html"

_MOCK_BANNER = "SCRIPTED MOCK PROVIDER: not live extraction"

# Providers understood by the factory, in the order they are offered.
_PROVIDER_ORDER: tuple[str, ...] = ("mock", "groq", "openai", "gemini")

_READ_BLOCK_BYTES = 1024 * 1024

# Run artifacts that may be downloaded by name. The map is the allow-list: any
# other name is refused, so the route can never read an arbitrary file.
_ARTIFACT_MEDIA_TYPES: dict[str, str] = {
    "result.json": "application/json",
    "review_queue.json": "application/json",
    "receipt.json": "application/json",
    "events.jsonl": "application/x-ndjson",
    "trace.jsonl": "application/x-ndjson",
}

# Run ids are produced by atlas.contracts.ids.make_run_id: RUN-YYYYMMDDTHHMMSSZ-<6 hex>.
_RUN_ID_PATTERN = re.compile(r"^RUN-\d{8}T\d{6}Z-[0-9a-f]{6}$")


def _has_secret(value: SecretStr | None) -> bool:
    """Return True when a provider secret is present and non-blank."""
    return bool(value and value.get_secret_value().strip())


def available_providers(settings: AtlasSettings | None = None) -> list[str]:
    """List LLM providers the operator allows in the UI.

    ``LLM_PROVIDERS_ENABLED`` (comma-separated) is the allow-list and wins when set;
    when it is empty every provider whose credentials are configured is offered. If an
    allow-list names nothing usable we fall back to the configured ``LLM_PROVIDER`` so
    the page can never end up offering a provider the server would refuse.
    """
    cfg = settings or get_settings()
    usable = {
        "mock": True,
        "groq": _has_secret(cfg.GROQ_API_KEY) or _has_secret(cfg.OPENAI_API_KEY),
        "openai": _has_secret(cfg.OPENAI_API_KEY),
        "gemini": _has_secret(cfg.GEMINI_API_KEY),
    }
    active = cfg.LLM_PROVIDER.lower().strip()
    allow = {item.strip().lower() for item in (cfg.LLM_PROVIDERS_ENABLED or "").split(",") if item.strip()}

    if allow:
        enabled = [name for name in _PROVIDER_ORDER if name in allow and usable[name]]
        if enabled:
            return enabled
        return [active] if active else ["mock"]

    providers = [name for name in _PROVIDER_ORDER if usable[name]]
    if active and active not in providers:
        providers.insert(0, active)
    return providers or ["mock"]


def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    """Stream one upload to ``destination`` without buffering it fully in memory.

    Returns:
        int: number of bytes written, or ``-1`` when the upload exceeds ``max_bytes``
        (in which case the partial file is removed).
    """
    written = 0
    with open(destination, "wb") as handle:
        while True:
            block = upload.file.read(_READ_BLOCK_BYTES)
            if not block:
                break
            written += len(block)
            if written > max_bytes:
                handle.close()
                destination.unlink(missing_ok=True)
                return -1
            handle.write(block)
    return written


def _state_note(state: str, warnings: list[str]) -> str | None:
    """Explain a non-obvious run state in plain language (no PII, no invented values)."""
    if state == "rejected_input":
        note = "Intake rejected the upload, so no entities could be extracted. Nothing was sent to the model."
        guard = next((w for w in warnings if "Synthetic data guard" in w), None)
        if guard:
            note += (
                " The synthetic-data guard requires the file's SHA-256 to be present in the "
                "synthetic manifest. Register it with "
                "`python -m atlas register-synthetic <path>` or tick "
                '"register uploads as synthetic" in this page.'
            )
        return note
    if state == "failed":
        return "The run failed before extracting entities; see the warnings below."
    if state == "completed_with_warnings":
        return "Extraction completed, but items were flagged for review; see the review queue below."
    return None


@router.get("/", response_class=HTMLResponse)
def ui_page() -> HTMLResponse:
    """Serve the single-page testing UI."""
    for candidate in (_TEMPLATE_PATH, Path("src") / "atlas" / "api" / "templates" / "ui.html"):
        if candidate.is_file():
            return HTMLResponse(candidate.read_text(encoding="utf-8"))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="UI template not found")


@router.get("/ui/config")
def ui_config() -> dict[str, Any]:
    """Expose providers, schema enums and downloadable artifact names (nothing hardcoded client-side)."""
    cfg = get_settings()
    active = cfg.LLM_PROVIDER.lower().strip()
    providers = available_providers(cfg)
    return {
        "providers": providers,
        "active_provider": active if active in providers else providers[0],
        "is_mock": active == "mock",
        "mock_banner": _MOCK_BANNER,
        "synthetic_only": cfg.ATLAS_SYNTHETIC_ONLY,
        "max_file_mb": cfg.MAX_FILE_MB,
        "entity_types": [e.value for e in EntityType],
        "relationship_types": [r.value for r in RelType],
        "event_types": [e.value for e in EventType],
        "artifacts": sorted(_ARTIFACT_MEDIA_TYPES),
        "state": "available",
    }


def _resolve_artifact(case_id: str, run_id: str, artifact: str) -> Path:
    """Return the on-disk path of a named run artifact, or raise a 400/404.

    Defence in depth before touching the filesystem: the case id is contract-validated,
    the run id must match the generated format, the artifact name must be on the
    allow-list, and the resolved path must stay inside the configured output directory.
    """
    try:
        validate_case_id(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid case_id: {exc}") from exc

    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid run_id: {run_id!r}")

    if artifact not in _ARTIFACT_MEDIA_TYPES:
        available = ", ".join(sorted(_ARTIFACT_MEDIA_TYPES))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown artifact {artifact!r}. Available artifacts: {available}.",
        )

    output_dir = Path(get_settings().OUTPUT_DIR).resolve()
    path = (output_dir / case_id / run_id / artifact).resolve()
    if not path.is_relative_to(output_dir) or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return path


@router.get("/ui/runs/{case_id}/{run_id}/{artifact}", response_class=FileResponse)
def ui_download_artifact(case_id: str, run_id: str, artifact: str) -> FileResponse:
    """Download one artifact written by the pipeline for a run, as a file attachment."""
    path = _resolve_artifact(case_id, run_id, artifact)
    return FileResponse(
        path,
        media_type=_ARTIFACT_MEDIA_TYPES[artifact],
        filename=f"{case_id}_{run_id}_{artifact}",
    )


@router.post("/ui/run")
def ui_run(
    case_id: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    provider: Annotated[str, Form()] = "",
    register_synthetic: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    """Run the pipeline synchronously on uploaded files and return extraction + graph JSON."""
    try:
        validate_case_id(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid case_id: {exc}") from exc

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")

    cfg = get_settings()
    allowed = available_providers(cfg)
    requested = (provider or cfg.LLM_PROVIDER).lower().strip()
    if requested not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{requested}' is not enabled. Allowed providers: {', '.join(allowed)}.",
        )

    max_bytes = cfg.MAX_FILE_MB * 1024 * 1024
    manifest_path = Path(cfg.DATA_DIR) / "synthetic_manifest.json"

    upload_warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="atlas_ui_") as tmp:
        tmp_dir = Path(tmp)
        saved_paths: list[Path] = []
        for upload in files:
            raw_name = Path(upload.filename or "upload").name
            destination = tmp_dir / raw_name
            written = _save_upload(upload, destination, max_bytes)
            if written < 0:
                upload_warnings.append(f"'{raw_name}' exceeds the {cfg.MAX_FILE_MB}MB limit and was skipped")
                continue
            if written == 0:
                upload_warnings.append(f"'{raw_name}' is empty and was skipped")
                continue
            saved_paths.append(destination)

        if not saved_paths:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No usable files uploaded (all were empty or over the size limit)",
            )

        if register_synthetic and cfg.ATLAS_SYNTHETIC_ONLY:
            registered = register_synthetic_files(saved_paths, manifest_path)
            upload_warnings.append(f"Registered {registered} uploaded file(s) as synthetic in '{manifest_path.name}'.")

        runner = PipelineRunner(settings=cfg)
        try:
            result = runner.run(case_id=case_id, file_paths=saved_paths, provider=requested)
        except (ConfigError, RejectedInputError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive: surface a safe message
            logger.exception("UI run failed for case %s", case_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Pipeline failed with {type(exc).__name__}; see the server console for details.",
            ) from exc

    graph = build_graph_payload(
        case_id=case_id,
        mentions=result.mentions,
        relationships=result.relationships,
        events=result.events,
    )

    is_mock = result.run.provider.lower() == "mock"
    state = result.state.value if hasattr(result.state, "value") else str(result.state)
    warnings = [*upload_warnings, *result.warnings]
    return {
        "state": state,
        "state_note": _state_note(state, warnings),
        "case_id": result.case_id,
        "run_id": result.run.run_id,
        "provider": result.run.provider,
        "model": result.run.model,
        "is_mock": is_mock,
        "mock_banner": _MOCK_BANNER if is_mock else None,
        "documents": [d.model_dump(mode="json") for d in result.documents],
        "mentions": [m.model_dump(mode="json") for m in result.mentions],
        "relationships": [r.model_dump(mode="json") for r in result.relationships],
        "events": [e.model_dump(mode="json") for e in result.events],
        "review_items": [r.model_dump(mode="json") for r in result.review_items],
        "rejections": [r.model_dump(mode="json") for r in result.rejections],
        "warnings": warnings,
        "graph": graph,
    }


__all__ = ["available_providers", "router"]
