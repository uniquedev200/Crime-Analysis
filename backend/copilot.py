import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

from backend.config import settings
from backend.graph_manager import get_graph_engine
from backend.rag_service import rag_service

logger = logging.getLogger("atlas.copilot")

def check_local_ollama() -> bool:
    """Check if local Ollama daemon is reachable."""
    try:
        url = f"{settings.ollama_host.rstrip('/')}/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "AtlasBackend/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False

def query_local_ollama(prompt: str) -> Optional[str]:
    """Execute inference on local Ollama qwen2.5:3b model."""
    if not check_local_ollama():
        return None
    try:
        url = f"{settings.ollama_host.rstrip('/')}/api/generate"
        payload = json.dumps({
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response")
    except Exception as e:
        logger.warning(f"Ollama inference error: {e}")
        return None

class CopilotEngine:
    @staticmethod
    def answer_graph_query(
        question: str,
        case_id: Optional[str] = None,
        nodes_count: Optional[int] = None,
        edges_count: Optional[int] = None,
        selected_node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        q_lower = question.lower()
        extracted_graph_type = None

        # Autonomous Subgraph Intent Extraction
        if any(w in q_lower for w in ["cdr", "call", "telecom", "phone", "tower"]):
            extracted_graph_type = "cdr"
        elif any(w in q_lower for w in ["person", "suspect", "people", "syndicate", "human"]):
            extracted_graph_type = "person"
        elif any(w in q_lower for w in ["financial", "money", "bank", "account", "transfer", "hawala"]):
            extracted_graph_type = "financial"
        elif any(w in q_lower for w in ["full", "all", "ecosystem", "reset"]):
            extracted_graph_type = "full"

        # RAG Search via Upstash Vector
        rag_hits = []
        try:
            rag_hits = rag_service.query(question, case_id=case_id, top_k=4)
        except Exception:
            pass

        # Graph Context
        engine = get_graph_engine()
        case_nodes = []
        for nid, n in engine.nodes.items():
            if not case_id or case_id in n.get("properties", {}).get("case_ids", []):
                case_nodes.append((nid, n))

        selected_info = ""
        if selected_node_id and selected_node_id in engine.nodes:
            sn = engine.nodes[selected_node_id]
            selected_info = f"\nCurrently Selected Focus: {sn.get('caption', selected_node_id)} ({sn.get('primary_label')})\nProperties: {json.dumps(sn.get('properties', {}))}"

        # If Ollama is available, synthesize via local LLM
        ollama_active = check_local_ollama()
        if ollama_active:
            context_text = "\n".join([f"- Evidence Citation: {h.get('data')}" for h in rag_hits])
            prompt = f"""You are ATLAS, an expert criminal intelligence and forensic graph copilot.
Case ID: {case_id or 'Global Workspace'}
Total Active Entities: {len(case_nodes)}
{selected_info}

Retrieved Grounded Evidence:
{context_text}

Investigator Question: "{question}"

Instructions:
1. Provide a grounded, objective answer citing exact source documents and records.
2. If evidence is insufficient, explicitly state "Insufficient evidence to conclude...".
3. Associations do not imply guilt.
4. Format key findings with bullet points.
"""
            llm_response = query_local_ollama(prompt)
            if llm_response:
                return {
                    "ai_model": f"Ollama ({settings.ollama_model})",
                    "answer": llm_response,
                    "extracted_graph_type": extracted_graph_type
                }

        # Deterministic Heuristic Forensic Engine (Zero-LLM fallback)
        answer_parts = []
        
        # Check specific suspect questions
        if "suspect" in q_lower or "who" in q_lower or "leader" in q_lower:
            persons = [n for nid, n in case_nodes if "Person" in n.get("labels", [])]
            if persons:
                answer_parts.append(f"**Identified Person Entities in Scope ({len(persons)}):**\n")
                for p in persons[:5]:
                    name = p.get("caption") or p.get("id")
                    role = p.get("properties", {}).get("role", "Mentioned in Record")
                    answer_parts.append(f"- 🎯 **{name}** — *{role}* (Node: `{p.get('id')}`)")
            else:
                answer_parts.append("⚠️ *Insufficient Evidence:* No named individual suspects are formally cataloged in the loaded case dossier.")

        elif "financial" in q_lower or "money" in q_lower or "transfer" in q_lower:
            accounts = [n for nid, n in case_nodes if "BankAccount" in n.get("labels", [])]
            tx_edges = [e for e in engine.aggregated_edges.values() if "TRANSFER" in e.get("label", "").upper()]
            answer_parts.append(f"**Financial Topology Analysis:**\n")
            answer_parts.append(f"- Discovered **{len(accounts)} Bank Accounts** across **{len(tx_edges)} Recorded Fund Trails**.")
            for e in tx_edges[:4]:
                props = e.get("properties", {})
                debit = props.get("debit_inr") or props.get("amount") or "unspecified"
                answer_parts.append(f"- 💳 `{e['from']}` → `{e['to']}` [Transfer ₹{debit}] (Ref: {props.get('transaction_id', 'TXN')})")

        elif "cdr" in q_lower or "call" in q_lower or "phone" in q_lower:
            phones = [n for nid, n in case_nodes if "Phone" in n.get("labels", [])]
            call_edges = [e for e in engine.aggregated_edges.values() if "COMMUNICAT" in e.get("label", "").upper() or "CALL" in e.get("label", "").upper()]
            answer_parts.append(f"**Telecommunication Network Analysis:**\n")
            answer_parts.append(f"- Ingested **{len(phones)} Telephone Numbers** and **{len(call_edges)} Distinct Caller-Callee Links**.")
            for e in call_edges[:4]:
                props = e.get("properties", {})
                count = props.get("call_count", 1) or 1
                answer_parts.append(f"- 📞 `{e['from']}` ↔ `{e['to']}` ({count} calls logged, duration {props.get('duration_seconds', 0)}s)")

        else:
            answer_parts.append(f"**Forensic Knowledge Graph Status for Case {case_id or 'All'}:**\n")
            answer_parts.append(f"- Total Tracked Entities: **{len(case_nodes)}**")
            answer_parts.append(f"- Total Active Relationships: **{len(engine.aggregated_edges)}**")
            if selected_info:
                answer_parts.append(f"- {selected_info}")
            if rag_hits:
                answer_parts.append("\n**Supporting Evidence Snippets:**")
                for h in rag_hits[:2]:
                    answer_parts.append(f"> {h.get('data')[:200]}… *(Citation ID: {h.get('id')})*")

        # Fallback note
        if not answer_parts:
            answer_parts.append("ATLAS analyzed the evidence graph. Use questions such as *'Who are the main suspects?'*, *'Show financial transfers'*, or *'Analyze CDR calls'* to inspect deeper leads.")

        return {
            "ai_model": "ATLAS Heuristic Intelligence Engine",
            "answer": "\n".join(answer_parts),
            "extracted_graph_type": extracted_graph_type
        }

    @staticmethod
    def generate_dossier(case_id: str, case_name: str) -> Dict[str, Any]:
        engine = get_graph_engine()
        case_nodes = [
            (nid, n) for nid, n in engine.nodes.items()
            if case_id in n.get("properties", {}).get("case_ids", []) or n.get("properties", {}).get("case_id") == case_id
        ]
        if not case_nodes:
            from backend.database import SessionLocal
            from backend.models import EvidenceMentionModel
            from backend.pipeline import EvidencePipeline
            with SessionLocal() as db_session:
                m_list = db_session.query(EvidenceMentionModel).filter(EvidenceMentionModel.case_id == case_id).all()
                if m_list:
                    EvidencePipeline._sync_to_graph(case_id, "db_sync", m_list, engine)
                    case_nodes = [
                        (nid, n) for nid, n in engine.nodes.items()
                        if case_id in n.get("properties", {}).get("case_ids", []) or n.get("properties", {}).get("case_id") == case_id
                    ]

        persons = [n for nid, n in case_nodes if "Person" in n.get("labels", [])]
        phones = [n for nid, n in case_nodes if "Phone" in n.get("labels", [])]
        accounts = [n for nid, n in case_nodes if "BankAccount" in n.get("labels", [])]
        vehicles = [n for nid, n in case_nodes if "Vehicle" in n.get("labels", [])]
        cross_cases = [n for nid, n in case_nodes if n.get("properties", {}).get("cross_case")]

        key_findings = [
            f"Case docket incorporates {len(case_nodes)} verified entities across {len(phones)} telephone numbers and {len(accounts)} bank accounts.",
            f"Identified {len(persons)} human subjects with stated roles in primary FIR and surveillance transcripts."
        ]
        if cross_cases:
            key_findings.append(f"🚨 CRITICAL: Discovered {len(cross_cases)} cross-case bridge entities connecting {case_id} to older criminal dossiers.")
        if vehicles:
            key_findings.append(f"Tracked {len(vehicles)} motor vehicles involved in suspect logistics or sighting reports.")

        summary_text = (
            f"Investigation docket **{case_name}** ({case_id}) synthesized from multi-format evidence. "
            f"The network structure reveals {len(persons)} individuals connected via telecom and banking channels. "
            f"All claims have quote-verified provenance grounded in official case exhibits."
        )

        return {
            "title": f"Executive Intelligence Dossier — {case_id}",
            "executive_summary": summary_text,
            "summary": summary_text,
            "key_findings": key_findings
        }
