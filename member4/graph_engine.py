import re
import json
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict
try:
    from .neo4j_client import Neo4jClient
except (ImportError, ValueError):
    from neo4j_client import Neo4jClient

logger = logging.getLogger("graph_system")

def sanitize_label(name: str) -> str:
    if not name:
        return "Unknown"
    cleaned = re.sub(r"[^a-zA-Z0-9_]", " ", str(name))
    parts = cleaned.replace("_", " ").split()
    return "".join(p.capitalize() for p in parts) if parts else "Unknown"

def sanitize_rel_type(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", str(name).strip().upper())
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_") or "RELATED_TO"

def clean_prop_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    result = {}
    for k, v in data.items():
        clean_k = re.sub(r"[^a-zA-Z0-9_]", "_", str(k).strip())
        clean_k = re.sub(r"_+", "_", clean_k).strip("_")
        if not clean_k:
            clean_k = "attr"
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            result[clean_k] = v
        elif isinstance(v, list):
            if all(isinstance(x, (str, int, float, bool)) for x in v):
                result[clean_k] = v
            else:
                result[clean_k] = json.dumps(v)
        elif isinstance(v, dict):
            result[clean_k] = json.dumps(v)
        else:
            result[clean_k] = str(v)
    return result


class KnowledgeGraphEngine:
    def __init__(self, neo4j_client: Optional[Neo4jClient] = None):
        self.neo4j = neo4j_client
        self.nodes: Dict[str, Dict[str, Any]] = {}
        # We aggregate parallel edges so Phone A -> Phone B has ONE clean edge, not 36 overlapping edges!
        self.aggregated_edges: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    @property
    def edges(self) -> List[Dict[str, Any]]:
        return list(self.aggregated_edges.values())

    def clear(self):
        self.nodes.clear()
        self.aggregated_edges.clear()

    def add_node(self, node_id: str, labels: List[str], properties: Dict[str, Any], caption: Optional[str] = None, level: int = 2):
        clean_props = clean_prop_dict(properties)
        clean_props["id"] = node_id
        if node_id not in self.nodes:
            case_id = clean_props.get("case_id")
            fir_num = clean_props.get("fir_number")
            clean_props["case_ids"] = [case_id] if case_id else []
            clean_props["fir_numbers"] = [fir_num] if fir_num else []
            clean_props["cross_case"] = False
            ordered = []
            for l in labels:
                if l != "Entity" and l not in ordered:
                    ordered.append(l)
            if "Entity" in labels and "Entity" not in ordered:
                ordered.append("Entity")
            if not ordered:
                ordered = ["Entity"]

            self.nodes[node_id] = {
                "id": node_id,
                "labels": ordered,
                "primary_label": ordered[0] if ordered else "Node",
                "properties": clean_props,
                "caption": caption or clean_props.get("canonical_value") or clean_props.get("description") or node_id,
                "level": level
            }
        else:
            existing = self.nodes[node_id]
            for lbl in labels:
                if lbl not in existing["labels"]:
                    existing["labels"].append(lbl)

            existing_cases = list(existing["properties"].get("case_ids") or [])
            new_case = clean_props.get("case_id")
            if new_case and new_case not in existing_cases:
                existing_cases.append(new_case)

            existing_firs = list(existing["properties"].get("fir_numbers") or [])
            new_fir = clean_props.get("fir_number")
            if new_fir and new_fir not in existing_firs:
                existing_firs.append(new_fir)

            existing["properties"].update(clean_props)
            existing["properties"]["case_ids"] = existing_cases
            existing["properties"]["fir_numbers"] = existing_firs
            existing["properties"]["case_id"] = ", ".join(existing_cases)
            if existing_firs:
                existing["properties"]["fir_number"] = ", ".join(existing_firs)
            existing["properties"]["cross_case"] = len(existing_cases) > 1

            if caption:
                existing["caption"] = caption
            # Preserve topmost level
            if level < existing.get("level", 2):
                existing["level"] = level

    def add_or_update_edge(self, source_id: str, target_id: str, rel_type: str, edge_data: Dict[str, Any], display_label: Optional[str] = None):
        rel_type = sanitize_rel_type(rel_type)
        key = (source_id, target_id, rel_type)
        if key not in self.aggregated_edges:
            self.aggregated_edges[key] = {
                "id": f"e_{len(self.aggregated_edges)+1}",
                "from": source_id,
                "to": target_id,
                "label": rel_type,
                "display_label": display_label or rel_type.replace("_", "-").lower(),
                "count": 1,
                "properties": clean_prop_dict(edge_data),
                "items": [edge_data]
            }
        else:
            agg = self.aggregated_edges[key]
            agg["count"] += 1
            agg["items"].append(edge_data)
            # Update summary properties
            if "duration_seconds" in edge_data:
                try:
                    dur = int(edge_data.get("duration_seconds") or 0)
                    agg["properties"]["total_duration_seconds"] = agg["properties"].get("total_duration_seconds", 0) + dur
                except Exception:
                    pass
            if "debit_inr" in edge_data:
                try:
                    amt = float(edge_data.get("debit_inr") or 0)
                    agg["properties"]["total_amount_inr"] = agg["properties"].get("total_amount_inr", 0.0) + amt
                except Exception:
                    pass
            if display_label:
                agg["display_label"] = display_label
            else:
                agg["display_label"] = f"{rel_type.replace('_', '-').lower()} ({agg['count']}x)"

    def ingest_payload(self, payload: Dict[str, Any], execute_in_neo4j: bool = True) -> Dict[str, int]:
        stats = {
            "entities": 0,
            "events": 0,
            "records": 0,
            "relationships": 0
        }

        # 1. Case Metadata (stored as node attributes, Case is NOT an entity node)
        case_data = payload.get("case") or {}
        case_id = case_data.get("case_id") or "CASE_UNKNOWN"
        fir_number = case_data.get("fir_number") or ""
        police_station = case_data.get("police_station") or ""
        reg_date = case_data.get("registration_date") or ""

        case_meta = {
            "case_id": case_id,
            "fir_number": fir_number,
            "police_station": police_station,
            "registration_date": reg_date
        }

        entity_id_map: Dict[str, str] = {}
        canonical_lookup: Dict[Tuple[str, str], str] = {}
        source_entities_map: Dict[str, Set[str]] = defaultdict(set)

        # 2. Ingest Resolved Entities with Clean Layer Assignment
        # Layer 1 (Top): Persons
        # Layer 2 (Middle): Phones, Bank Accounts, Vehicles
        # Layer 3 (Bottom): IMEIs, Cell Towers
        resolved_entities = payload.get("resolved_entities") or []
        for ent in resolved_entities:
            raw_ent_id = ent.get("entity_id")
            ent_type = ent.get("entity_type", "entity").lower()
            canonical_val = str(ent.get("canonical_value") or raw_ent_id or "")

            global_ent_id = f"{ent_type}:{canonical_val}" if canonical_val else raw_ent_id
            entity_labels = ["Entity", sanitize_label(ent_type)]

            level = 2
            if ent_type == "person":
                level = 1
            elif ent_type in ("cell_tower", "imei"):
                level = 3

            ent_props = {
                "entity_id": raw_ent_id,
                "canonical_value": canonical_val,
                "entity_type": ent_type,
                "known_surface_forms": ent.get("known_surface_forms", []),
                **case_meta,
                **(ent.get("attributes") or {})
            }
            self.add_node(global_ent_id, entity_labels, ent_props, caption=canonical_val or raw_ent_id, level=level)
            entity_id_map[raw_ent_id] = global_ent_id
            canonical_lookup[(ent_type, canonical_val)] = global_ent_id
            stats["entities"] += 1

        # 3. Document-based Edges: Iterate through entity_mentions sharing the same source_id
        entity_mentions = payload.get("entity_mentions") or []
        for mention in entity_mentions:
            if not isinstance(mention, dict):
                continue
            s_id = mention.get("source_id")
            e_id = mention.get("entity_id")
            if s_id and e_id:
                resolved_node_id = entity_id_map.get(e_id)
                if resolved_node_id:
                    source_entities_map[s_id].add(resolved_node_id)

        # Also merge source_refs from resolved_entities if available
        for ent in resolved_entities:
            raw_id = ent.get("entity_id")
            resolved_node_id = entity_id_map.get(raw_id)
            if resolved_node_id:
                for s_ref in ent.get("source_refs") or []:
                    source_entities_map[s_ref].add(resolved_node_id)

        co_mentioned_pairs: Set[Tuple[str, str]] = set()
        for s_ref, ent_set in source_entities_map.items():
            if len(ent_set) < 2:
                continue
            ent_list = sorted(list(ent_set))
            persons = [e for e in ent_list if e.startswith("person:")]
            assets = [e for e in ent_list if not e.startswith("person:")]

            # Link persons to associated assets in same document (FIR, Seizure, Surveillance)
            for p in persons:
                for a in assets:
                    rel_name = "CO_MENTIONED"
                    disp = "co-mentioned"
                    if "vehicle" in a:
                        rel_name = "USES_VEHICLE"
                        disp = "uses-vehicle"
                    elif "imei" in a:
                        rel_name = "OPERATES_DEVICE"
                        disp = "operates-device"
                    elif "phone" in a:
                        rel_name = "USES_PHONE"
                        disp = "uses-phone"

                    self.add_or_update_edge(p, a, rel_name, {
                        "case_id": case_id,
                        "reference": s_ref
                    }, display_label=disp)
                    stats["relationships"] += 1
                    co_mentioned_pairs.add((p, a))

            # Link multiple persons co-mentioned in same document (e.g. Kiran Bose & The Person in witness statement)
            if len(persons) >= 2:
                for i in range(len(persons)):
                    for j in range(i + 1, len(persons)):
                        p1, p2 = persons[i], persons[j]
                        if (p1, p2) not in co_mentioned_pairs and (p2, p1) not in co_mentioned_pairs:
                            self.add_or_update_edge(p1, p2, "CO_MENTIONED", {
                                "case_id": case_id,
                                "reference": s_ref
                            }, display_label="co-mentioned")
                            stats["relationships"] += 1
                            co_mentioned_pairs.add((p1, p2))

        # 4. Events metadata (Timeline and milestone nodes removed from canvas per user specification)
        events = payload.get("events") or []
        stats["events"] = len(events)

        # 5. Ingest Structured Records with Clean Edge Aggregation
        structured_records = payload.get("structured_records") or {}
        for category, records in structured_records.items():
            if not isinstance(records, list):
                continue
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                stats["records"] += 1
                rel_count = self._process_record(category, rec, entity_id_map, canonical_lookup, case_meta)
                stats["relationships"] += rel_count

        if execute_in_neo4j and self.neo4j and self.neo4j.is_connected:
            self._sync_to_neo4j()

        return stats

    def _process_record(self, category: str, record: Dict[str, Any], 
                        entity_id_map: Dict[str, str], 
                        canonical_lookup: Dict[Tuple[str, str], str], 
                        case_meta: Dict[str, Any]) -> int:
        rels_created = 0
        rec_id = record.get("Record ID") or record.get("transaction_id") or record.get("id")
        case_id = case_meta.get("case_id", "")

        # Telecommunications / CDR pattern: Prioritize normalized columns and exclude LRN
        a_party = record.get("Target / A-Party Number_normalized") or record.get("Target / A-Party Number")
        b_party = record.get("B Party Number_normalized") or record.get("B Party Number")

        if not a_party or not b_party:
            for k, v in record.items():
                if not v or "lrn" in k.lower():
                    continue
                k_lower = k.lower()
                if not a_party and ("target" in k_lower or "a-party" in k_lower or "a_party" in k_lower or "caller" in k_lower):
                    a_party = str(v).strip()
                elif not b_party and ("b party" in k_lower or "b-party" in k_lower or "b_party" in k_lower or "callee" in k_lower):
                    b_party = str(v).strip()

        imei_val = record.get("IMEI/ESN_normalized") or record.get("IMEI/ESN") or record.get("imei")
        cell_tower_val = record.get("First Cell Global ID (MCC/MNC/LAC/Site ID)") or record.get("First Cell Global ID") or record.get("cell_tower")

        if a_party and b_party:
            caller_node = canonical_lookup.get(("phone", a_party)) or f"phone:{a_party}"
            callee_node = canonical_lookup.get(("phone", b_party)) or f"phone:{b_party}"

            self.add_node(caller_node, ["Entity", "Phone"], {"canonical_value": a_party, "entity_type": "phone", **case_meta}, caption=a_party, level=2)
            self.add_node(callee_node, ["Entity", "Phone"], {"canonical_value": b_party, "entity_type": "phone", **case_meta}, caption=b_party, level=2)

            call_props = {
                "call_type": record.get("Call Type (In/Out)"),
                "duration_seconds": record.get("Call Duration (second)"),
                "call_date": record.get("Call date"),
                "call_time": record.get("Call Initiation Time (CIT)"),
                "service_type": record.get("Service Type"),
                "record_id": rec_id,
                "case_id": case_id
            }
            direction = str(record.get("Call Type (In/Out)", "Out")).strip().lower()
            
            # Aggregate parallel calls between the same two phones into ONE clean edge!
            if direction == "in":
                self.add_or_update_edge(callee_node, caller_node, "COMMUNICATED_WITH", call_props, display_label="communicates-with")
            else:
                self.add_or_update_edge(caller_node, callee_node, "COMMUNICATED_WITH", call_props, display_label="communicates-with")
            rels_created += 1

            if imei_val and imei_val != "NOT_APPLICABLE":
                imei_node = canonical_lookup.get(("imei", str(imei_val))) or f"imei:{imei_val}"
                self.add_node(imei_node, ["Entity", "Imei"], {"canonical_value": str(imei_val), "entity_type": "imei", **case_meta}, caption=str(imei_val), level=3)
                self.add_or_update_edge(caller_node, imei_node, "OPERATED_ON_DEVICE", {"record_id": rec_id, "case_id": case_id}, display_label="operated-device")
                rels_created += 1

            if cell_tower_val and cell_tower_val != "NOT_APPLICABLE":
                tower_node = canonical_lookup.get(("cell_tower", str(cell_tower_val))) or f"cell_tower:{cell_tower_val}"
                self.add_node(tower_node, ["Entity", "CellTower"], {"canonical_value": str(cell_tower_val), "entity_type": "cell_tower", **case_meta}, caption=str(cell_tower_val), level=3)
                self.add_or_update_edge(caller_node, tower_node, "CONNECTED_TO_TOWER", {
                    "location": record.get("First BTS location"),
                    "record_id": rec_id,
                    "case_id": case_id
                }, display_label="connected-tower")
                rels_created += 1

        # Financial Transactions pattern
        acc_num = record.get("account_number") or record.get("account_number_normalized")
        counterparty_acc = record.get("counterparty_account") or record.get("counterparty_account_normalized")
        counterparty_name = record.get("counterparty_name_recorded")

        if acc_num:
            acc_num = str(acc_num).strip()
            src_acc_node = canonical_lookup.get(("bank_account", acc_num)) or f"bank_account:{acc_num}"
            self.add_node(src_acc_node, ["Entity", "BankAccount"], {"canonical_value": acc_num, "entity_type": "bank_account", **case_meta}, caption=acc_num, level=2)

            txn_props = {
                "transaction_id": rec_id,
                "booking_time": record.get("booking_time_ist"),
                "value_date": record.get("value_date"),
                "channel": record.get("channel"),
                "narration": record.get("narration"),
                "debit_inr": record.get("debit_inr"),
                "credit_inr": record.get("credit_inr"),
                "reference_number": record.get("reference_number"),
                "case_id": case_id
            }

            if counterparty_acc and counterparty_acc not in ("NOT_RECORDED", "NOT_APPLICABLE", ""):
                dst_acc = str(counterparty_acc).strip()
                dst_acc_node = canonical_lookup.get(("bank_account", dst_acc)) or f"bank_account:{dst_acc}"
                self.add_node(dst_acc_node, ["Entity", "BankAccount"], {"canonical_value": dst_acc, "entity_type": "bank_account", **case_meta}, caption=dst_acc, level=2)

                debit_amt = float(record.get("debit_inr") or 0)
                if debit_amt > 0:
                    self.add_or_update_edge(src_acc_node, dst_acc_node, "TRANSFERRED_FUNDS", txn_props, display_label="transferred-funds")
                else:
                    self.add_or_update_edge(dst_acc_node, src_acc_node, "TRANSFERRED_FUNDS", txn_props, display_label="transferred-funds")
                rels_created += 1

            elif counterparty_name and counterparty_name not in ("NOT_RECORDED", "NOT_APPLICABLE", ""):
                person_node = canonical_lookup.get(("person", counterparty_name)) or f"person:{counterparty_name}"
                self.add_node(person_node, ["Entity", "Person"], {"canonical_value": counterparty_name, "entity_type": "person", **case_meta}, caption=counterparty_name, level=1)
                self.add_or_update_edge(src_acc_node, person_node, "FINANCIAL_TRANSACTION_WITH", txn_props, display_label="transacted-with")
                rels_created += 1

        return rels_created

    def export_cypher(self) -> str:
        lines = [
            "// ==============================================",
            "// AUTO-GENERATED NEO4J GRAPH INGESTION SCRIPT",
            "// ==============================================",
            "",
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;",
            "CREATE INDEX entity_canon_idx IF NOT EXISTS FOR (e:Entity) ON (e.entity_type, e.canonical_value);",
            ""
        ]

        lines.append("// 2. MERGE NODES")
        for n_id, n in self.nodes.items():
            props_json = json.dumps(n["properties"])
            lines.append(f"MERGE (n:`{n['labels'][0]}` {{id: '{n_id}'}})")
            if len(n["labels"]) > 1:
                extra_labels = ":".join([f"`{lbl}`" for lbl in n["labels"][1:]])
                lines.append(f"SET n:{extra_labels}")
            lines.append(f"SET n += {props_json};")

        lines.append("\n// 3. MERGE RELATIONSHIPS")
        for e in self.aggregated_edges.values():
            rel_type = e["label"]
            props_json = json.dumps(e["properties"])
            lines.append(
                f"MATCH (a {{id: '{e['from']}'}}), (b {{id: '{e['to']}'}})\n"
                f"MERGE (a)-[r:`{rel_type}`]->(b)\n"
                f"SET r += {props_json};"
            )

        return "\n".join(lines)

    def _sync_to_neo4j(self):
        if not self.neo4j or not self.neo4j.is_connected:
            return

        self.neo4j.ensure_constraints()
        node_batch = [{"id": n_id, "labels": n["labels"], "props": n["properties"]} for n_id, n in self.nodes.items()]
        node_cypher = """
        UNWIND $batch AS item
        MERGE (n {id: item.id})
        SET n += item.props
        RETURN count(*)
        """
        try:
            self.neo4j.execute_write(node_cypher, {"batch": node_batch})
        except Exception as e:
            logger.error(f"Error syncing nodes to Neo4j: {e}")

        edge_batch = [{"from": e["from"], "to": e["to"], "type": e["label"], "props": e["properties"]} for e in self.aggregated_edges.values()]
        for e in edge_batch:
            cypher = f"""
            MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
            MERGE (a)-[r:`{e['type']}`]->(b)
            SET r += $props
            """
            try:
                self.neo4j.execute_write(cypher, {"from_id": e["from"], "to_id": e["to"], "props": e["props"]})
            except Exception as ex:
                logger.debug(f"Failed to write relationship {e['type']}: {ex}")

    def get_graph_data(self, filter_isolated: bool = True) -> Dict[str, Any]:
        """
        Returns clean, non-overlapping graph representation.
        Removes Case and Source document nodes.
        Filters out isolated nodes (degree == 0).
        Aggregates parallel edges into single clean directional relationships.
        """
        candidate_nodes = {}
        excluded_labels = {"Source", "Case", "Mention", "Timeline", "Event", "Milestone"}
        for n_id, node in self.nodes.items():
            labels = node.get("labels", [])
            # Exclude non-entity nodes (Source, Case, Mention, Timeline, Event, Milestone)
            if not any(lbl in excluded_labels for lbl in labels):
                candidate_nodes[n_id] = node

        connected_edges = []
        for edge in self.aggregated_edges.values():
            if edge["from"] in candidate_nodes and edge["to"] in candidate_nodes:
                connected_edges.append(edge)

        degree_map: Dict[str, int] = defaultdict(int)
        for edge in connected_edges:
            degree_map[edge["from"]] += 1
            degree_map[edge["to"]] += 1

        final_nodes = []
        for n_id, node in candidate_nodes.items():
            deg = degree_map.get(n_id, 0)
            if filter_isolated and deg == 0:
                continue
            node_copy = dict(node)
            node_copy["degree"] = deg
            final_nodes.append(node_copy)

        return {
            "summary": {
                "total_nodes": len(final_nodes),
                "total_edges": len(connected_edges),
                "entity_types": list(set([lbl for n in final_nodes for lbl in n["labels"]])),
                "relationship_types": list(set([e["label"] for e in connected_edges]))
            },
            "nodes": final_nodes,
            "edges": connected_edges
        }
