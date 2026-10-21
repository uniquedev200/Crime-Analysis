"""Contract and schema conformance tests for Dev 4 graph payload mapping and Cypher export.

All tests marked with @pytest.mark.gate4.
"""

from __future__ import annotations

import pytest

from atlas.adapters.dev4_graph import format_for_dev4
from atlas.contracts.enums import (
    Assertion,
    EntityType,
    IdentifierTrust,
    Origin,
    QuoteStatus,
    RelType,
    SignalPolarity,
    StatedRole,
    SuggestionStatus,
    UnitKind,
)
from atlas.contracts.records import (
    Mention,
    Relationship,
    ResolutionSuggestion,
    Signal,
    SourceRef,
)
from atlas.output.cypher_export import export_cypher
from atlas.output.graph_payload import build_graph_payload

pytestmark = pytest.mark.gate4


def _sample_source_ref(doc_id: str = "DOC-112233445566", unit_id: str = "DOC-112233445566:p001") -> SourceRef:
    return SourceRef(
        doc_id=doc_id,
        file_name="FIR_A.pdf",
        file_sha256="11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff",
        unit_id=unit_id,
        unit_kind=UnitKind.PAGE,
        page=1,
        text_origin=Origin.PDF_TEXT,
        quote="Accused Vikram Singh uses phone 9876543210 and drove vehicle DL01AB1234",
        quote_status=QuoteStatus.VERIFIED,
        occurrence_count=1,
    )


def test_build_graph_payload_trust_gate_and_canonical():
    """Identifier nodes are created ONLY when trust is strong/confirmed; unconfirmed OCR does not create node."""
    case_id = "CASE-A-001"
    src = _sample_source_ref()

    m_person = Mention(
        mention_id="M-P1",
        case_id=case_id,
        doc_id=src.doc_id,
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        normalized_value="vikram_singh",
        stated_role=StatedRole.ACCUSED,
        origin=Origin.PDF_TEXT,
        source=src,
    )

    # Strong phone -> MUST create node
    m_phone_strong = Mention(
        mention_id="M-PH1",
        case_id=case_id,
        doc_id=src.doc_id,
        type=EntityType.PHONE,
        surface_text="9876543210",
        normalized_value="+919876543210",
        origin=Origin.PDF_TEXT,
        identifier_trust=IdentifierTrust.STRONG,
        source=src,
    )

    # Unconfirmed OCR IMEI -> MUST NOT create node
    m_imei_unconfirmed = Mention(
        mention_id="M-IM1",
        case_id=case_id,
        doc_id=src.doc_id,
        type=EntityType.IMEI,
        surface_text="867543029182736",
        normalized_value="867543029182736",
        origin=Origin.OCR,
        identifier_trust=IdentifierTrust.REVIEW_REQUIRED,
        confirmed_by=None,
        source=src,
    )

    # Confirmed OCR Vehicle -> MUST create node
    m_veh_confirmed = Mention(
        mention_id="M-VH1",
        case_id=case_id,
        doc_id=src.doc_id,
        type=EntityType.VEHICLE,
        surface_text="DL 01 AB 1234",
        normalized_value="DL01AB1234",
        origin=Origin.OCR,
        identifier_trust=IdentifierTrust.REVIEW_REQUIRED,
        confirmed_by="analyst_1",
        source=src,
    )

    r_phone = Relationship(
        rel_id="R-1",
        case_id=case_id,
        type=RelType.USES_PHONE,
        subject_mention_id="M-P1",
        object_mention_id="M-PH1",
        assertion=Assertion.STATED,
        origin=Origin.PDF_TEXT,
        source=src,
    )

    # Relationship to unconfirmed IMEI -> should not create edge because target node omitted
    r_imei = Relationship(
        rel_id="R-2",
        case_id=case_id,
        type=RelType.USES_DEVICE,
        subject_mention_id="M-P1",
        object_mention_id="M-IM1",
        assertion=Assertion.STATED,
        origin=Origin.OCR,
        source=src,
    )

    payload = build_graph_payload(
        case_id=case_id,
        mentions=[m_person, m_phone_strong, m_imei_unconfirmed, m_veh_confirmed],
        relationships=[r_phone, r_imei],
        events=[],
    )

    node_ids = {n["node_id"] for n in payload["nodes"]}
    edge_ids = {e["edge_id"] for e in payload["edges"]}

    assert "CASE:CASE-A-001" in node_ids
    assert "PERSON:CASE-A-001:vikram_singh" in node_ids
    assert "PHONE:+919876543210" in node_ids
    assert "VEHICLE:DL01AB1234" in node_ids

    # Unconfirmed OCR identifier must not create node
    assert "IMEI:867543029182736" not in node_ids

    # Edge to strong phone must exist; edge to omitted IMEI must not exist
    assert "R-1" in edge_ids
    assert "R-2" not in edge_ids

    # Every node and edge must carry case_ids and evidence_ids
    for n in payload["nodes"]:
        assert "case_ids" in n and len(n["case_ids"]) > 0
        assert "evidence_ids" in n
        assert isinstance(n["canonical"], bool)

    for e in payload["edges"]:
        assert "case_ids" in e and len(e["case_ids"]) > 0
        assert "evidence_ids" in e
        assert isinstance(e["canonical"], bool)


