import datetime
import hashlib
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    CaseModel, EvidenceItemModel, EvidenceMentionModel, 
    CaseFindingModel, ActivityLogModel, BlockchainBlockModel
)
from backend.analytics import compute_rankings, find_shortest_path, detect_pattern_insights
from backend.copilot import CopilotEngine
from backend.graph_manager import get_graph_engine
from backend.blockchain_service import BlockchainService

router = APIRouter(prefix="/api/cases", tags=["Case Management & Intelligence"])

class CaseCreateRequest(BaseModel):
    case_id: str
    case_name: str
    fir_number: Optional[str] = None
    status: Optional[str] = "Under Investigation"
    lead_investigator: Optional[str] = "Lead Investigator"
    uploaded_by: Optional[str] = None
    severity: Optional[str] = "High"
    crime_category: Optional[str] = "General Investigation"
    primary_suspect: Optional[str] = None
    victim: Optional[str] = None
    date_filed: Optional[str] = None
    summary: Optional[str] = None

class CaseFindingCreateRequest(BaseModel):
    title: str
    category: Optional[str] = "General Note"
    content: str
    officer_name: Optional[str] = "Investigator"
    officer_badge: Optional[str] = "LE-8402"
    severity: Optional[str] = "MEDIUM"
    attachments: Optional[List[Dict[str, Any]]] = []

