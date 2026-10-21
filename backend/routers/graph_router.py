import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from backend.graph_manager import get_graph_engine, neo4j_client
from backend.copilot import CopilotEngine
from backend.config import settings

logger = logging.getLogger("atlas.graph_router")

router = APIRouter(prefix="/api/graph", tags=["Knowledge Graph & Topology Explorer"])

class AiQueryRequest(BaseModel):
    question: str
    case_id: Optional[str] = None
    nodes_count: Optional[int] = None
    edges_count: Optional[int] = None
    selected_node_id: Optional[str] = None

class CypherRequest(BaseModel):
    query: str
    params: Optional[Dict[str, Any]] = None

@router.get("", summary="Get Filtered Network Graph Data")
async def get_graph(
    limit: int = Query(500, ge=1, le=2000),
    graph_type: str = Query("full"),
    case_id: Optional[str] = Query(None),
    include_isolated: bool = Query(False)
):
    engine = get_graph_engine()

    # Normalize parameters for both HTTP requests and direct programmatic calls
    lim = limit if isinstance(limit, int) else 500
    gt = (graph_type if isinstance(graph_type, str) else "full").lower()
    cid = case_id.strip() if (isinstance(case_id, str) and case_id.strip()) else None
    inc_iso = include_isolated if isinstance(include_isolated, bool) else False

    # If case_id is specified, ensure case entities are loaded into engine from database
    if cid:
        has_case = any(
            cid in n.get("properties", {}).get("case_ids", []) or n.get("properties", {}).get("case_id") == cid
            for n in engine.nodes.values()
        )
        if not has_case:
            from backend.database import SessionLocal
            from backend.models import EvidenceMentionModel
            from backend.pipeline import EvidencePipeline
            with SessionLocal() as db_session:
                m_list = db_session.query(EvidenceMentionModel).filter(EvidenceMentionModel.case_id == cid).all()
                if m_list:
                    EvidencePipeline._sync_to_graph(cid, "db_sync", m_list, engine)

    # If case_id is specified, include isolated entities for that case so user sees all extracted entities
    filter_iso = False if cid else (not inc_iso)
    g_data = engine.get_graph_data(filter_isolated=filter_iso)
    
    raw_nodes = g_data.get("nodes", [])
    raw_edges = g_data.get("edges", [])

    # Filter by case_id if specified
    if case_id and case_id.strip():
        cid = case_id.strip()
        case_nodes_set = set()
        filtered_nodes = []
        for n in raw_nodes:
            c_ids = n.get("properties", {}).get("case_ids", [])
            # Strictly include only nodes that belong to this case
            if cid in c_ids or n.get("properties", {}).get("case_id") == cid:
                filtered_nodes.append(n)
                case_nodes_set.add(n["id"])

        filtered_edges = [
            e for e in raw_edges
            if e["from"] in case_nodes_set and e["to"] in case_nodes_set
        ]

        raw_nodes = filtered_nodes
        raw_edges = filtered_edges

    # Filter by graph_type
    gt = (graph_type if isinstance(graph_type, str) else "full").lower()
    if gt in ("cdr", "telecom"):
        # Keep only phone, call, tower, imei, device
        allowed_labels = {"Phone", "CellTower", "Imei", "IMEI", "Device"}
        kept_nodes = [n for n in raw_nodes if any(l in allowed_labels for l in n.get("labels", []))]
        kept_node_ids = {n["id"] for n in kept_nodes}
        raw_nodes = kept_nodes
        raw_edges = [e for e in raw_edges if e["from"] in kept_node_ids and e["to"] in kept_node_ids]

    elif gt in ("person", "suspect"):
        # Keep only person suspects and direct connections
        kept_nodes = [n for n in raw_nodes if "Person" in n.get("labels", [])]
        kept_node_ids = {n["id"] for n in kept_nodes}
        raw_nodes = kept_nodes
        raw_edges = [e for e in raw_edges if e["from"] in kept_node_ids and e["to"] in kept_node_ids]

    elif gt in ("financial", "banking"):
        # Keep bank accounts and transfers
        allowed_labels = {"BankAccount", "Organization", "Account"}
        kept_nodes = [n for n in raw_nodes if any(l in allowed_labels for l in n.get("labels", []))]
        kept_node_ids = {n["id"] for n in kept_nodes}
        raw_nodes = kept_nodes
        raw_edges = [e for e in raw_edges if e["from"] in kept_node_ids and e["to"] in kept_node_ids]

    elif gt in ("vehicle", "mobility"):
        # Keep vehicles and locations
        allowed_labels = {"Vehicle", "Location", "CellTower", "Person"}
        kept_nodes = [n for n in raw_nodes if any(l in allowed_labels for l in n.get("labels", []))]
        kept_node_ids = {n["id"] for n in kept_nodes}
        raw_nodes = kept_nodes
        raw_edges = [e for e in raw_edges if e["from"] in kept_node_ids and e["to"] in kept_node_ids]

    # Format nodes and edges to match Vis.js and Member 1 interfaces
    formatted_nodes = []
    for n in raw_nodes[:lim]:
        deg = n.get("degree", 0)
        labels = n.get("labels", ["Entity"])
        specific = [l for l in labels if l != "Entity"]
        ordered_labels = specific + (["Entity"] if "Entity" in labels else [])
        if not ordered_labels:
            ordered_labels = ["Entity"]

        formatted_nodes.append({
            "id": n["id"],
            "name": n.get("caption") or n.get("properties", {}).get("name") or n["id"],
            "labels": ordered_labels,
            "properties": n.get("properties", {}),
            "degree": deg,
            "is_key_entity": deg >= 4 or n.get("properties", {}).get("cross_case", False),
            "level": n.get("level", 2)
        })

    formatted_edges = []
    for idx, e in enumerate(raw_edges):
        formatted_edges.append({
            "id": e.get("id") or f"edge_{e['from']}_{e.get('label', 'REL')}_{e['to']}_{idx}",
            "source": e["from"],
            "target": e["to"],
            "from": e["from"],
            "to": e["to"],
            "type": e.get("label", "ASSOCIATED_WITH"),
            "label": e.get("label", "ASSOCIATED_WITH"),
            "properties": e.get("properties", {})
        })

    return {
        "nodes": formatted_nodes,
        "edges": formatted_edges,
        "total_nodes": len(formatted_nodes),
        "total_edges": len(formatted_edges),
        "total_isolated_nodes": 0
    }