def test_suggestions_and_merges_canonical_flags():
    """Unapproved suggestions produce CANDIDATE_MATCH (canonical: false); approved merges produce SAME_AS (canonical: true)."""
    case_id = "CASE-A-001"
    src = _sample_source_ref()

    m_person = Mention(
        mention_id="M-P1",
        case_id=case_id,
        doc_id=src.doc_id,
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        normalized_value="vikram_singh",
        origin=Origin.PDF_TEXT,
        source=src,
    )

    sug = ResolutionSuggestion(
        suggestion_id="SUG-01",
        case_id=case_id,
        mention_id="M-P1",
        candidate_entity_id="PERSON:CASE-B-002:vicky",
        candidate_case_id="CASE-B-002",
        status=SuggestionStatus.NEEDS_REVIEW,
        heuristic_rank=0.78,
        rank_note="heuristic ordering, not a probability",
        signals=[
            Signal(
                kind="exact_identifier",
                polarity=SignalPolarity.SUPPORTS,
                detail="Shared phone +919876543210",
                sources=[],
            )
        ],
        explanation="Possible match between Vikram Singh and Vicky via shared phone.",
        requires_human_decision=True,
    )

    approved_merge = {
        "entity_id_1": "PERSON:CASE-A-001:vikram_singh",
        "entity_id_2": "PERSON:CASE-B-002:vicky",
        "action_id": "ACT-APPROVED-999",
        "case_id": case_id,
        "status": "active",
    }

    payload = build_graph_payload(
        case_id=case_id,
        mentions=[m_person],
        relationships=[],
        events=[],
        suggestions=[sug],
        approved_merges=[approved_merge],
    )

    edge_map = {e["type"]: e for e in payload["edges"]}

    assert "CANDIDATE_MATCH" in edge_map
    assert edge_map["CANDIDATE_MATCH"]["canonical"] is False
    assert edge_map["CANDIDATE_MATCH"]["props"]["rank_note"] == "heuristic ordering, not a probability"

    assert "SAME_AS" in edge_map
    assert edge_map["SAME_AS"]["canonical"] is True
    assert edge_map["SAME_AS"]["props"]["audit_action_id"] == "ACT-APPROVED-999"


def test_export_cypher_syntax():
    """export_cypher generates deterministic valid Neo4j Cypher MERGE statements."""
    payload = {
        "case_id": "CASE-1",
        "state": "completed",
        "nodes": [
            {
                "node_id": "CASE:CASE-1",
                "label": "Case",
                "props": {"case_id": "CASE-1"},
                "case_ids": ["CASE-1"],
                "evidence_ids": [],
                "canonical": True,
            },
            {
                "node_id": "PERSON:CASE-1:p1",
                "label": "Person",
                "props": {"name": "Arjun Sharma", "role": "witness"},
                "case_ids": ["CASE-1"],
                "evidence_ids": ["M-1"],
                "canonical": True,
            },
        ],
        "edges": [
            {
                "edge_id": "EDGE-1",
                "type": "ASSOCIATED_WITH",
                "src": "PERSON:CASE-1:p1",
                "dst": "CASE:CASE-1",
                "assertion": "stated",
                "origin": "pdf_text",
                "case_ids": ["CASE-1"],
                "evidence_ids": ["R-1"],
                "canonical": True,
                "props": {"note": "Investigated in case"},
            }
        ],
    }

    cypher_text = export_cypher(payload)

    assert "MERGE (n:Case {node_id: 'CASE:CASE-1'})" in cypher_text
    assert "MERGE (n:Person {node_id: 'PERSON:CASE-1:p1'})" in cypher_text
    assert "MATCH (src {node_id: 'PERSON:CASE-1:p1'}), (dst {node_id: 'CASE:CASE-1'})" in cypher_text
    assert "MERGE (src)-[r:ASSOCIATED_WITH {edge_id: 'EDGE-1'}]->(dst)" in cypher_text
    assert "SET n.canonical = true" in cypher_text


def test_format_for_dev4_formats():
    """format_for_dev4 properly converts graph payload to generic, cytoscape, d3, and dev4 formats."""
    payload = {
        "case_id": "CASE-1",
        "state": "completed",
        "nodes": [
            {
                "node_id": "P1",
                "label": "Person",
                "props": {"name": "Vikram"},
                "case_ids": ["CASE-1"],
                "evidence_ids": ["M-1"],
                "canonical": True,
            }
        ],
        "edges": [
            {
                "edge_id": "E1",
                "type": "CALLS",
                "src": "P1",
                "dst": "P2",
                "assertion": "stated",
                "origin": "table_parser",
                "case_ids": ["CASE-1"],
                "evidence_ids": ["R-1"],
                "canonical": True,
                "props": {},
            }
        ],
    }

    # 1. Generic format
    gen = format_for_dev4(payload, format_name="generic")
    assert gen["format"] == "generic"
    assert len(gen["nodes"]) == 1
    assert len(gen["edges"]) == 1

    # 2. Cytoscape format
    cy = format_for_dev4(payload, format_name="cytoscape")
    assert cy["format"] == "cytoscape"
    assert "elements" in cy
    assert cy["elements"]["nodes"][0]["data"]["id"] == "P1"
    assert cy["elements"]["edges"][0]["data"]["source"] == "P1"
    assert cy["elements"]["edges"][0]["data"]["target"] == "P2"

    # 3. D3 format
    d3_res = format_for_dev4(payload, format_name="d3")
    assert d3_res["format"] == "d3"
    assert d3_res["nodes"][0]["id"] == "P1"
    assert d3_res["links"][0]["source"] == "P1"

    # 4. Dev 4 format
    d4 = format_for_dev4(payload, format_name="dev4")
    assert d4["format"] == "dev4"
    assert d4["node_count"] == 1
    assert d4["edge_count"] == 1

    # 5. Unsupported format raises ValueError
    with pytest.raises(ValueError, match="Unsupported Dev4 graph format"):
        format_for_dev4(payload, format_name="unknown_format_xyz")
