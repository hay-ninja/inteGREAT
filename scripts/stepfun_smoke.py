"""Check StepFun access + strict structured output before relying on orchestration (D-023).

Usage: set STEP_API_KEY (or put it in .env), then
       apps/api/.venv/Scripts/python scripts/stepfun_smoke.py
Optional: INTEGREAT_STEPFUN_MODEL (default step-5-preview), INTEGREAT_STEPFUN_BASE_URL.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from integreat.agents.schemas import TriageOut  # noqa: E402
from integreat.config import load_settings  # noqa: E402
from integreat.service import make_orchestrator_provider  # noqa: E402


async def main() -> int:
    s = load_settings()
    p = make_orchestrator_provider(s)
    if not p.available:
        print(f"UNAVAILABLE: {p.reason}")
        return 1
    t0 = time.perf_counter()
    out = await p.generate_structured(
        system="You are the triage orchestrator for an embedded debugging tool. Choose which "
               "specialist agents to consult (1-3) and state the question each should resolve.",
        prompt="Incident: servo did not move; source configures GPIO19 but wiring uses GPIO18. "
               "Choose agents and questions.",
        schema=TriageOut, timeout_s=s.agent_timeout_s)
    print(f"OK model={p.model} latency={time.perf_counter() - t0:.1f}s "
          f"agents={out.agents} questions={len(out.questions)} rationale={out.rationale!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
