# ATLAS — Criminal Intelligence & Forensic Network Analysis System

**ATLAS** is an advanced, enterprise-grade criminal investigation and link-analysis intelligence platform. It ingests complex, multi-source, multi-format investigative evidence (scanned PDF FIRs, Call Detail Records (CDRs), bank transaction spreadsheets, cell tower location logs, and field reports), deterministically extracts and normalizes entities, computes provenance citations, detects cross-case overlaps, and visualizes criminal syndicates via an interactive knowledge graph with an autonomous AI copilot.

---

## 🏗️ System Architecture & Integrated Modules

```
+-----------------------------------------------------------------------------------------+
|                        MEMBER 1: FRONTEND & INVESTIGATION WORKSPACE                     |
|      React 19 | TypeScript | Vite | Vis.js Network Studio | ForceAtlas2 | Responsive    |
+-----------------------------------------------------------------------------------------+
                                             ▲
                                             │ HTTP REST / WebSocket (/api/*)
                                             ▼
+-----------------------------------------------------------------------------------------+
|                MEMBER 2: BACKEND, DATABASE & APPLICATION CORE (THIS SERVICE)            |
|       FastAPI App | PostgreSQL (Supabase) | Upstash Vector | JWT RBAC | Audit Ledger    |
+-----------------------------------------------------------------------------------------+
       │                                     │                                    │
       ▼                                     ▼                                    ▼
+-----------------------+   +---------------------------------+   +-----------------------+
|  MEMBER 3: EXTRACTION |   |  MEMBER 4: KNOWLEDGE GRAPH      |   |  MEMBER 5: AI COPILOT |
|  SFIC Document Module |   |  KnowledgeGraphEngine, Neo4j,   |   |  Vector RAG Search,   |
|  Dual-Path OCR & YAML,|   |  In-Memory Fast Engine,         |   |  Natural Language     |
|  Provenance Quotation,|   |  Centrality (PageRank/Between), |   |  Graph Inferences,    |
|  Anti-Prompt-Injection|   |  Cypher Script Exporters        |   |  Dossier Generation   |
+-----------------------+   +---------------------------------+   +-----------------------+
```

---

## 🚀 Setup & Installation Instructions

Follow these step-by-step instructions to set up, configure, and launch ATLAS locally or on a server.

### 1. Prerequisites
Ensure you have the following installed on your system:
- **Python 3.10+** (Tested on Python 3.11 and 3.13)
- **Node.js 18+** and **npm** (Required to compile frontend assets)
- **Git**
- *(Optional)* **Tesseract OCR** (If processing raw scanned images offline without cloud OCR)
- *(Optional)* **Neo4j 5+** (Optional: the backend automatically uses its high-performance in-memory graph engine if Neo4j is offline)
- *(Optional)* **Ollama** (If running offline local LLMs such as `qwen2.5:3b`)

---

### 2. Clone the Repository

```bash
git clone https://github.com/uniquedev200/Crime-Analysis.git
cd Crime-Analysis
```

---

### 3. Configure Environment Variables

Copy the sample environment file to create your local `.env`:

```bash
# On Linux / macOS:
cp .env.example .env

# On Windows (PowerShell):
Copy-Item .env.example .env
```

Open `.env` in your text editor and configure your secrets and services:

```ini
# General Runtime
ENVIRONMENT=development
SECRET_KEY=your_secure_jwt_random_secret_here

# PostgreSQL / Supabase Connection
DATABASE_URL=postgresql://user:password@host:5432/dbname
SUPABASE_PASSWORD=your_database_password

# Upstash Vector (For forensic document RAG)
UPSTASH_URL=https://your-database-id-vector.upstash.io
UPSTASH_TOKEN=your_upstash_token_here

# LLM Extraction Provider (Groq, OpenAI, or Mock)
GROQ_API_KEY=gsk_your_groq_api_key
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-20b

# Graph & Pipeline Configuration
SEED_SAMPLE_DATA=false
ATLAS_SYNTHETIC_ONLY=false
ATLAS_REQUIRE_TESSERACT=false
```

---

### 4. Set Up the Python Virtual Environment & Backend Dependencies

It is recommended to use a virtual environment:

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment:
# On Linux / macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# On Windows (Command Prompt):
.venv\Scripts\activate.bat
```

Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

---

### 5. Install Frontend Dependencies & Build Assets

The frontend is built with React 19, Vite, and Vis.js in the `member1` folder. Build the production bundle so FastAPI can serve it statically:

```bash
# Navigate to the frontend directory
cd member1

# Install node dependencies
npm install

# Build production assets (emits to member1/dist)
npm run build

