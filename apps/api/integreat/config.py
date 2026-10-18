"""Settings from environment (INTEGREAT_*), optionally loaded from the repo-root `.env`.

Secrets (the Gemini API key) stay server-side: never returned by the API or put in model context.
No Gemini model id is hardcoded (PRD §11.4) — set INTEGREAT_GEMINI_MODEL explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal KEY=VALUE loader; real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    db_path: str
    fixtures_dir: Path
    replay_speed: float = 1.0  # 1.0 = real time; 0 = instant (tests)
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    agent_timeout_s: float = 30.0
    max_context_tokens: int = 6000

    @property
    def replay_dir(self) -> Path:
        return self.fixtures_dir / "recorded"


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        db_path=os.environ.get("INTEGREAT_DB_PATH", str(REPO_ROOT / "apps" / "api" / ".data" / "integreat.db")),
        fixtures_dir=Path(os.environ.get("INTEGREAT_FIXTURES_DIR", str(REPO_ROOT / "fixtures"))),
        replay_speed=float(os.environ.get("INTEGREAT_REPLAY_SPEED", "1.0")),
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("INTEGREAT_GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("INTEGREAT_GEMINI_MODEL") or None,
        agent_timeout_s=float(os.environ.get("INTEGREAT_AGENT_TIMEOUT_S", "30")),
        max_context_tokens=int(os.environ.get("INTEGREAT_MAX_CONTEXT_TOKENS", "6000")),
    )
