import json
import logging
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal, init_db
from backend.models import (
    User, CaseModel, EvidenceItemModel, EvidenceMentionModel,
    EvidenceSourceModel, CaseFindingModel, InvestigationBoardModel
)
from backend.auth import hash_password
from backend.graph_manager import get_graph_engine
from backend.blockchain_service import BlockchainService
from backend.rag_service import rag_service

logger = logging.getLogger("atlas.seed")

DEMO_USERS = [
    {
        "badge_number": "IND-LE-8402",
        "officer_name": "Inspector Vikram Rathore",
        "email": "v.rathore@cid.gov.in",
        "password": "password123",
        "department": "Crime Branch Special Investigation Unit",
        "unit": "Cyber & Organized Crime Cell",
        "role": "investigator",
        "clearance_level": "Level 3: Lead Detective"
    },
    {
        "badge_number": "ADMIN-001",
        "officer_name": "Special Director Rajesh Sharma",
        "email": "r.sharma@cid.gov.in",
        "password": "admin123",
        "department": "Central Intelligence Directorate",
        "unit": "Headquarters Security Division",
        "role": "admin",
        "clearance_level": "Level 4: Special Director"
    },
    {
        "badge_number": "ANALYST-101",
        "officer_name": "Intelligence Analyst Priya Sen",
        "email": "p.sen@cid.gov.in",
        "password": "analyst123",
        "department": "Forensic Data Analytics Wing",
        "unit": "Telecom & AML Division",
        "role": "analyst",
        "clearance_level": "Level 2: Investigator"
    }
]

SAMPLE_CASE_FILES = [
    settings.data_dir.parent / "member4" / "sample_data" / "case_001.json",
    settings.data_dir.parent / "member4" / "sample_data" / "case_002.json",
    settings.data_dir.parent / "member3" / "sample_data" / "case_001.json",
    settings.data_dir.parent / "member3" / "sample_data" / "case_002.json",
    settings.data_dir.parent / "member5" / "criminal-copilot" / "data" / "CASE_006_BACKEND.json"
]

