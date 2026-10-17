"""Settings from environment (INTEGREAT_*). No secrets are exposed to the frontend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    db_path: str
    fixtures_dir: Path
    replay_speed: float  # 1.0 = real time; 0 = instant (tests)

    @property
    def replay_dir(self) -> Path:
        return self.fixtures_dir / "recorded"


def load_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("INTEGREAT_DB_PATH", str(REPO_ROOT / "apps" / "api" / ".data" / "integreat.db")),
        fixtures_dir=Path(os.environ.get("INTEGREAT_FIXTURES_DIR", str(REPO_ROOT / "fixtures"))),
        replay_speed=float(os.environ.get("INTEGREAT_REPLAY_SPEED", "1.0")),
    )
