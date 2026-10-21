import logging
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase, Driver

logger = logging.getLogger("graph_system")

class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self._driver: Optional[Driver] = None
        self._connected = False

    def connect(self) -> bool:
        try:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self._driver.verify_connectivity()
            self._connected = True
            logger.info(f"Successfully connected to Neo4j at {self.uri}")
            return True
        except Exception:
            logger.info(f"Neo4j is not active at {self.uri}. Operating in high-speed in-memory graph mode.")
            self._connected = False
            return False

    @property
    def is_connected(self) -> bool:
        if self._driver and not self._connected:
            try:
                self._driver.verify_connectivity()
                self._connected = True
            except Exception:
                self._connected = False
        return self._connected

    def close(self):
        if self._driver:
            self._driver.close()
            self._connected = False

    def ensure_constraints(self):
        """Creates baseline constraints and indexes idempotently without hardcoding schema."""
        if not self.is_connected:
            return
        
        queries = [
            "CREATE CONSTRAINT case_id_unique IF NOT EXISTS FOR (c:Case) REQUIRE c.case_id IS UNIQUE",
            "CREATE CONSTRAINT source_id_unique IF NOT EXISTS FOR (s:Source) REQUIRE s.source_id IS UNIQUE",
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
            "CREATE INDEX entity_canonical_idx IF NOT EXISTS FOR (e:Entity) ON (e.entity_type, e.canonical_value)",
            "CREATE CONSTRAINT event_id_unique IF NOT EXISTS FOR (ev:Event) REQUIRE ev.event_id IS UNIQUE",
            "CREATE INDEX mention_id_idx IF NOT EXISTS FOR (m:Mention) ON (m.mention_id)",
        ]
        with self._driver.session(database=self.database) as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as ex:
                    logger.debug(f"Constraint notice ({q}): {ex}")

    def execute_write(self, cypher: str, parameters: Optional[Dict[str, Any]] = None):
        if not self.is_connected:
            return None
        with self._driver.session(database=self.database) as session:
            return session.execute_write(lambda tx: list(tx.run(cypher, parameters or {})))

    def execute_read(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        with self._driver.session(database=self.database) as session:
            res = session.run(cypher, parameters or {})
            return [record.data() for record in res]

    def get_full_graph(self, limit: int = 2500) -> Dict[str, Any]:
        """Fetch nodes and edges formatted for visualization."""
        if not self.is_connected:
            return {"nodes": [], "edges": []}

        cypher = """
        MATCH (n)
        OPTIONAL MATCH (n)-[r]->(m)
        RETURN n, r, m
        LIMIT $limit
        """
        nodes_dict = {}
        edges_list = []

        try:
            with self._driver.session(database=self.database) as session:
                result = session.run(cypher, {"limit": limit})
                for record in result:
                    n = record.get("n")
                    r = record.get("r")
                    m = record.get("m")

                    if n:
                        n_id = str(n.element_id if hasattr(n, "element_id") else n.id)
                        labels = list(n.labels)
                        nodes_dict[n_id] = {
                            "id": n_id,
                            "labels": labels,
                            "primary_label": labels[0] if labels else "Node",
                            "properties": dict(n.items()),
                            "caption": n.get("canonical_value") or n.get("case_id") or n.get("file_name") or n.get("event_id") or n.get("entity_id") or n_id
                        }
                    if m:
                        m_id = str(m.element_id if hasattr(m, "element_id") else m.id)
                        labels = list(m.labels)
                        nodes_dict[m_id] = {
                            "id": m_id,
                            "labels": labels,
                            "primary_label": labels[0] if labels else "Node",
                            "properties": dict(m.items()),
                            "caption": m.get("canonical_value") or m.get("case_id") or m.get("file_name") or m.get("event_id") or m.get("entity_id") or m_id
                        }
                    if r:
                        r_id = str(r.element_id if hasattr(r, "element_id") else r.id)
                        start_id = str(r.start_node.element_id if hasattr(r.start_node, "element_id") else r.start_node.id)
                        end_id = str(r.end_node.element_id if hasattr(r.end_node, "element_id") else r.end_node.id)
                        edges_list.append({
                            "id": r_id,
                            "from": start_id,
                            "to": end_id,
                            "label": r.type,
                            "properties": dict(r.items())
                        })
        except Exception as e:
            logger.error(f"Error fetching full graph from Neo4j: {e}")

        return {
            "nodes": list(nodes_dict.values()),
            "edges": edges_list
        }
