import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import EvidenceMentionModel
from backend.graph_manager import get_graph_engine

logger = logging.getLogger("atlas.entities_router")

router = APIRouter(prefix="/api/entities", tags=["Entity Directory & Search"])

@router.get("/search", summary="Multi-Property Entity Search")
async def search_entities(
    q: str = Query("", description="Query string for name, phone, VIN, account"),
    entity_type: Optional[str] = Query(None, description="Filter by category (Person, Phone, Vehicle, BankAccount)"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    query_str = q.strip().lower()
    engine = get_graph_engine()
    results = []
    seen = set()

    for nid, node in engine.nodes.items():
        labels = node.get("labels", [])
        props = node.get("properties", {})
        caption = str(node.get("caption") or "").lower()
        canon = str(props.get("canonical_value") or "").lower()
        name = str(props.get("name") or "").lower()

        # Check entity_type
        if entity_type and entity_type.lower() != "all":
            if not any(l.lower() == entity_type.lower() for l in labels):
                continue

        # Match query
        if not query_str or query_str in caption or query_str in canon or query_str in name or query_str in nid.lower():
            if nid not in seen:
                seen.add(nid)
                display_title = node.get("caption") or props.get("name") or nid
                results.append({
                    "id": nid,
                    "entity_id": nid,
                    "name": display_title,
                    "display_name": display_title,
                    "labels": labels,
                    "case_ids": props.get("case_ids", []),
                    "properties": props
                })
                if len(results) >= limit:
                    break

    # If graph had few, also check DB mentions
    if len(results) < limit:
        m_query = db.query(EvidenceMentionModel)
        if query_str:
            m_query = m_query.filter(
                EvidenceMentionModel.normalized_value.ilike(f"%{query_str}%") |
                EvidenceMentionModel.raw_value.ilike(f"%{query_str}%")
            )
        if entity_type and entity_type.lower() != "all":
            m_query = m_query.filter(EvidenceMentionModel.type.ilike(f"%{entity_type}%"))
        
        db_mentions = m_query.limit(limit - len(results)).all()
        for m in db_mentions:
            m_nid = f"{m.type.lower()}:{m.normalized_value}"
            if m_nid not in seen:
                seen.add(m_nid)
                results.append({
                    "id": m_nid,
                    "entity_id": m_nid,
                    "name": m.normalized_value,
                    "display_name": m.normalized_value,
                    "labels": ["Entity", m.type],
                    "case_ids": [m.case_id],
                    "properties": {
                        "canonical_value": m.normalized_value,
                        "raw_value": m.raw_value,
                        "role": m.role,
                        "quote": m.quote,
                        "case_ids": [m.case_id]
                    }
                })

    return results

@router.get("/{entity_id:path}", summary="Get Entity Profile & 1-Hop Connections")
async def get_entity_profile(entity_id: str, db: Session = Depends(get_db)):
    engine = get_graph_engine()
    node = engine.nodes.get(entity_id)

    if not node:
        # Check DB for mention fallback
        mention = db.query(EvidenceMentionModel).filter(
            (EvidenceMentionModel.id == entity_id) |
            (EvidenceMentionModel.normalized_value == entity_id)
        ).first()
        if mention:
            node = {
                "id": entity_id,
                "caption": mention.normalized_value,
                "labels": ["Entity", mention.type],
                "properties": {
                    "name": mention.normalized_value,
                    "canonical_value": mention.normalized_value,
                    "role": mention.role,
                    "quote": mention.quote,
                    "case_ids": [mention.case_id]
                }
            }
        else:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found.")

    # Find connections
    connections = []
    seen_conn = set()

    for idx, e in enumerate(engine.aggregated_edges.values()):
        rel = e.get("label", "CONNECTED")
        if e["from"] == entity_id:
            target_id = e["to"]
            target_node = engine.nodes.get(target_id, {})
            key = f"OUT_{rel}_{target_id}"
            if key not in seen_conn:
                seen_conn.add(key)
                connections.append({
                    "relationship": rel,
                    "rel_type": rel,
                    "direction": "OUTGOING",
                    "target_id": target_id,
                    "target_name": target_node.get("caption") or target_id,
                    "neighbor_labels": target_node.get("labels", ["Entity"]),
                    "properties": e.get("properties", {})
                })
        elif e["to"] == entity_id:
            src_id = e["from"]
            src_node = engine.nodes.get(src_id, {})
            key = f"IN_{rel}_{src_id}"
            if key not in seen_conn:
                seen_conn.add(key)
                connections.append({
                    "relationship": rel,
                    "rel_type": rel,
                    "direction": "INCOMING",
                    "target_id": src_id,
                    "target_name": src_node.get("caption") or src_id,
                    "neighbor_labels": src_node.get("labels", ["Entity"]),
                    "properties": e.get("properties", {})
                })

    return {
        "node": {
            "id": node["id"],
            "name": node.get("caption") or node.get("properties", {}).get("name") or node["id"],
            "labels": node.get("labels", ["Entity"]),
            "properties": node.get("properties", {})
        },
        "connections": connections
    }
