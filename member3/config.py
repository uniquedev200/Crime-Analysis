"""
Backward-compatibility alias module.
Member 4 is the Knowledge Graph Engine.
Re-exports everything from member4.config.
"""
import sys
from pathlib import Path

MEMBER4_DIR = Path(__file__).resolve().parent.parent / "member4"
if str(MEMBER4_DIR) not in sys.path:
    sys.path.insert(0, str(MEMBER4_DIR))

from member4.config import *
