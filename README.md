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

Open http://localhost:5173, pick a demo fixture, click **Propose test from code → Confirm → Run Test**.

> Until hardware is connected, tests run on **synthetic replay** data and the UI labels them as such.
