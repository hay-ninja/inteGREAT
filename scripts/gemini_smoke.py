"""Check Gemini access + structured output before relying on agents (PRD §20 assumption).

Usage: set GEMINI_API_KEY and INTEGREAT_GEMINI_MODEL (or put them in .env), then
       apps/api/.venv/Scripts/python scripts/gemini_smoke.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from integreat.agents.schemas import TriageOut  # noqa: E402
from integreat.config import load_settings  # noqa: E402
from integreat.service import make_provider  # noqa: E402


async def main() -> int:
    s = load_settings()
    p = make_provider(s)
    if not p.available:
        print(f"UNAVAILABLE: {p.reason}")
        return 1
    t0 = time.perf_counter()
    out = await p.generate_structured(
        system="You route embedded debugging questions to specialist agents.",
        prompt="Incident: servo did not move; source configures GPIO19 but wiring uses GPIO18. Choose agents.",
        schema=TriageOut, timeout_s=s.agent_timeout_s)
    print(f"OK model={p.model} latency={time.perf_counter() - t0:.1f}s agents={out.agents} rationale={out.rationale!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
