import uvicorn
import os
import sys

# Ensure current project directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("=" * 60)
    print("  ATLAS Criminal Network Intelligence & Forensic Analysis API")
    print("  Member 2: Backend, Database & Application Management")
    print("=" * 60)
    print("  Serving API & Frontend at: http://127.0.0.1:8000")
    print("  Interactive Swagger Docs at: http://127.0.0.1:8000/docs")
    print("=" * 60)
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
