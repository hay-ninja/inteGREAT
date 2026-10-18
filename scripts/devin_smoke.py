"""Check Devin Cloud credentials WITHOUT creating a session (D-025).

Usage: set DEVIN_API_KEY and INTEGREAT_DEVIN_ORG_ID (or put them in .env), then
       apps/api/.venv/Scripts/python scripts/devin_smoke.py
This only calls GET /v3/self — it never starts a paid session.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from integreat.config import load_settings  # noqa: E402
from integreat.repair import make_devin  # noqa: E402


async def main() -> int:
    s = load_settings()
    d = make_devin(s)
    if not d.available:
        print(f"UNAVAILABLE: {d.reason}")
        return 1
    me = await d.whoami()
    print(f"OK org={s.devin_org_id} principal={me.get('principal_type')} "
          f"name={me.get('service_user_name') or me.get('user_name')}")
    print("No session was created. Repair sessions are only created from the app UI.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
