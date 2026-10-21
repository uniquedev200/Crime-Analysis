"""
app.py

AI-Powered Criminal Investigation Copilot — Stage 4 Streamlit Interface
Member 5: AI-Assisted Search and Investigation Reporting

Features:
- Strict case isolation across all searches, timelines, and AI queries.
- Deterministic Python metrics (counts, financial totals, citation coverage).
- Local Ollama Q&A using qwen2.5:3b (no external APIs).
- Privacy protection with sensitive contact details hidden/redacted.
- Clear 4-section structured AI investigation reporting.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evidence_search import (
    calculate_case_metrics,
    format_evidence_citation,
    get_citation_metadata,
    load_and_normalize_records,
    sort_records_chronologically,
)
from src.investigation_assistant import (
    answer_question,
    check_ollama_availability,
    sanitize_pii_for_prompt,
)
from src.ui_helpers import (
    filter_case_evidence,
    format_citation_card,
    get_available_cases,
    get_record_types_for_case,
    load_dataset_metadata,
    parse_uploaded_json,
)

# Page configuration
st.set_page_config(
    page_title="Criminal Investigation Copilot",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_PATH = PROJECT_ROOT / "data" / "mock_investigation_data.json"


@st.cache_data
def get_cached_records() -> List[Dict[str, Any]]:
    """Load and normalize investigation records from the mock JSON dataset."""
    return load_and_normalize_records(DATA_PATH)


@st.cache_data
def get_cached_metadata() -> Dict[str, Any]:
    """Load top-level dataset metadata and mock flags."""
    return load_dataset_metadata(DATA_PATH)


def main() -> None:
    # -------------------------------------------------------------
    # SIDEBAR: Data Source, Case Selection, System Status, & Safety
    # -------------------------------------------------------------
    st.sidebar.title("⚖️ Investigation Copilot")
    st.sidebar.markdown(
        "**Member 5 — AI-Assisted Search & Investigation Reporting**"
    )
    st.sidebar.divider()

    # Data Source Selection (Default Mock vs. Uploaded JSON)
    st.sidebar.subheader("📂 Case Data Source")
    data_source_mode = st.sidebar.radio(
        "Choose Data Source:",
        options=["Default Investigation Dataset", "Upload Custom JSON File"],
        index=0,
        help="Analyze the project's standard dataset or upload your own case JSON file.",
    )

    records: List[Dict[str, Any]] = []
    dataset_meta: Dict[str, Any] = {}
    source_label = "Default Mock Dataset"
    upload_errors: List[str] = []
    upload_warnings: List[str] = []

    if data_source_mode == "Upload Custom JSON File":
        uploaded_file = st.sidebar.file_uploader(
            "Upload Case JSON File:",
            type=["json"],
            help="Upload a UTF-8 JSON file containing cases or records. All processing occurs locally on your Mac.",
        )
        if uploaded_file is not None:
            source_label = f"Uploaded File: {uploaded_file.name}"
            payload = uploaded_file.getvalue()
            records, dataset_meta, upload_errors, upload_warnings = parse_uploaded_json(payload)
            if upload_errors:
                for err in upload_errors:
                    st.sidebar.error(f"❌ {err}")
                st.error("Uploaded JSON file has validation errors. Please check the sidebar notices.")
                return
            if upload_warnings:
                with st.sidebar.expander(f"⚠️ Dataset Notices ({len(upload_warnings)})", expanded=False):
                    for warn in upload_warnings:
                        st.caption(f"• {warn}")
        else:
            st.sidebar.info("Upload a JSON file above to inspect and query its cases.")
            st.info("📂 **Please upload an investigation JSON file in the sidebar** to start evidence analysis.")
            return
    else:
        records = get_cached_records()
        dataset_meta = get_cached_metadata()

    # Fictional Dataset Notice
    if dataset_meta.get("is_fictional_mock"):
        st.sidebar.warning(
            "⚠️ **FICTIONAL MOCK DATASET**\n\n"
            "All names, events, and records are synthetic for college project development only."
        )
    else:
        st.sidebar.success(f"📄 **Active Source**: {source_label}")

    # Ollama Health Check
    is_ollama_ready, ollama_status = check_ollama_availability()
    if is_ollama_ready:
        st.sidebar.success(f"🟢 **Local Ollama Active**\n\nModel: `qwen2.5:3b` (Offline)")
    else:
        st.sidebar.error(f"🔴 **Local Ollama Offline**\n\n{ollama_status}")

    st.sidebar.divider()

    # Case Selection
    available_cases = get_available_cases(records)
    if not available_cases:
        st.error("No case records found in the selected dataset. Please verify your JSON file structure.")
        return

    st.sidebar.subheader("📁 Case Selector")
    selected_case = st.sidebar.selectbox(
        "Select Active Case Scope:",
        options=available_cases,
        index=0,
        help="All searches, timelines, and AI queries are strictly isolated to the chosen case.",
    )

    st.sidebar.divider()
    st.sidebar.markdown(
        "### 🛡️ Core Safety Principles\n"
        "- **Case Isolation**: No cross-case record mixing.\n"
        "- **Objective Review**: Association is **not** proof of guilt.\n"
        "- **Deterministic Numbers**: Python computes counts & totals.\n"
        "- **Source Traceability**: Every fact cites records.\n"
        "- **Local Only**: Zero external cloud APIs."
    )

    # -------------------------------------------------------------
    # MAIN PANEL: Header, Metrics, & Tabs
    # -------------------------------------------------------------
    st.title(f"📁 Case Investigation Workspace: `{selected_case}`")
    case_info = dataset_meta.get("case_info")
    if case_info and case_info.get("case_id") == selected_case:
        fir_no = case_info.get("fir_number") or "Not Recorded"
        reg_date = case_info.get("registration_date") or "Not Recorded"
        st.caption(
            f"**FIR Number**: `{fir_no}` • **Registration Date**: `{reg_date}` • "
            "Operates strictly on local Ollama models with source citations."
        )
    else:
        st.caption(
            "AI-assisted evidence retrieval and investigation inquiry system. "
            "Operates strictly on local Ollama models with source citations."
        )

    # Legal / Operational Disclaimer
    st.info(
        "⚖️ **Investigation Disclaimer**: This system assists in retrieving and reviewing factual case records. "
        "It does **not** determine guilt, innocence, or legal liability. An association between people, vehicles, "
        "locations, or badge scans does not establish wrongdoing.",
        icon="ℹ️",
    )

    # Deterministic Python Metrics Bar
    case_metrics = calculate_case_metrics(records, case_id=selected_case)
    total_recs = case_metrics["total_records"]
    total_usd = case_metrics["total_amount_usd"]
    missing_pages = case_metrics["missing_citation_counts"]["missing_page_number"]
    distinct_types = len(case_metrics["record_type_breakdown"])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Total Case Records", value=total_recs)
    with col2:
        st.metric(label="Recorded USD Total", value=f"${total_usd:,.2f}")
    with col3:
        st.metric(label="Record Types", value=distinct_types)
    with col4:
        st.metric(label="Missing Page Numbers", value=missing_pages)

    earliest_dt = case_metrics.get("earliest_timestamp") or "[NOT RECORDED]"
    latest_dt = case_metrics.get("latest_timestamp") or "[NOT RECORDED]"
    st.caption(
        f"🔒 *Exact counts, totals, and timeline bounds computed deterministically in Python (never generated by LLM). "
        f"Recorded Date Span: `{earliest_dt}` to `{latest_dt}`.*"
    )
    st.divider()

    # Workspace Tabs
    tab_search, tab_ai, tab_timeline = st.tabs([
        "🔎 Evidence Search & Filters",
        "🤖 AI Investigation Assistant",
        "📅 Chronological Timeline",
    ])

    # -------------------------------------------------------------
    # TAB 1: Evidence Search & Filters
    # -------------------------------------------------------------
    with tab_search:
        st.subheader("🔎 Search & Filter Evidence Records")
        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            query = st.text_input(
                "Keyword Search (case-insensitive):",
                placeholder="Enter keyword to search across records (e.g. document title, type, location)...",
                help="Searches text fields strictly within the selected case.",
            )
        with search_col2:
            type_options = get_record_types_for_case(records, selected_case)
            selected_type = st.selectbox("Record Type Filter:", options=type_options)

        filtered = filter_case_evidence(
            records=records,
            case_id=selected_case,
            query=query,
            selected_type=selected_type,
        )

        st.markdown(f"**Found {len(filtered)} matching record(s) in `{selected_case}`:**")

        if not filtered:
            st.warning("No records in this case matched your search criteria.")
        else:
            for rec in filtered:
                card = format_citation_card(rec)
                with st.container(border=True):
                    header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
                    with header_col1:
                        st.markdown(f"**Record ID: `{card['record_id']}`** | Type: `{card['record_type']}`")
                    with header_col2:
                        amt_display = card['amount_usd'] if card['amount_usd'] else "N/A"
                        st.markdown(f"**Amount**: {amt_display}")
                    with header_col3:
                        if card["has_complete_citations"]:
                            st.caption("✅ Complete Citation")
                        else:
                            st.caption("⚠️ Partial Citation")

                    # Source Citation Coordinates
                    st.markdown(
                        f"📄 **Document**: `{card['document_name']}` | "
                        f"**Page**: `{card['page_number']}` | "
                        f"**Timestamp**: `{card['timestamp']}`"
                    )

                    # Sanitized Description Preview
                    raw_desc = rec.get("description", "No description recorded.")
                    safe_desc = sanitize_pii_for_prompt(str(raw_desc))
                    st.markdown(f"**Summary**: {safe_desc}")

                    # Collapsible Safe Inspector for remaining fields
                    with st.expander("🔍 View Traceability & Safe Metadata (Sensitive Contact Details Redacted)"):
                        st.code(card["citation_string"], language="text")
                        if rec.get("location"):
                            st.markdown(f"- **Location**: `{sanitize_pii_for_prompt(str(rec.get('location')))}`")
                        if rec.get("person_name") or rec.get("witness_name") or rec.get("reported_by_name"):
                            entity = rec.get("person_name") or rec.get("witness_name") or rec.get("reported_by_name")
                            st.markdown(f"- **Recorded Entity**: `{entity}` *(Contact details withheld for privacy)*")

    # -------------------------------------------------------------
    # TAB 2: AI Investigation Assistant
    # -------------------------------------------------------------
    with tab_ai:
        st.subheader("🤖 AI-Assisted Investigation Inquiry")
        st.markdown(
            "Ask natural-language questions regarding the evidence in this case. "
            "Answers are grounded strictly in retrieved records using the local **Ollama** model (`qwen2.5:3b`)."
        )

        # Pre-set inquiry helpers (dynamically tailored to active case)
        preset_cols = st.columns(3)
        sample_q = ""
        with preset_cols[0]:
            if st.button("📋 Case Event Overview", use_container_width=True):
                sample_q = f"Provide an objective factual summary of all recorded events in case {selected_case}."
        with preset_cols[1]:
            if st.button("🕒 Chronological Inquiry", use_container_width=True):
                sample_q = f"What is the chronological sequence of documented events in case {selected_case}?"
        with preset_cols[2]:
            if st.button("💰 Financial / Numeric Inquiry", use_container_width=True):
                sample_q = f"What financial transactions, amounts, or numerical adjustments are documented in case {selected_case}?"

        user_question = st.text_area(
            "Enter your investigation question:",
            value=sample_q if sample_q else "",
            placeholder=f"e.g. Which documents describe events in case {selected_case}? What evidence supports these records?",
            height=100,
        )

        col_btn, _ = st.columns([1, 4])
        with col_btn:
            ask_clicked = st.button("🔍 Ask Copilot", type="primary", use_container_width=True)

        if ask_clicked:
            if not user_question.strip():
                st.warning("Please enter a question before submitting.")
            else:
                with st.spinner("Retrieving evidence and consulting local Ollama model (qwen2.5:3b)..."):
                    result = answer_question(
                        question=user_question.strip(),
                        case_id=selected_case,
                        records_source=records,
                    )

                # Render Structured Report
                st.markdown("---")
                if result.get("status") == "no_evidence_found":
                    st.warning(f"🔍 **No Evidence Found**: {result.get('answer')}")
                    st.info(result.get("limitations"))
                else:
                    if result.get("status") == "model_error":
                        st.error("⚠️ Local model execution encountered an issue. Displaying deterministic evidence fallback:")

                    # Section 1: Answer
                    st.markdown("### 📌 Answer")
                    st.markdown(result.get("answer"))

                    # Section 2: Supporting Evidence
                    st.markdown("### 🔍 Supporting Evidence")
                    st.markdown(result.get("supporting_evidence"))

                    # Section 3: Limitations / Missing Information
                    st.markdown("### ⚠️ Limitations / Missing Information")
                    st.markdown(result.get("limitations"))

                    # Section 4: Suggested Follow-up Questions
                    st.markdown("### 💡 Suggested Follow-up Questions")
                    st.markdown(result.get("suggested_follow_up_questions"))

                # Citation Traceability Drawer
                with st.expander("📋 Review Active Source Citations"):
                    if result.get("citations"):
                        for c in result["citations"]:
                            p_str = c['page_number'] if c['page_number'] is not None else "[NOT RECORDED]"
                            st.markdown(
                                f"- **Record**: `{c['record_id']}` | "
                                f"**Document**: `{c['document_name']}` | "
                                f"**Page**: `{p_str}` | "
                                f"**Timestamp**: `{c['timestamp']}`"
                            )
                    else:
                        st.caption("No citations attached to this inquiry.")

    # -------------------------------------------------------------
    # TAB 3: Chronological Timeline
    # -------------------------------------------------------------
    with tab_timeline:
        st.subheader(f"📅 Chronological Timeline for `{selected_case}`")
        st.caption("Records sorted by verified ISO-8601 timestamps. Undated records are placed at the end.")

        ordered = sort_records_chronologically(records, case_id=selected_case)

        if not ordered:
            st.info("No records available in this case.")
        else:
            for idx, rec in enumerate(ordered, start=1):
                citation = get_citation_metadata(rec)
                ts = citation.get("timestamp") or "⚠️ [TIMESTAMP NOT RECORDED]"
                p_display = str(citation.get("page_number")) if citation.get("page_number") is not None else "[NOT RECORDED]"
                doc = citation.get("document_name") or "[NOT RECORDED]"
                rtype = rec.get("record_type", "unspecified")
                amt = rec.get("amount_usd")

                with st.container(border=True):
                    col_t1, col_t2 = st.columns([3, 1])
                    with col_t1:
                        st.markdown(f"**{idx}. `{ts}`** — Record `{citation.get('record_id')}` (`{rtype}`)")
                    with col_t2:
                        if amt is not None:
                            st.markdown(f"**Amount**: `${amt:,.2f}`")

                    st.markdown(f"📄 **Source**: `{doc}` (Page: `{p_display}`)")
                    safe_desc = sanitize_pii_for_prompt(str(rec.get("description", "")))
                    st.markdown(f"*{safe_desc}*")


if __name__ == "__main__":
    main()
