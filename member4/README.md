# Knowledge Graph Backend Module (SFIC / ATLAS)

Ready-to-use FastAPI package for knowledge graph entity extraction, cross-case interlinking, and visualization data serving.

---

## 1. Quick Integration (2 Lines of Code)

Mount the router directly into your main FastAPI application (`main.py`):

```python
from fastapi import FastAPI, Depends
from backend.router import router as graph_router

# Import your RBAC and logging dependencies
# from auth.rbac import require_permission, log_audit_trail

app = FastAPI(title="Investigation Portal API")

# Mount graph endpoints with your RBAC and logging:
app.include_router(
    graph_router,
    # prefix is already "/api/graph" inside router.py
    # dependencies=[Depends(require_permission("graph:read")), Depends(log_audit_trail)]
)
```

---

## 2. Dependencies

Add these to your project's `requirements.txt`:

```text
fastapi>=0.110.0
uvicorn>=0.28.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
python-multipart>=0.0.9
networkx>=3.2.1
neo4j>=5.18.0
```

Install:
```bash
pip install -r requirements.txt
```

---

## 3. Environment Variables (Optional)

Configure in `.env` or system environment variables:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Connection URI |
| `NEO4J_USERNAME` | `neo4j` | Database username |
| `NEO4J_PASSWORD` | `password` | Database password |
| `NEO4J_DATABASE` | `neo4j` | Database name |

> **Note:** If Neo4j is offline or unavailable, the module **automatically falls back to its built-in in-memory engine**. It will NOT crash your backend server.

---

## 4. API Endpoints & RBAC Mapping

| Method | Endpoint | Description | Recommended RBAC Permission |
| :--- | :--- | :--- | :--- |
| **GET** | `/api/graph` | Returns nodes and edges filtered by degree $\ge 1$. Flags cross-case bridge entities with `cross_case: true`. | `graph:read` (Investigator, Analyst, Admin) |
| **POST** | `/api/graph/upload` | Ingests case JSON file via multipart form. Extracts Persons, Phones, Vehicles, IMEIs, Cell Towers, Bank Accounts, CDRs, and document mentions. | `case:upload` / `graph:write` (Investigator, Admin) |
| **GET** | `/api/graph/export/cypher` | Generates complete Cypher migration script for Neo4j. | `graph:export` (Analyst, Admin) |
| **POST** | `/api/graph/cypher` | Executes raw Cypher query against live Neo4j DB. Body: `{"query": "MATCH (n) RETURN n LIMIT 10"}`. | `graph:admin` (Super Admin) |
| **POST** | `/api/graph/reset` | Purges in-memory graph and deletes Neo4j records. | `graph:admin` (Super Admin) |
| **GET** | `/api/graph/status` | Health check returning Neo4j connection state and engine mode. | Public / `health:read` |

---

## 5. Testing with Sample Data

You can immediately test the upload route via Swagger UI (`/docs`) or curl:

```bash
curl -X POST "http://localhost:8000/api/graph/upload" \
  -F "file=@sample_data/case_001.json"
```

And view the extracted graph:
```bash
curl "http://localhost:8000/api/graph"
```