@router.get("", summary="List Investigation Cases")
async def list_cases(
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    cases = db.query(CaseModel).order_by(CaseModel.created_at.desc()).limit(limit).all()
    results = []
    for c in cases:
        ev_count = db.query(EvidenceItemModel).filter(EvidenceItemModel.case_id == c.case_id).count()
        ent_count = db.query(EvidenceMentionModel).filter(EvidenceMentionModel.case_id == c.case_id).count()
        results.append({
            "case_id": c.case_id,
            "fir_number": c.fir_number or f"FIR-{c.case_id}",
            "case_name": c.case_name,
            "status": c.status,
            "lead_investigator": c.lead_investigator,
            "uploaded_by": c.uploaded_by,
            "severity": c.severity,
            "crime_category": c.crime_category,
            "primary_suspect": c.primary_suspect,
            "victim": c.victim,
            "date_filed": c.date_filed or c.created_at.strftime("%Y-%m-%d"),
            "summary": c.summary,
            "total_entities": ent_count if ent_count > 0 else c.total_entities,
            "evidences": c.evidences or [],
            "evidence_count": ev_count,
            "overlapping_cases": c.overlapping_cases or [],
            "created_at": c.created_at.isoformat() if c.created_at else None
        })
    return results

@router.get("/rankings", summary="Graph Centrality Rankings")
async def get_rankings(
    metric: str = Query("pagerank", pattern="^(pagerank|betweenness|degree)$"),
    label: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    case_id: Optional[str] = Query(None)
):
    return compute_rankings(metric=metric, label=label, limit=limit, case_id=case_id)

@router.get("/shortest-path", summary="Dijkstra Shortest Path Finder")
async def get_shortest_path(
    suspect_name: Optional[str] = Query(None),
    victim_name: Optional[str] = Query(None),
    suspect_id: Optional[str] = Query(None),
    victim_id: Optional[str] = Query(None),
    max_depth: int = Query(5, ge=1, le=10)
):
    src = suspect_id or suspect_name
    dst = victim_id or victim_name
    if not src or not dst:
        raise HTTPException(status_code=400, detail="Must supply both suspect and victim/target parameters.")
    return find_shortest_path(src, dst, max_depth)

@router.post("", summary="Create Investigation Case")
async def create_case(req: CaseCreateRequest, db: Session = Depends(get_db)):
    cid = req.case_id.strip()
    existing = db.query(CaseModel).filter(CaseModel.case_id == cid).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Case with ID '{cid}' already exists.")

    new_case = CaseModel(
        case_id=cid,
        fir_number=req.fir_number or f"FIR-{cid}",
        case_name=req.case_name.strip(),
        status=req.status or "Under Investigation",
        lead_investigator=req.lead_investigator or "Lead Detective",
        uploaded_by=req.uploaded_by,
        severity=req.severity or "High",
        crime_category=req.crime_category or "General Investigation",
        primary_suspect=req.primary_suspect,
        victim=req.victim,
        date_filed=req.date_filed or datetime.date.today().isoformat(),
        summary=req.summary,
        created_at=datetime.datetime.utcnow(),
        updated_at=datetime.datetime.utcnow()
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Log activity and blockchain block
    BlockchainService.append_block(
        db=db,
        case_id=cid,
        document_type="CASE_CREATION",
        data={"case_id": cid, "case_name": new_case.case_name, "fir_number": new_case.fir_number}
    )
    BlockchainService.log_activity(
        db=db,
        case_id=cid,
        action_type="CASE_CREATED",
        title=f"Case Docket Registered: {new_case.case_name}",
        description=f"Initial registration for {cid} under category '{new_case.crime_category}'.",
        officer_name=new_case.lead_investigator,
        status_type="verified",
        icon_type="case"
    )

    return {"case_id": cid, "case_name": new_case.case_name, "status": "created"}

@router.get("/{case_id}", summary="Get Case Details")
async def get_case(case_id: str, db: Session = Depends(get_db)):
    c = db.query(CaseModel).filter(CaseModel.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    
    ev_count = db.query(EvidenceItemModel).filter(EvidenceItemModel.case_id == case_id).count()
    ent_count = db.query(EvidenceMentionModel).filter(EvidenceMentionModel.case_id == case_id).count()

    return {
        "case_id": c.case_id,
        "fir_number": c.fir_number or f"FIR-{c.case_id}",
        "case_name": c.case_name,
        "status": c.status,
        "lead_investigator": c.lead_investigator,
        "uploaded_by": c.uploaded_by,
        "severity": c.severity,
        "crime_category": c.crime_category,
        "primary_suspect": c.primary_suspect,
        "victim": c.victim,
        "date_filed": c.date_filed,
        "summary": c.summary,
        "total_entities": ent_count if ent_count > 0 else c.total_entities,
        "evidences": c.evidences or [],
        "evidence_count": ev_count,
        "overlapping_cases": c.overlapping_cases or [],
        "created_at": c.created_at.isoformat() if c.created_at else None
    }

@router.get("/{case_id}/insights", summary="10 Pattern Insights for Case")
async def get_case_insights(case_id: str):
    return detect_pattern_insights(case_id)

@router.get("/{case_id}/ai-dossier", summary="Executive AI Dossier")
async def get_case_ai_dossier(case_id: str, db: Session = Depends(get_db)):
    c = db.query(CaseModel).filter(CaseModel.case_id == case_id).first()
    c_name = c.case_name if c else case_id
    return CopilotEngine.generate_dossier(case_id, c_name)

@router.delete("/{case_id}", summary="Delete Investigation Case")
async def delete_case(
    case_id: str,
    confirm: bool = Query(False),
    db: Session = Depends(get_db)
):
    if not confirm:
        raise HTTPException(status_code=400, detail="Must set confirm=true to delete case.")
    c = db.query(CaseModel).filter(CaseModel.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    # Remove evidence records, mentions, sources, findings
    db.query(EvidenceMentionModel).filter(EvidenceMentionModel.case_id == case_id).delete()
    db.query(EvidenceSourceModel).filter(EvidenceSourceModel.case_id == case_id).delete()
    db.query(EvidenceItemModel).filter(EvidenceItemModel.case_id == case_id).delete()
    db.query(CaseFindingModel).filter(CaseFindingModel.case_id == case_id).delete()
    db.delete(c)
    db.commit()

    return {"status": "deleted", "case_id": case_id}

@router.delete("/reset", summary="Admin Purge All Cases")
async def reset_cases(
    confirm: bool = Query(False),
    db: Session = Depends(get_db)
):
    if not confirm:
        raise HTTPException(status_code=400, detail="Must set confirm=true to reset database.")
    db.query(EvidenceMentionModel).delete()
    db.query(EvidenceSourceModel).delete()
    db.query(EvidenceItemModel).delete()
    db.query(CaseFindingModel).delete()
    db.query(CaseModel).delete()
    db.commit()
    get_graph_engine().clear()
    return {"status": "all_cases_purged"}

# ---------- Case Findings Endpoints ----------

@router.get("/{case_id}/findings", summary="List Case Finding Notes")
async def get_findings(case_id: str, db: Session = Depends(get_db)):
    findings = db.query(CaseFindingModel).filter(CaseFindingModel.case_id == case_id).all()
    results = []
    for f in findings:
        results.append({
            "finding_id": f.finding_id,
            "case_id": f.case_id,
            "title": f.title,
            "category": f.category,
            "content": f.content,
            "officer_name": f.officer_name,
            "officer_badge": f.officer_badge,
            "severity": f.severity,
            "attachments": f.attachments or [],
            "created_at": f.created_at,
            "updated_at": f.updated_at
        })
    return results

@router.post("/{case_id}/findings", summary="Add Case Finding Note")
async def add_finding(case_id: str, req: CaseFindingCreateRequest, db: Session = Depends(get_db)):
    fid = f"FIND-{abs(hash(req.title + datetime.datetime.utcnow().isoformat())) % 1000000}"
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    finding = CaseFindingModel(
        finding_id=fid,
        case_id=case_id,
        title=req.title,
        category=req.category or "General Note",
        content=req.content,
        officer_name=req.officer_name,
        officer_badge=req.officer_badge,
        severity=req.severity or "MEDIUM",
        attachments=req.attachments or [],
        created_at=now_iso,
        updated_at=now_iso
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)

    BlockchainService.log_activity(
        db=db,
        case_id=case_id,
        action_type="FINDING_ADDED",
        title=f"Finding Note Recorded: {req.title}",
        description=f"Investigative observation cataloged under '{req.category}'.",
        officer_name=req.officer_name or "Investigator",
        officer_badge=req.officer_badge or "LE-8402",
        status_type="info",
        icon_type="note"
    )

    return {
        "finding_id": finding.finding_id,
        "case_id": finding.case_id,
        "title": finding.title,
        "category": finding.category,
        "content": finding.content,
        "officer_name": finding.officer_name,
        "officer_badge": finding.officer_badge,
        "severity": finding.severity,
        "attachments": finding.attachments or [],
        "created_at": finding.created_at
    }

@router.delete("/{case_id}/findings/{finding_id}", summary="Delete Finding Note")
async def delete_finding(case_id: str, finding_id: str, db: Session = Depends(get_db)):
    f = db.query(CaseFindingModel).filter(
        CaseFindingModel.case_id == case_id,
        CaseFindingModel.finding_id == finding_id
    ).first()
    if not f:
        raise HTTPException(status_code=404, detail="Finding note not found.")
    db.delete(f)
    db.commit()
    return {"status": "deleted", "finding_id": finding_id}