@router.get("/expand", summary="Expand 1-Hop Neighbor Network")
async def expand_node(
    node_id: str = Query(...),
    case_id: Optional[str] = Query(None)
):
    engine = get_graph_engine()
    neighbor_ids = set()
    expanded_edges = []

    for idx, e in enumerate(engine.aggregated_edges.values()):
        if e["from"] == node_id:
            neighbor_ids.add(e["to"])
            expanded_edges.append({
                "id": f"exp_edge_{e['from']}_{e['to']}_{idx}",
                "source": e["from"],
                "target": e["to"],
                "from": e["from"],
                "to": e["to"],
                "type": e.get("label", "REL"),
                "label": e.get("label", "REL"),
                "properties": e.get("properties", {})
            })
        elif e["to"] == node_id:
            neighbor_ids.add(e["from"])
            expanded_edges.append({
                "id": f"exp_edge_{e['from']}_{e['to']}_{idx}",
                "source": e["from"],
                "target": e["to"],
                "from": e["from"],
                "to": e["to"],
                "type": e.get("label", "REL"),
                "label": e.get("label", "REL"),
                "properties": e.get("properties", {})
            })

    expanded_nodes = []
    for nid in neighbor_ids:
        if nid in engine.nodes:
            n = engine.nodes[nid]
            expanded_nodes.append({
                "id": n["id"],
                "name": n.get("caption") or n["id"],
                "labels": n.get("labels", ["Entity"]),
                "properties": n.get("properties", {}),
                "degree": n.get("degree", 1),
                "is_key_entity": n.get("properties", {}).get("cross_case", False)
            })

    return {
        "nodes": expanded_nodes,
        "edges": expanded_edges,
        "total_nodes": len(expanded_nodes),
        "total_edges": len(expanded_edges)
    }

@router.post("/ai-query", summary="Interactive AI Graph Query & Subgraph Extraction")
async def ai_graph_query(req: AiQueryRequest):
    return CopilotEngine.answer_graph_query(
        question=req.question,
        case_id=req.case_id,
        nodes_count=req.nodes_count,
        edges_count=req.edges_count,
        selected_node_id=req.selected_node_id
    )

# ---------- Member 3 Direct Endpoints ----------

@router.post("/upload", summary="Ingest Case JSON directly into Knowledge Graph")
async def upload_case_json(file: UploadFile = File(...)):
    engine = get_graph_engine()
    try:
        content = await file.read()
        payload = json.loads(content.decode("utf-8"))
        stats = engine.ingest_payload(payload, execute_in_neo4j=neo4j_client.is_connected)
        return {
            "status": "success",
            "filename": file.filename,
            "ingested_stats": stats
        }
    except Exception as e:
        logger.error(f"Error ingesting JSON case file: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/export/cypher", response_class=PlainTextResponse, summary="Export Neo4j Cypher Script")
async def export_cypher():
    engine = get_graph_engine()
    return engine.export_cypher()

@router.post("/cypher", summary="Execute Raw Cypher Query")
async def execute_cypher(req: CypherRequest):
    if not neo4j_client.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not connected. In-memory graph engine is active."
        )
    try:
        results = neo4j_client.execute_read(req.query, req.params or {})
        return {"status": "success", "records": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/reset", summary="Clear Knowledge Graph Engine")
async def reset_graph():
    engine = get_graph_engine()
    engine.clear()
    if neo4j_client.is_connected:
        neo4j_client.execute_write("MATCH (n) DETACH DELETE n")
    return {"status": "cleared"}

@router.get("/status", summary="Check Neo4j Engine Status")
async def get_neo4j_status():
    return {
        "connected": neo4j_client.is_connected,
        "uri": settings.neo4j_uri,
        "database": settings.neo4j_database,
        "mode": "live_neo4j" if neo4j_client.is_connected else "in_memory_engine"
    }
