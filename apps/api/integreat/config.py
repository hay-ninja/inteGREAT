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
    # StepFun runs triage + synthesis (D-023); the sponsor-required default model is step-5-preview.
    stepfun_api_key: str | None = None
    stepfun_model: str = "step-5-preview"
    stepfun_base_url: str = "https://api.stepfun.ai/v1"  # global endpoint; China region differs
    # Devin Cloud: remote, reviewable software-fix proposals only (D-025). v3 org-scoped API.
    devin_api_key: str | None = None
    devin_org_id: str | None = None
    devin_repo: str | None = None  # optional "owner/name" override when the git remote can't be parsed
    devin_api_base: str = "https://api.devin.ai"
    devin_max_acu: float = 10.0    # resource cap sent as max_acu_limit per repair session
    agent_timeout_s: float = 30.0
    # StepFun step-5 is a reasoning model: triage/synthesis need a larger budget than the
    # Gemini specialists' ~10s calls (reasoning tokens alone can exceed 30s of generation).
    orchestrator_timeout_s: float = 120.0
    max_context_tokens: int = 6000
    # Standard observer; an empty DSN sends nothing, and the explicit switch can disable it.
    sentry_enabled: bool = True
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    sentry_release: str = "integreat@0.1.0"
    sentry_traces_sample_rate: float = 0.1

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
        stepfun_api_key=os.environ.get("STEP_API_KEY") or os.environ.get("INTEGREAT_STEPFUN_API_KEY") or None,
        stepfun_model=os.environ.get("INTEGREAT_STEPFUN_MODEL", "step-5-preview"),
        stepfun_base_url=os.environ.get("INTEGREAT_STEPFUN_BASE_URL", "https://api.stepfun.ai/v1"),
        devin_api_key=os.environ.get("DEVIN_API_KEY") or os.environ.get("INTEGREAT_DEVIN_API_KEY") or None,
        devin_org_id=os.environ.get("INTEGREAT_DEVIN_ORG_ID") or os.environ.get("DEVIN_ORG_ID") or None,
        devin_repo=os.environ.get("INTEGREAT_DEVIN_REPO") or None,
        devin_api_base=os.environ.get("INTEGREAT_DEVIN_API_BASE", "https://api.devin.ai"),
        devin_max_acu=float(os.environ.get("INTEGREAT_DEVIN_MAX_ACU", "10")),
        agent_timeout_s=float(os.environ.get("INTEGREAT_AGENT_TIMEOUT_S", "30")),
        orchestrator_timeout_s=float(os.environ.get("INTEGREAT_ORCHESTRATOR_TIMEOUT_S", "120")),
        max_context_tokens=int(os.environ.get("INTEGREAT_MAX_CONTEXT_TOKENS", "6000")),
        sentry_enabled=os.environ.get("INTEGREAT_SENTRY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
        sentry_dsn=os.environ.get("INTEGREAT_SENTRY_DSN") or None,
        sentry_environment=os.environ.get("INTEGREAT_SENTRY_ENVIRONMENT", "development"),
        sentry_release=os.environ.get("INTEGREAT_SENTRY_RELEASE", "integreat@0.1.0"),
        sentry_traces_sample_rate=_telemetry_rate(),
    )


def _telemetry_rate() -> float:
    """Bad optional telemetry config must not prevent the application starting."""
    try:
        rate = float(os.environ.get("INTEGREAT_SENTRY_TRACES_SAMPLE_RATE", "0.1"))
        return rate if 0 <= rate <= 1 else 0.1
    except ValueError:
        return 0.1
