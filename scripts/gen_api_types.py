"""Dump the backend OpenAPI schema so the web app can generate TypeScript types from it.

Usage: apps/api/.venv/Scripts/python scripts/gen_api_types.py && (cd apps/web && npm run gen:types)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from integreat.config import Settings  # noqa: E402
from integreat.main import create_app  # noqa: E402

app = create_app(Settings(db_path=":memory:", fixtures_dir=ROOT / "fixtures", replay_speed=0))
out = ROOT / "apps" / "web" / "src" / "types" / "openapi.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(app.openapi(), indent=1), encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)}")
