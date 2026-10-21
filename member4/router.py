"""
Investigation Knowledge Graph API Router (FastAPI)
Plugs directly into the main backend application.
Compatible with standard RBAC dependencies, logging middleware, and auth guards.
"""

import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

try:
    from .config import settings
    from .neo4j_client import Neo4jClient
    from .graph_engine import KnowledgeGraphEngine
except (ImportError, ValueError):
    from config import settings
    from neo4j_client import Neo4jClient
    from graph_engine import KnowledgeGraphEngine

logger = logging.getLogger("graph_router")

router = APIRouter(prefix="/api/graph", tags=["Knowledge Graph"])

# Initialize client and engine (runs in-memory automatically if Neo4j is offline)
neo4j_client = Neo4jClient(
    uri=settings.neo4j_uri,
    user=settings.neo4j_user,
    password=settings.neo4j_password,
    database=settings.neo4j_database
)
neo4j_client.connect()
engine = KnowledgeGraphEngine(neo4j_client=neo4j_client)


class CypherRequest(BaseModel):
    query: str
    params: Optional[Dict[str, Any]] = None


@router.get("", summary="Fetch Graph Data for Visualizer")
async def get_graph_data(filter_isolated: bool = True):
    """
    Returns all extracted nodes and relationships.
    Nodes have degree >= 1 (isolated nodes automatically filtered out).
    Cross-case overlapping entities are flagged with `cross_case: true`.
    """
    return engine.get_graph_data(filter_isolated=filter_isolated)


@router.post("/upload", summary="Ingest Investigation Case JSON")
async def upload_case_payload(file: UploadFile = File(...)):
    """
    Ingests an investigation JSON file:
    - Extracts Person, Phone, Vehicle, IMEI, Cell Tower, Bank Account
    - Builds CDR communication and tower connection edges
    - Builds document co-mention edges
    - Cross-links across existing cases
    """
    try:
        content = await file.read()
        payload = json.loads(content.decode("utf-8"))
        stats = engine.ingest_payload(payload, execute_in_neo4j=neo4j_client.is_connected)
        logger.info(f"Ingested {file.filename}: {stats}")
        return {
            "status": "success",
            "filename": file.filename,
            "ingested_stats": stats
        }
    except Exception as e:
        logger.error(f"Error ingesting case file {file.filename}: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/export/cypher", response_class=PlainTextResponse, summary="Export Cypher Migration Script")
async def export_cypher_script():
    """Returns pure Cypher MERGE statements to populate any Neo4j instance directly."""
    return engine.export_cypher()


@router.post("/cypher", summary="Execute Custom Cypher Query")
async def execute_cypher(req: CypherRequest):
    """Runs a read query against the live Neo4j database."""
    if not neo4j_client.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not connected. In-memory engine is active."
        )
    try:
        results = neo4j_client.execute_read(req.query, req.params or {})
        return {"status": "success", "records": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reset", summary="Clear Graph Engine")
async def reset_graph():
    """Resets in-memory graph and purges Neo4j database."""
    engine.clear()
    if neo4j_client.is_connected:
        neo4j_client.execute_write("MATCH (n) DETACH DELETE n")
    return {"status": "cleared"}


@router.get("/status", summary="Check Neo4j Engine Status")
async def get_neo4j_status():
    """Returns connection state and active database mode."""
    return {
        "connected": neo4j_client.is_connected,
        "uri": settings.neo4j_uri,
        "database": settings.neo4j_database,
        "mode": "live_neo4j" if neo4j_client.is_connected else "in_memory_engine"
    }
