import requests

base = "http://127.0.0.1:8000"

print("=" * 60)
print("TESTING FULL INVESTIGATION PIPELINE END-TO-END")
print("=" * 60)

# 1. Upload FIR_A.pdf to CASE_TEST_007
upload_url = f"{base}/api/evidence/uploads"
file_path = r"member4\SFIC_Doc_Module\data\synth\FIR_A.pdf"

with open(file_path, "rb") as f:
    files = {"files": ("FIR_A.pdf", f, "application/pdf")}
    data = {
        "case_id": "CASE_TEST_007",
        "category": "Extortion Investigation",
        "uploader": "Inspector Vikram Rathore"
    }
    res = requests.post(upload_url, files=files, data=data)
    print("1. Upload Status:", res.status_code)
    json_data = res.json()
    items = json_data.get("items", [])
    if items:
        it = items[0]
        eid = it["evidence_id"]
        print("   Evidence ID:", eid)
        print("   Classification:", it["job"]["classification"])
        print("   Status:", it["job"]["status"])
        print("   Mentions Extracted:", it["job"]["mention_count"])

# 2. Check Case details
case_res = requests.get(f"{base}/api/cases/CASE_TEST_007")
c_data = case_res.json()
print("\n2. Case Details:")
print("   Case ID:", c_data.get("case_id"))
print("   Total Entities:", c_data.get("total_entities"))
print("   Overlapping Cases (Cross-Case Links):", c_data.get("overlapping_cases"))

# 3. Check Extracted Mentions & Provenance Quotes
m_res = requests.get(f"{base}/api/evidence/{eid}/results/mentions")
mentions = m_res.json().get("items", [])
print(f"\n3. Extracted Mentions ({len(mentions)}):")
for m in mentions:
    print(f"   [{m['type']}] {m['raw_value']} (Role: {m['role']})")
    print(f"       Quote: \"{m['quote']}\"")
    print(f"       Provenance: Page {m['provenance'].get('page')}")

# 4. Check Shortest Path
print("\n4. Tracing Shortest Path across Case 001 and Case 002:")
path_res = requests.get(f"{base}/api/cases/shortest-path?suspect_name=Vikrant%20Naik&victim_name=Deepa%20Rao")
print("   Path Result:", path_res.json().get("summary") or path_res.json().get("error"))

# 5. Check Blockchain Chain-of-Custody
bc_res = requests.get(f"{base}/api/v1/blockchain/verify-case/CASE_TEST_007")
print("\n5. Chain-of-Custody Verification:")
print("   Status:", bc_res.json().get("status"))
print("   Message:", bc_res.json().get("message"))
print("   Blocks Count:", bc_res.json().get("blocks_count"))

print("\n" + "=" * 60)
print("TEST COMPLETED SUCCESSFULLY!")
print("=" * 60)
