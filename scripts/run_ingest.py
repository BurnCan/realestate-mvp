from pathlib import Path
import sys

# Ensure repo root is on sys.path when this file is invoked directly via an
# absolute/relative path (for example: `python3 scripts/run_ingest.py`).
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ingest import run

if __name__ == "__main__":
    run()
