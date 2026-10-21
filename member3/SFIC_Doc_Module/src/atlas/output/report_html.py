"""HTML report generator for ATLAS Dev 3 case investigation evidence.

Renders a standalone, self-contained, interactive HTML evidence report
with strict XSS auto-escaping, case boundary isolation, mock provider honesty banner,
side-by-side document and fact viewer with verified quote highlighting, OCR uncertainty
routing, cross-case candidate suggestions, and cryptographic audit trail.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from atlas.contracts.records import CaseResult, Mention, ResolutionSuggestion, ReviewAction


def highlight_quotes_in_text(raw_text: str, quotes: list[str]) -> str:
    """Safely escape text and highlight verbatim quotes using HTML <mark> tags.

    Both raw text and quotes are escaped first, preventing any script injection
    or XSS attack from untrusted document content.
    """
    escaped_text = html.escape(raw_text)

    # Sort quotes by descending length so longer quotes are matched before substrings
    unique_quotes = sorted({q.strip() for q in quotes if q and q.strip()}, key=len, reverse=True)

    for q in unique_quotes:
        escaped_q = html.escape(q)
        if escaped_q in escaped_text:
            # Case-sensitive exact replacement with safe mark tag
            pattern = re.escape(escaped_q)
            escaped_text = re.sub(
                pattern,
                f'<mark class="quote-highlight">{escaped_q}</mark>',
                escaped_text,
                count=1,
            )

    return escaped_text


def _resolve_document_text(
    doc_id: str,
    file_name: str,
    file_sha256: str,
    raw_texts: dict[str, str | dict[int, str]] | None,
    data_dir: Path | str | None,
    quotes: list[str],
) -> str:
    """Retrieve or synthesize raw document text for the document viewer."""
    if raw_texts:
        # Check by doc_id or file_name
        if doc_id in raw_texts:
            val = raw_texts[doc_id]
            if isinstance(val, dict):
                return "\n\n--- Next Page ---\n\n".join(val[p] for p in sorted(val.keys()))
            return str(val)
        if file_name in raw_texts:
            val = raw_texts[file_name]
            if isinstance(val, dict):
                return "\n\n--- Next Page ---\n\n".join(val[p] for p in sorted(val.keys()))
            return str(val)

    # Check data_dir originals
    if data_dir is not None:
        orig_path = Path(data_dir) / "originals" / file_sha256
        if orig_path.is_file():
            try:
                # Text files can be read directly
                if file_name.endswith((".txt", ".json", ".csv")):
                    return orig_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

    # Fallback: synthesize readable view from verified quotes
    if quotes:
        excerpts = [f"[Page excerpt / quote {i + 1}]: {q}" for i, q in enumerate(quotes)]
        return "\n\n".join(excerpts)

    return f"[Document {file_name} ({doc_id}) — text content preserved in content-addressed store]"


def render_report_html(
    case_result: CaseResult,
    suggestions: list[ResolutionSuggestion] | None = None,
    audit_entries: list[dict[str, Any]] | list[ReviewAction] | None = None,
    raw_texts: dict[str, str | dict[int, str]] | None = None,
    data_dir: Path | str | None = None,
) -> str:
    """Generate self-contained HTML report string for a completed or warned case result.

    Enforces:
    1. Case isolation: foreign case data is strictly filtered out.
    2. Mock honesty: prominently flags mock provider.
    3. XSS escaping: all dynamic fields are escaped via Jinja2 autoescape.
    4. Side-by-side raw text and verified fact alignment.
    """
    current_case_id = case_result.case_id

    # 1. Filter mentions, relationships, events, review items for strict case isolation
    mentions: list[Mention] = [m for m in case_result.mentions if m.case_id == current_case_id]
    relationships = [r for r in case_result.relationships if r.case_id == current_case_id]
    events = [e for e in case_result.events if e.case_id == current_case_id]
    review_items = [rv for rv in case_result.review_items if rv.case_id == current_case_id]
    documents = [d for d in case_result.documents if d.case_id is None or d.case_id == current_case_id]

    # Map mentions by document ID
    doc_mentions: dict[str, list[Mention]] = {d.doc_id: [] for d in documents}
    doc_quotes: dict[str, list[str]] = {d.doc_id: [] for d in documents}

    for m in mentions:
        d_id = m.doc_id
        if d_id in doc_mentions:
            doc_mentions[d_id].append(m)
        else:
            doc_mentions[d_id] = [m]

        if m.source and m.source.quote:
            if d_id not in doc_quotes:
                doc_quotes[d_id] = []
            doc_quotes[d_id].append(m.source.quote)

    # Prepare rendered text per document with highlighted quotes
    doc_rendered_texts: dict[str, str] = {}
    for doc in documents:
        raw = _resolve_document_text(
            doc_id=doc.doc_id,
            file_name=doc.file_name,
            file_sha256=doc.file_sha256,
            raw_texts=raw_texts,
            data_dir=data_dir,
            quotes=doc_quotes.get(doc.doc_id, []),
        )
        highlighted = highlight_quotes_in_text(raw, doc_quotes.get(doc.doc_id, []))
        doc_rendered_texts[doc.doc_id] = highlighted

    # 2. Filter cross-case suggestions (must belong to this case)
    filtered_suggestions: list[ResolutionSuggestion] = []
    if suggestions:
        for s in suggestions:
            if s.case_id == current_case_id:
                filtered_suggestions.append(s)

    # 3. Format audit entries
    formatted_audit: list[dict[str, Any]] = []
    if audit_entries:
        for entry in audit_entries:
            if isinstance(entry, ReviewAction):
                c_id = entry.case_id
                if c_id is None or c_id == current_case_id:
                    formatted_audit.append(
                        {
                            "action_id": entry.action_id,
                            "actor": entry.actor,
                            "type": entry.type.value if hasattr(entry.type, "value") else str(entry.type),
                            "at": entry.at,
                            "reason": entry.reason,
                            "target_ids": entry.target_ids,
                            "entry_hash": entry.entry_hash,
                            "prev_hash": entry.prev_hash,
                        }
                    )
            elif isinstance(entry, dict):
                c_id = entry.get("case_id")
                if c_id is None or c_id == current_case_id:
                    act_type = entry.get("type", "")
                    if hasattr(act_type, "value"):
                        act_type = act_type.value
                    formatted_audit.append(
                        {
                            "action_id": entry.get("action_id", ""),
                            "actor": entry.get("actor", ""),
                            "type": str(act_type),
                            "at": entry.get("at", ""),
                            "reason": entry.get("reason", ""),
                            "target_ids": entry.get("target_ids", []),
                            "entry_hash": entry.get("entry_hash", ""),
                            "prev_hash": entry.get("prev_hash", ""),
                        }
                    )

    # 4. Setup Jinja2 environment with strict HTML autoescaping
    template_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("report.html.j2")

    is_mock = case_result.run.provider.lower() == "mock"
    ocr_langs_display = (
        ", ".join(case_result.run.ocr_langs)
        if isinstance(case_result.run.ocr_langs, list)
        else str(case_result.run.ocr_langs)
    )

    rendered_html = template.render(
        case_id=case_result.case_id,
        run_id=case_result.run.run_id,
        is_mock=is_mock,
        job_state=case_result.state.value if hasattr(case_result.state, "value") else str(case_result.state),
        started_at=case_result.run.started_at,
        pipeline_version=case_result.run.pipeline_version,
        provider=case_result.run.provider,
        model=case_result.run.model,
        ocr_engine=case_result.run.ocr_engine,
        ocr_langs=ocr_langs_display,
        idempotency_key=case_result.run.idempotency_key,
        documents=documents,
        mentions=mentions,
        relationships=relationships,
        events=events,
        review_items=review_items,
        doc_mentions=doc_mentions,
        doc_rendered_texts=doc_rendered_texts,
        suggestions=filtered_suggestions,
        audit_entries=formatted_audit,
    )

    return rendered_html


def generate_report_html(
    case_result: CaseResult,
    suggestions: list[ResolutionSuggestion] | None = None,
    audit_entries: list[dict[str, Any]] | list[ReviewAction] | None = None,
    raw_texts: dict[str, str | dict[int, str]] | None = None,
    data_dir: Path | str | None = None,
) -> str:
    """Alias for render_report_html."""
    return render_report_html(
        case_result=case_result,
        suggestions=suggestions,
        audit_entries=audit_entries,
        raw_texts=raw_texts,
        data_dir=data_dir,
    )


def write_report_html(
    case_result: CaseResult,
    output_path: Path | str,
    suggestions: list[ResolutionSuggestion] | None = None,
    audit_entries: list[dict[str, Any]] | list[ReviewAction] | None = None,
    raw_texts: dict[str, str | dict[int, str]] | None = None,
    data_dir: Path | str | None = None,
) -> Path:
    """Render and write report.html to specified file path with UTF-8 encoding."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    content = render_report_html(
        case_result=case_result,
        suggestions=suggestions,
        audit_entries=audit_entries,
        raw_texts=raw_texts,
        data_dir=data_dir,
    )
    out.write_text(content, encoding="utf-8")
    return out


__all__ = ["generate_report_html", "highlight_quotes_in_text", "render_report_html", "write_report_html"]
