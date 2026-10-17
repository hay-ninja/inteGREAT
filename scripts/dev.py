"""Start the API (port 8000) and web UI (port 5173) together. Cross-platform; Ctrl+C stops both.

Usage (from repo root): apps/api/.venv/Scripts/python scripts/dev.py   (Windows)
                        apps/api/.venv/bin/python scripts/dev.py       (macOS/Linux)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"


def main() -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm not found on PATH", file=sys.stderr)
        return 1
    if not (WEB / "node_modules").is_dir():
        subprocess.run([npm, "install"], cwd=WEB, check=True)
    procs = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "integreat.main:create_app", "--factory", "--reload",
                          "--port", "8000"], cwd=API, env=os.environ.copy()),
        subprocess.Popen([npm, "run", "dev"], cwd=WEB),
    ]
    print("inteGREAT: UI http://localhost:5173  ·  API http://127.0.0.1:8000/docs")
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
