# AGENTS.md — read this first

inteGREAT (formerly "TRACE" in early PRD drafts) is a graph-first debugging workspace for ESP32 Arduino projects:
import repo + hardware manifest → dependency graph → run a test → evidence-backed hypotheses
→ clickable diagnostic actions → verify fix. 24–36h hackathon MVP.

## Read order for any agent picking this up
1. `docs/STATUS.md` — where the work is right now, what's next, what's broken. **Always current.**
2. `docs/decisions.md` — why things are the way they are (intent the code can't tell you).
3. `PRD.md` — full product spec. Authoritative. Sections are referenced as `PRD §N`.

## Non-negotiables (do not trade these away for speed)
- **Provenance:** every finding cites evidence IDs that resolve. Observed ≠ verified ≠ inferred ≠ unknown.
- **No fabrication:** never present replay/synthetic data as live hardware; never claim PWM/voltage was measured.
  Missing CV marker is "measurement unavailable", never a servo failure.
- **No arbitrary execution:** no `shell=True`, no LLM-authored commands, no auto-flash, no auto-patching.
  Tools are fixed templates in the registry with validated args + permission category (D-004, D-005).
- **Bounded agents:** one initial fan-out + one follow-up per incident. No open-ended loops.
- **Core works without AI:** rules + graph + tests must function if Gemini is down.
- **Existing firmware only:** inteGREAT never requires its own instrumentation in user firmware.

## Layout
- `apps/api/integreat/` — FastAPI modular monolith (package `integreat`). `models/` is the single source
  of truth for contracts. Map of modules and "where to change things": `docs/architecture.md`.
- `apps/web/` — Vite + React 19 + `@xyflow/react` + **Astryx** design system (rules: `apps/web/ASTRYX.md`,
  intent: D-021). Types generated from backend OpenAPI. Keep the UI calm: one primary button per step.
- `fixtures/` — demo firmware, manifests, recorded serial/CV JSONL (synthetic files say so in name/header).
- `docs/` — STATUS, decisions, architecture, hardware-setup (rig checklist), demo-script.

## Commands
See `docs/STATUS.md` → "How to run / verify" (kept current there to avoid drift).

## Working agreement for agents
- **After each verifiable slice:** update `docs/STATUS.md` (done / in progress / next / known issues),
  and add a `docs/decisions.md` entry for any choice that isn't obvious from the code or deviates from the PRD.
- Don't silently change CONFIRMED PRD requirements; log it as a decision and flag to the user.
- Don't promote P1/P2 work to P0. Follow PRD §17 cut order if behind.
- Prefer vertical working slices over scaffolding; no empty placeholder modules.
- Tests for every deterministic rule and every security boundary.
- Platform: dev machine is Windows (PowerShell + Git Bash). Keep scripts cross-platform (Python, not .sh).
