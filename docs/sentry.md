# Standard Sentry observability

This integration uses **Tracing** and **Logs**, two products beyond error monitoring.
It is included in the standard API install and runs automatically when a DSN is configured.
The UI and hardware protocol are unchanged. Set `INTEGREAT_SENTRY_ENABLED=false` to opt out.
No Sentry account, DSN or network connection is required for the core app or its tests.

Verified setup on 2026-10-18: project `ryder-ys/integreat-api`, DSN in ignored `.env`,
synthetic fail/pass traces and correlated history logs confirmed indexed in Sentry.
The idle localhost API was restarted with telemetry enabled. This is ingestion verification,
not live-hardware validation or a measured improvement claim.

## Observer-only boundary

Sentry is an outbound telemetry destination. It is not a diagnostic agent in inteGREAT.
The app has no Sentry command endpoint, webhook, repair callback or Sentry-controlled tool.
After lifecycle events are persisted and published, a projection mirrors only allowlisted
event types, source kinds and outcomes. It cannot edit the stored history, hypotheses,
permissions, firmware or device state. Raw history/log contents remain local.

The separately installed Sentry Codex plugin helps this coding assistant query Sentry.
That is separate from the running app. For inspection-only access, select only
**Inspect Issues & Events** on the MCP consent page and deselect **Seer**, **Triage Issues**,
and **Manage Projects & Teams**. Create the initial Python project in Sentry's web UI.
Do not enable repository write access or automatic Seer fixes for this integration.

The owner-authorized initial project was provisioned through MCP during setup. Ongoing
Codex access now has a saved plugin-specific inspection tool allowlist, excluding Seer,
issue writes and the generic executor. It applies on the next Codex reload. This local
restriction does not revoke previously granted OAuth scopes in Sentry.

## Safe simulation

From the repository root:

```text
apps/api/.venv/Scripts/python scripts/sentry_simulation.py
```

This runs the actual import/rules/history pipeline with synthetic failure/pass replays,
an in-memory database, unavailable AI providers and a device stub with no hardware
interfaces. It compares the outcomes and lifecycle history with telemetry off/on.
Real SDK Tracing + Logs envelopes are captured in memory, then saved to the ignored
`apps/api/.data/sentry-simulation.json` for inspection. No upload happens by default.

After configuring your DSN, explicitly send the same synthetic workflow to Sentry:

```text
apps/api/.venv/Scripts/python scripts/sentry_simulation.py --send-live
```

Only telemetry from the synthetic run is exported, tagged `environment=simulation`.
The script does not open hardware, call AI providers, modify a user project, or
run diagnostic tools. Confirm both products in the Sentry dashboard afterward.
Sending an SDK envelope is not proof that Sentry accepted or indexed it.

## Enable locally

1. Create a Python project in your Sentry organization and copy its DSN.
2. Use the normal API installation from `apps/api`:
   `python -m pip install -e ".[dev]"` (use the project's virtual environment).
3. Set these values in the ignored repository-root `.env`:

   ```dotenv
   INTEGREAT_SENTRY_ENABLED=true
   INTEGREAT_SENTRY_DSN=https://YOUR_PUBLIC_KEY@YOUR_INGEST_HOST/YOUR_PROJECT_ID
   INTEGREAT_SENTRY_ENVIRONMENT=hackathon
   INTEGREAT_SENTRY_RELEASE=integreat@demo-1
   INTEGREAT_SENTRY_TRACES_SAMPLE_RATE=1.0
   ```

4. Restart the API, import a project, and run a test. For AI timing, use the existing
   agent-enabled diagnostic flow with your configured providers. The separate two-LED
   visual path records `visual.observe`; it does not call AI providers.
5. In Sentry, open Traces and search for `project.import`, `test.run`, `diagnosis.run`,
   or `visual.observe`. Expand `project.build`, `test.collect`, and `ai.structured`
   child spans. Logs have the message `integreat.operation.completed` and searchable
   attributes `operation`, `outcome`, `duration_ms`, and (for AI) `provider`.
   HTTP logs also include a fixed endpoint name and status code. Select a log's trace
   link to correlate it with the workflow. Allow a few seconds for SDK log batching.

The default trace sampling rate is 10%; 100% is useful for a small demo. Logs are emitted
per instrumented operation, independent of trace sampling. Remove/empty the DSN and restart
to disable all integration activity, or set `INTEGREAT_SENTRY_ENABLED=false` and restart.
Startup logs report `active`, `disabled`, `not_configured`, or `unavailable` without credentials.
No frontend token or Sentry auth token is needed. The DSN stays deployment-specific;
new checkouts do not silently upload data to someone else's Sentry project.

## What leaves the app

Only fixed operation/provider/endpoint names, allowlisted outcomes, durations, HTTP status
codes, SDK trace/span IDs, and configured environment/release labels. Do not put private
information into the environment/release labels. Data is sent to your configured Sentry project.

Automatic integrations and error capture are deliberately disabled. There is no request-body,
query-string, header, cookie, source-path, project-ID, serial-message, prompt/response, image,
exception-message, local-variable, or stack-source collection. Export hooks strip inherited
scope metadata and reject non-application logs. Health checks, camera endpoints, and WebSockets
are excluded. This is manual Tracing + Logs, not Session Replay or Sentry AI agent monitoring.

The SDK uses a bounded asynchronous transport queue. Initialization/emission/shutdown
failures are fail-open and must not change diagnostic results. A missing SDK or malformed DSN
prints a generic local warning, without printing credentials, and leaves telemetry disabled.

HTTP transaction duration includes ASGI background task completion, so use the child spans to
distinguish response handling from tests/diagnosis. Do not describe it as browser-perceived latency.

## Evidence for the sponsor challenge

Integration is only the first step. Before claiming observability improved the hack:

1. Capture a real trace and correlated log from an actual slow or failed workflow.
2. Record the environment/release, operation, duration, and trace link. State whether input
   came from hardware, replay, or a controlled simulation.
3. Investigate the cause, make a justified fix, and rerun the same scenario.
4. Keep the before/after evidence and explain the change without claiming simulated data is live.

The regression tests inject a delayed fake provider and a timeout, capture real SDK envelopes
in memory, and verify timings and privacy boundaries. This demonstrates instrumentation only.
It is **not** a measured production improvement or proof of delivery to Sentry. No deliberate
crash endpoint, automatic hardware actions, or artificial production failure is added.

## Verify

From `apps/api`, after the normal install:

```text
.venv/Scripts/python -m pytest tests/test_observability.py -q
.venv/Scripts/python -m pytest -q
```

Enabled tests use an in-memory SDK transport and never upload data. The SDK is now a required
installation dependency; graceful handling of a missing SDK is still tested defensively.

SDK reference: [Python API](https://getsentry.github.io/sentry-python/api.html) and
[Sentry Python Logs](https://docs.sentry.io/platforms/python/logs/).