def seed_database(db: Optional[Session] = None):
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        logger.info("Starting ATLAS database seeding...")
        # 1. Seed demo users
        for u in DEMO_USERS:
            existing = db.query(User).filter(User.badge_number == u["badge_number"]).first()
            if not existing:
                new_user = User(
                    badge_number=u["badge_number"],
                    officer_name=u["officer_name"],
                    email=u["email"],
                    password_hash=hash_password(u["password"]),
                    department=u["department"],
                    unit=u["unit"],
                    role=u["role"],
                    clearance_level=u["clearance_level"],
                    created_at=datetime.datetime.utcnow(),
                    last_login=datetime.datetime.utcnow()
                )
                db.add(new_user)
        db.commit()

        # 2. Ingest Sample Cases (Only if explicitly enabled via SEED_SAMPLE_DATA=true)
        if not getattr(settings, "seed_sample_data", False):
            logger.info("Sample demo case seeding is disabled (SEED_SAMPLE_DATA=false). Operating strictly on live uploaded evidence.")
            return

        engine = get_graph_engine()
        rag_chunks = []

        for c_file in SAMPLE_CASE_FILES:
            if not c_file.exists():
                logger.warning(f"Sample file {c_file} not found, skipping.")
                continue

            with open(c_file, "r", encoding="utf-8") as f:
                payload = json.load(f)

            case_info = payload.get("case", {})
            cid = case_info.get("case_id") or f"CASE_{c_file.stem}"
            fir = case_info.get("fir_number") or f"SYN-{cid}"
            reg_date = case_info.get("registration_date") or datetime.date.today().isoformat()

            # Always populate Knowledge Graph Engine
            engine.ingest_payload(payload, execute_in_neo4j=False)

            # Check if Case already seeded in DB
            db_case = db.query(CaseModel).filter(CaseModel.case_id == cid).first()
            if not db_case:
                db_case = CaseModel(
                    case_id=cid,
                    fir_number=fir,
                    case_name=f"Syndicate Probe: {cid}",
                    status="Under Investigation",
                    lead_investigator="Inspector Vikram Rathore",
                    uploaded_by="IND-LE-8402",
                    severity="Critical" if cid == "CASE_001" else "High",
                    crime_category="Organized Crime & Extortion",
                    date_filed=reg_date,
                    summary=f"Investigation docket {cid} registered under FIR {fir} containing multi-channel telecom and banking exhibits.",
                    overlapping_cases=["CASE_002"] if cid == "CASE_001" else ["CASE_001"] if cid == "CASE_002" else [],
                    evidences=[s.get("file_name", "exhibit") for s in payload.get("source_index", [])]
                )
                db.add(db_case)
                db.commit()

                # Sources and Evidence items
                ev_objects = []
                for s_idx, s in enumerate(payload.get("source_index", [])):
                    fname = s.get("file_name", f"source_{s_idx}.pdf")
                    eid = s.get("source_id") or f"EV-{cid}-{s_idx+1}"
                    ev_objects.append(EvidenceItemModel(
                        evidence_id=eid,
                        case_id=cid,
                        sha256=f"a1b2c3d4e5f6{cid.lower()}{s_idx:04d}000000000000000000000000000000000000"[:64],
                        filename=fname,
                        uploader="Inspector Vikram Rathore (IND-LE-8402)",
                        uploaded_at=datetime.datetime.utcnow().isoformat() + "Z",
                        format=s.get("format", "pdf"),
                        size=s.get("row_count", 15) * 512,
                        relative_path=f"data/originals/{cid}/{fname}",
                        category=s.get("source_type", "Forensic Document"),
                        status="Complete",
                        job_id=f"JOB-{eid}",
                        job_stage="Complete",
                        job_progress=1.0,
                        job_classification=s.get("source_type", "Document"),
                        mention_count=len(payload.get("entity_mentions", [])),
                        claim_count=s.get("row_count", 1)
                    ))
                db.add_all(ev_objects)
                db.commit()

                # Seed sample mentions in batch (limit to first 100 for fast seeding)
                mention_objects = []
                for m_idx, m in enumerate(payload.get("entity_mentions", [])[:100]):
                    mid = m.get("mention_id") or f"M-{cid}-{m_idx+1}"
                    prov = m.get("provenance", {}) or {}
                    mention_objects.append(EvidenceMentionModel(
                        id=mid,
                        evidence_id=m.get("source_id", f"EV-{cid}-1"),
                        case_id=cid,
                        type=m.get("entity_type", "Entity").capitalize(),
                        raw_value=m.get("surface_form", ""),
                        normalized_value=m.get("canonical_value", m.get("surface_form", "")),
                        role=m.get("role", "Accused"),
                        quote=m.get("verbatim_quote") or m.get("surface_form"),
                        page=prov.get("page_number", 1),
                        row=prov.get("row_number"),
                        ocr_scores={"confidence": m.get("confidence", 0.95)}
                    ))
                    if m.get("verbatim_quote") and len(rag_chunks) < 30:
                        rag_chunks.append({
                            "id": f"chunk_{cid}_{m_idx}",
                            "data": f"Case {cid} | Entity: {m.get('canonical_value')} ({m.get('entity_type')}) | Quote: {m.get('verbatim_quote')}",
                            "metadata": {"case_id": cid, "entity_type": m.get("entity_type")}
                        })

                db.add_all(mention_objects)
                db.commit()

                # Blockchain ledger block
                BlockchainService.append_block(
                    db=db,
                    case_id=cid,
                    document_type="SEED_INTELLIGENCE_DOCKET",
                    data={"case_id": cid, "fir_number": fir, "sources": len(payload.get("source_index", []))}
                )

                # Activity log entry
                BlockchainService.log_activity(
                    db=db,
                    case_id=cid,
                    action_type="CASE_SEEDED",
                    title=f"Intelligence Docket Synced: {cid}",
                    description=f"Loaded {len(payload.get('source_index', []))} forensic sources and established cross-case intelligence links.",
                    officer_name="Inspector Vikram Rathore",
                    officer_badge="IND-LE-8402",
                    status_type="verified",
                    icon_type="check"
                )

        # Seed initial Investigation Board
        b1 = db.query(InvestigationBoardModel).filter(InvestigationBoardModel.board_id == "BOARD-DEMO-001").first()
        if not b1:
            b1 = InvestigationBoardModel(
                board_id="BOARD-DEMO-001",
                case_id="CASE_001",
                title="Cross-Case Syndicate Master Canvas",
                creator_name="Inspector Vikram Rathore",
                creator_badge="IND-LE-8402",
                nodes=[
                    {"id": "node_1", "type": "manualEntity", "position": {"x": 200, "y": 150}, "data": {"label": "Vikram Singh", "category": "Person", "status": "Prime Suspect"}},
                    {"id": "node_2", "type": "manualEntity", "position": {"x": 550, "y": 150}, "data": {"label": "+919876543210", "category": "Phone", "status": "Burner Line"}},
                    {"id": "node_3", "type": "stickyNote", "position": {"x": 200, "y": 320}, "data": {"text": "Note: Vikram Singh's phone co-located with Sameer Khan near Tower 404.", "color": "#fef08a"}}
                ],
                edges=[
                    {"id": "edge_1_2", "source": "node_1", "target": "node_2", "type": "manualEdge", "data": {"label": "OPERATES"}}
                ],
                created_at=datetime.datetime.utcnow().isoformat() + "Z",
                updated_at=datetime.datetime.utcnow().isoformat() + "Z"
            )
            db.add(b1)
            db.commit()

        # Upsert RAG chunks into Upstash Vector
        if rag_chunks:
            try:
                rag_service.upsert_chunks(rag_chunks)
            except Exception as e:
                logger.warning(f"RAG upsert during seed: {e}")

        logger.info("ATLAS database seeding completed successfully.")

    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
        raise e
    finally:
        if close_db:
            db.close()

if __name__ == "__main__":
    init_db()
    seed_database()
