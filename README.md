# inteGREAT

Graph-first debugging workspace for ESP32 Arduino projects. Import an existing repo plus its hardware manifest,
review the hardware/software dependency graph, run a test, and get evidence-backed hypotheses with clickable
next steps — then verify the fix with the same test. No firmware instrumentation required.

- Product spec: [`PRD.md`](PRD.md)
- Current progress and how to run: [`docs/STATUS.md`](docs/STATUS.md)
- Why things are the way they are: [`docs/decisions.md`](docs/decisions.md)
- For AI agents: start at [`AGENTS.md`](AGENTS.md)

## Quick start (Windows)

```powershell
cd apps/api; py -3.13 -m venv .venv; .venv/Scripts/python -m pip install -e ".[dev]"; cd ../..
cd apps/web; npm install; cd ../..
apps/api/.venv/Scripts/python scripts/dev.py
```

Open http://localhost:5173, pick a demo fixture, click **Suggest a test from the code → Confirm test → Run test**.
Use **Rig setup** in the header to connect real devices. Select graph nodes/connections or supporting
evidence to inspect them; **Focus graph** closes the measurement drawer without interrupting the investigation.

Observation sources (top bar): **Sim** (simulated rig through the real CV pipeline), **Replay** (recorded or
synthetic files), **Live rig** (real ESP32 + camera — see [`docs/hardware-setup.md`](docs/hardware-setup.md)).
Non-live runs are always labelled as synthetic/simulated.

Optional AI agents: copy `.env.example` to `.env`, set `GEMINI_API_KEY` and `INTEGREAT_GEMINI_MODEL`, then
run `apps/api/.venv/Scripts/python scripts/gemini_smoke.py`. Without them, everything except *Ask agents* works.

More: [`docs/architecture.md`](docs/architecture.md) · [`docs/demo-script.md`](docs/demo-script.md)
