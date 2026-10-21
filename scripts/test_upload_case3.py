import requests
import os
import time
from pathlib import Path

folder = Path(r"C:\Users\suraj\Downloads\Updated dataset\CASE_003")
files = sorted(list(folder.glob("*.*")))
print(f"Found {len(files)} files in {folder}")

# 1. Reset / ensure case exists
requests.post("http://127.0.0.1:8000/api/cases", json={
    "case_id": "CASE_003",
    "case_name": "Nandipur Cargo Diversion Case 003",
    "lead_investigator": "Lead Inspector",
    "crime_category": "Cargo Theft & Syndicate Diversion"
})

t0 = time.time()
uploaded = 0
for f in files:
    if f.suffix.lower() not in (".pdf", ".xlsx", ".csv", ".json", ".png", ".jpg"):
        continue
    with open(f, "rb") as fp:
        resp = requests.post(
            "http://127.0.0.1:8000/api/evidence/upload",
            data={"case_id": "CASE_003", "uploader": "TestRunner"},
            files={"file": (f.name, fp, "application/octet-stream")}
        )
        if resp.status_code == 200:
            uploaded += 1
            classification = resp.json().get("job_classification")
            mentions = resp.json().get("mention_count", 0)
            print(f" [OK] {f.name} -> {classification} ({mentions} mentions)")
        else:
            print(f" [ERR {resp.status_code}] {f.name}: {resp.text[:150]}")

total_time = time.time() - t0
print(f"\nUploaded {uploaded} files in {total_time:.2f}s! (Avg: {total_time/max(1, uploaded):.2f}s per file)")

# 2. Check Graph
g_resp = requests.get("http://127.0.0.1:8000/api/graph?case_id=CASE_003")
if g_resp.status_code == 200:
    g = g_resp.json()
    print(f"\n--- Knowledge Graph Explorer (CASE_003) ---")
    print(f"Total Nodes: {g.get('total_nodes')}")
    print(f"Total Edges: {g.get('total_edges')}")
    edge_types = set(e.get("type") for e in g.get("edges", []))
    print(f"Edge Types: {edge_types}")
    node_labels = set(lbl for n in g.get("nodes", []) for lbl in n.get("labels", []))
    print(f"Node Labels: {node_labels}")

# 3. Check Case Details
c_resp = requests.get("http://127.0.0.1:8000/api/cases/CASE_003")
if c_resp.status_code == 200:
    c = c_resp.json()
    print(f"\n--- Case Summary ---")
    print(f"Total Entities in DB: {c.get('total_entities')}")
    print(f"Primary Suspect: {c.get('primary_suspect')}")
    print(f"Evidence Files: {len(c.get('evidences', []))}")
    print(f"Overlapping Cases: {c.get('overlapping_cases')}")

# 4. Check Pattern Insights
i_resp = requests.get("http://127.0.0.1:8000/api/cases/CASE_003/insights")
if i_resp.status_code == 200:
    insights = i_resp.json()
    print(f"\n--- Pattern Insights ({len(insights)} detected) ---")
    for ins in insights:
        print(f" - [{ins.get('severity')}] {ins.get('title')}: {ins.get('description')[:100]}...")
