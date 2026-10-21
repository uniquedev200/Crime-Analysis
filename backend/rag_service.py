import logging
from typing import List, Dict, Any, Optional
from upstash_vector import Index
from backend.config import settings

logger = logging.getLogger("atlas.rag")

class RagService:
    def __init__(self):
        self.index: Optional[Index] = None
        self._init_index()

    def _init_index(self):
        try:
            if settings.upstash_url and settings.upstash_token:
                self.index = Index(url=settings.upstash_url, token=settings.upstash_token)
                logger.info("Upstash Vector initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not connect to Upstash Vector: {e}. Semantic RAG will use fallback.")
            self.index = None

    def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        """
        Upsert evidence chunks into Upstash Vector.
        Each item in chunks: {"id": str, "data": str (text content to embed), "metadata": dict}
        """
        if not self.index or not chunks:
            return
        try:
            from upstash_vector import Vector
            vectors = []
            for c in chunks:
                vectors.append(Vector(
                    id=str(c["id"]),
                    data=str(c.get("data") or c.get("text", "")),
                    metadata=c.get("metadata", {})
                ))
            # Batch upsert in groups of 50
            for i in range(0, len(vectors), 50):
                batch = vectors[i:i+50]
                self.index.upsert(vectors=batch)
            logger.info(f"Upserted {len(chunks)} vectors to Upstash.")
        except Exception as e:
            logger.error(f"Error upserting vectors to Upstash: {e}")

    def query(self, query_text: str, case_id: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Perform semantic similarity search against Upstash Vector.
        """
        if not self.index:
            return []
        try:
            filter_expr = f"case_id = '{case_id}'" if case_id else None
            results = self.index.query(
                data=query_text,
                top_k=top_k,
                include_metadata=True,
                include_data=True,
                filter=filter_expr
            )
            hits = []
            for r in results:
                hits.append({
                    "id": r.id,
                    "score": r.score,
                    "data": r.data,
                    "metadata": r.metadata
                })
            return hits
        except Exception as e:
            logger.warning(f"Error querying Upstash Vector: {e}")
            return []

rag_service = RagService()
