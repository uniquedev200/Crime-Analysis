import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import InvestigationBoardModel

router = APIRouter(prefix="/api/boards", tags=["Investigation Canvas Board"])

class BoardCreateRequest(BaseModel):
    case_id: str
    title: Optional[str] = "Primary Investigation Canvas"
    creator_id: Optional[str] = None
    creator_name: Optional[str] = "Officer"
    creator_badge: Optional[str] = "IND-LE-8402"
    nodes: Optional[List[Dict[str, Any]]] = []
    edges: Optional[List[Dict[str, Any]]] = []
    notes: Optional[List[Dict[str, Any]]] = []
    viewport: Optional[Dict[str, Any]] = {}

class BoardUpdateRequest(BaseModel):
    title: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    notes: Optional[List[Dict[str, Any]]] = None
    viewport: Optional[Dict[str, Any]] = None

def serialize_board(b: InvestigationBoardModel) -> Dict[str, Any]:
    return {
        "board_id": b.board_id,
        "case_id": b.case_id,
        "title": b.title,
        "creator_id": b.creator_id,
        "creator_name": b.creator_name,
        "creator_badge": b.creator_badge,
        "nodes": b.nodes or [],
        "edges": b.edges or [],
        "notes": b.notes or [],
        "viewport": b.viewport or {"x": 0, "y": 0, "zoom": 1},
        "created_at": b.created_at,
        "updated_at": b.updated_at
    }

@router.get("", summary="List Investigation Boards for Case")
async def list_boards(
    case_id: str = Query(...),
    db: Session = Depends(get_db)
):
    boards = db.query(InvestigationBoardModel).filter(
        InvestigationBoardModel.case_id == case_id
    ).all()
    return {
        "total": len(boards),
        "boards": [serialize_board(b) for b in boards]
    }

@router.post("", summary="Create Investigation Canvas Board")
async def create_board(req: BoardCreateRequest, db: Session = Depends(get_db)):
    bid = f"BOARD-{abs(hash(req.case_id + req.title + datetime.datetime.utcnow().isoformat())) % 1000000}"
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    board = InvestigationBoardModel(
        board_id=bid,
        case_id=req.case_id,
        title=req.title or "Primary Investigation Canvas",
        creator_id=req.creator_id,
        creator_name=req.creator_name or "Investigator",
        creator_badge=req.creator_badge or "IND-LE-8402",
        nodes=req.nodes or [],
        edges=req.edges or [],
        notes=req.notes or [],
        viewport=req.viewport or {"x": 0, "y": 0, "zoom": 1},
        created_at=now_iso,
        updated_at=now_iso
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return serialize_board(board)

@router.get("/{board_id}", summary="Get Canvas Board Detail")
async def get_board(board_id: str, db: Session = Depends(get_db)):
    board = db.query(InvestigationBoardModel).filter(
        InvestigationBoardModel.board_id == board_id
    ).first()
    if not board:
        raise HTTPException(status_code=404, detail="Investigation board not found.")
    return serialize_board(board)

@router.put("/{board_id}", summary="Save Investigation Canvas Board State")
async def update_board(
    board_id: str,
    req: BoardUpdateRequest,
    db: Session = Depends(get_db)
):
    board = db.query(InvestigationBoardModel).filter(
        InvestigationBoardModel.board_id == board_id
    ).first()
    if not board:
        raise HTTPException(status_code=404, detail="Investigation board not found.")

    if req.title is not None:
        board.title = req.title
    if req.nodes is not None:
        board.nodes = req.nodes
    if req.edges is not None:
        board.edges = req.edges
    if req.notes is not None:
        board.notes = req.notes
    if req.viewport is not None:
        board.viewport = req.viewport

    board.updated_at = datetime.datetime.utcnow().isoformat() + "Z"
    db.commit()
    db.refresh(board)
    return serialize_board(board)

@router.delete("/{board_id}", summary="Delete Investigation Canvas Board")
async def delete_board(
    board_id: str,
    officer_name: Optional[str] = Query("Officer"),
    officer_badge: Optional[str] = Query("IND-LE-8402"),
    db: Session = Depends(get_db)
):
    board = db.query(InvestigationBoardModel).filter(
        InvestigationBoardModel.board_id == board_id
    ).first()
    if not board:
        raise HTTPException(status_code=404, detail="Investigation board not found.")
    db.delete(board)
    db.commit()
    return {"status": "deleted", "board_id": board_id}
