import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add member4 and member3 to sys.path so graph imports resolve cleanly
MEMBER4_PATH = Path(__file__).resolve().parent.parent / "member4"
MEMBER3_PATH = Path(__file__).resolve().parent.parent / "member3"
if str(MEMBER4_PATH) not in sys.path:
    sys.path.insert(0, str(MEMBER4_PATH))
if str(MEMBER3_PATH) not in sys.path:
    sys.path.insert(0, str(MEMBER3_PATH))

try:
    from member4.graph_engine import KnowledgeGraphEngine
    from member4.neo4j_client import Neo4jClient
except ImportError:
    try:
        from graph_engine import KnowledgeGraphEngine
        from neo4j_client import Neo4jClient
    except ImportError:
        from member3.graph_engine import KnowledgeGraphEngine
        from member3.neo4j_client import Neo4jClient

from backend.config import settings

logger = logging.getLogger("atlas.graph_manager")

# Initialize Neo4j client (falls back to memory if offline)
neo4j_client = Neo4jClient(
    uri=settings.neo4j_uri,
    user=settings.neo4j_user,
    password=settings.neo4j_password,
    database=settings.neo4j_database
)
try:
    neo4j_client.connect()
except Exception:
    logger.info("Neo4j offline; running in-memory Knowledge Graph Engine.")

# Shared KnowledgeGraphEngine instance
graph_engine = KnowledgeGraphEngine(neo4j_client=neo4j_client)

def get_graph_engine() -> KnowledgeGraphEngine:
    return graph_engine