# Return to root directory
cd ..
```

> **Note:** Once `npm run build` completes, the compiled bundle in `member1/dist` is automatically served directly by FastAPI at the root URL.

---

### 6. Run the Application

Start the unified backend and frontend server:

```bash
python run.py
```

Or using Uvicorn directly:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

### 7. Access the System

Once running:
- 🌐 **Web Application Portal:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- 📚 **Interactive Swagger API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 📖 **ReDoc API Documentation:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- ❤️ **Health Check Endpoint:** [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

## 🔐 Demo Officer Credentials

The database comes pre-configured with the following role-based access control (RBAC) officer credentials:

| Officer Name | Officer ID (Badge) | Passcode | Role & Clearance Level |
|---|---|---|---|
| **Inspector Vikram Rathore** | `IND-LE-8402` | `password123` | **Lead Detective** (Level 3 Clearance) |
| **Special Director Rajesh Sharma** | `ADMIN-001` | `admin123` | **Super Admin** (Level 4 Clearance) |
| **Intelligence Analyst Priya Sen** | `ANALYST-101` | `analyst123` | **Forensic Analyst** (Level 2 Clearance) |

---

## 🧪 Testing & Verification

Run the automated end-to-end integration test suite to verify extraction, hashing, quote provenance verification, and graph synchronization:

```bash
python scripts/test_pipeline.py
```

The automated test validates:
1. Ingestion of multi-page FIRs with SHA-256 evidence hashing and immutable receipt generation.
2. Deterministic zero-LLM spreadsheet parsing for Call Detail Records (CDRs) and Bank Transaction Statements.
3. Filtering and extraction gating preventing anomalous entities (`The Person`, `Service reversal`, `Ordinary business counterparty`).
4. Cross-case entity resolution detecting matches between independent cases.
5. Multi-hop Dijkstra shortest connection path tracing in the graph.
6. Merkle blockchain chain-of-custody verification.

---

## 📊 Key Platform Capabilities

### 1. Document Intelligence & Entity Extraction
- **Dual-Path Ingestion:** Spreadsheets and tabular logs (CDRs, bank statements, tower dumps) are parsed deterministically at zero LLM cost using YAML profile matching. Narratives (FIRs, inquiry notes) use nonce-fenced LLM extraction.
- **Quote-Verified Provenance:** Every single entity and relationship extracted from narrative text is mechanically verified against the verbatim quote in the source document. Hallucinations are automatically rejected.
- **Anomalous Entity Elimination:** Strict stopword and regex gating prevents bookkeeping labels, transaction descriptions, and preamble artifacts from polluting the graph.

### 2. Knowledge Graph Explorer & Visualizer
- **Hierarchical Swimlane Presentation:**
  - `Tier 1: Actors & Command` (Key operatives, persons, kingpins)
  - `Tier 2: Operations & Assets` (Bank accounts, burner phones, vehicles)
  - `Tier 3: Technical & Forensics` (Cell towers, IMEIs, physical locations)
- **Dynamic Filtering:** Instant subgraph toggling for `Full Ecosystem`, `CDR Telecom Only`, `Person Syndicate Only`, and `Financial Money Flows`.
- **Centrality Analytics:** Built-in calculation of PageRank, Betweenness Centrality, and Degree Centrality to identify ringleaders and bridge nodes.
- **Docked AI Copilot:** Integrated natural language investigative copilot supporting instant topology queries, money flow tracing, and syndicate summaries.

### 3. Forensic Integrity & Chain of Custody
- **Immutable Evidence Storage:** Raw bytes hashed with SHA-256 and stored in write-protected content-addressed storage.
- **Cryptographic Audit Ledger:** Tamper-evident Merkle tree blockchain recording all file uploads, officer access, and metadata modifications.
- **Certificate of Authenticity:** Instant export of court-admissible cryptographic chain-of-custody certificates.

---

## 📡 Core API Endpoints

| Category | Endpoint | Method | Description |
|---|---|---|---|
| **Health** | `/api/health` | `GET` | Service, database, and graph engine health status |
| **Auth** | `/api/auth/login` | `POST` | Officer login returning JWT bearer token |
| **Auth** | `/api/auth/me` | `GET` | Get current active officer profile and permissions |
| **Cases** | `/api/cases` | `GET` / `POST` | List all investigation cases or register a new case |
| **Cases** | `/api/cases/{case_id}` | `GET` | Comprehensive case overview and entity breakdown |
| **Cases** | `/api/cases/{case_id}/insights` | `GET` | 10 automated suspicious anomaly pattern detectors |
| **Cases** | `/api/cases/rankings` | `GET` | Graph centrality rankings (PageRank, Betweenness) |
| **Cases** | `/api/cases/shortest-path` | `GET` | Dijkstra multi-hop shortest connection path finder |
| **Evidence** | `/api/evidence/uploads` | `POST` | Multipart upload for PDF, CSV, XLSX, and TXT files |
| **Evidence** | `/api/evidence/{id}/original` | `GET` | Stream original evidence file (supports inline viewer) |
| **Graph** | `/api/graph` | `GET` | Fetch filtered network nodes and edges for Vis.js |
| **Graph** | `/api/graph/expand` | `GET` | Dynamic 1-hop neighbor expansion for selected node |
| **Graph** | `/api/graph/ai-query` | `POST` | LLM Graph Copilot for natural language topology Q&A |
| **Graph** | `/api/graph/export/cypher` | `GET` | Export live graph as standalone Neo4j Cypher script |
| **Integrity** | `/api/v1/blockchain/ledger` | `GET` | Inspect append-only cryptographic Merkle blocks |
| **Integrity** | `/api/v1/blockchain/verify-chain` | `GET` | Bit-level verification of entire chain-of-custody |
| **Canvases** | `/api/boards` | `GET` / `POST` | Investigator freeform pinning whiteboard canvases |

---

## 🛡️ License

This project was developed for the Smart India Hackathon (SIH) Forensic Intelligence track. All rights reserved.
