# Integration research note — StepFun + Devin (2026-10-17)

Findings used while implementing provider routing and the remote repair workflow.
URLs were fetched on 2026-10-17; verify again if the APIs change.

## StepFun (orchestration + synthesis)

Sources:

- <https://platform.stepfun.com/cookbook/step-5-tool-calling>
- <https://platform.stepfun.com/cookbook/step-5-vision-structured>
- Model endpoint given by the hackathon sponsor: `https://api.stepfun.ai/v1/chat/completions`

Concrete conclusions:

- The global base URL is `https://api.stepfun.ai/v1` (OpenAI-compatible). The China-region endpoint
  is a different host (`api.stepfun.com`); the global one is used by default and the base URL is
  configurable via `INTEGREAT_STEPFUN_BASE_URL`.
- Required model ID: `step-5-preview` (configured default, overridable via `INTEGREAT_STEPFUN_MODEL`).
- Auth: `Authorization: Bearer $STEP_API_KEY` (env name given by sponsor: `STEP_API_KEY`).
- Structured output is supported via `response_format: {"type": "json_schema", "json_schema":
  {"name": ..., "schema": ..., "strict": true}}`. **Structured output still needs application-side
  validation** — StepFun guarantees JSON schema shape, not that cited IDs exist. inteGREAT therefore
  re-validates every evidence/action/agent ID the model emits, exactly like the Gemini path.
- Tool calling model: the application declares tool schemas; the model returns tool-call *requests*;
  the application validates arguments and executes fixed application-side functions, then posts
  results back keyed by `tool_call_id`. We do **not** give StepFun live tool-calling loops in v1 —
  specialist/context fetch remains the deterministic context engine (same permission-gated path).
  This preserves the "no model-executed tools" boundary while StepFun performs *orchestration*
  decisions (which specialists to call, what question each resolves, and final synthesis).
- One schema-repair retry is kept (same policy as Gemini). Timeout → request aborted; caller maps
  it to a failed/timeout agent run, never a crash.

## Devin Cloud (reviewable software fixes only)

Sources:

- <https://docs.devin.ai/api-reference/authentication>
- <https://docs.devin.ai/api-reference/common-flows>
- <https://docs.devin.ai/_llms/en/api.txt> (machine-readable OpenAPI for v3)
- <https://docs.devin.ai/llms.txt> (docs index)

Concrete conclusions:

- Current API is **v3, organization-scoped**: base `https://api.devin.ai`, endpoints under
  `/v3/organizations/{org_id}/...`. Legacy `/v1/...` session endpoints exist but are deprecated for
  new work; we use v3.
- Auth: `Authorization: Bearer <key>` where the key is a **service-user key `cog_...`** (preferred)
  or a personal access token. Legacy `apk_` keys are deprecated for new v3 integrations.
  Org ID is shown at **Settings → Devin API** and is required (`INTEGREAT_DEVIN_ORG_ID`).
- `GET /v3/self` verifies credentials without creating anything (used by the smoke script and
  preflight).
- Create session: `POST /v3/organizations/{org_id}/sessions` with JSON body; relevant fields:
  `prompt` (required), `repos` (list of repo identifiers available to the org), `title`,
  `max_acu_limit` (resource cap), `resumable`, `tags`, `structured_output_schema` +
  `structured_output_required`. Response includes `session_id` (`devin-...`), `url`
  (`https://app.devin.ai/sessions/devin-...`), `status`.
- Poll status: `GET /v3/organizations/{org_id}/sessions/{devin_id}` returns `status`
  (`new|claimed|running|exit|error|suspended|resuming`), `status_detail` (`working`,
  `waiting_for_user`, `waiting_for_approval`, `finished`, usage/quota failures, errors...),
  `pull_requests` (`[{pr_url, pr_state}]`), `structured_output`, `acus_consumed`, timestamps.
- Status mapping used by inteGREAT (remote → local):
  `new|claimed → queued`, `running|resuming → working` (but `waiting_for_user|waiting_for_approval`
  detail → `needs_input`), `exit + finished → ready_for_review`, `error` or `exit` without finished
  → `failed`, `suspended → needs_input`.
- Session creation is **not idempotent**: on POST timeout we do not retry automatically; the job is
  marked `uncertain` and a new attempt requires a deliberate engineer request.
- `repos` values are repo identifiers the Devin org can access (as indexed in Devin Cloud). We derive
  `owner/repo` from the git remote URL when it looks like a GitHub-style remote and allow an explicit
  override via `INTEGREAT_DEVIN_REPO`, because a local Windows path is meaningless to Devin Cloud.
- Devin works in **its own cloud sandbox**. inteGREAT never applies the result locally, never merges,
  never flashes. Remote "finished"/"tests passed" is remote software-test evidence only.

## Assumptions recorded

- `step-5-preview` accepts OpenAI-style `json_schema` response_format; if strict mode rejects our
  schema, the provider retries once with a repaired prompt and otherwise reports failure honestly.
- Devin `repos` strings of the form `owner/name` match how orgs register repos; when the remote URL
  cannot be normalized the preflight asks for `INTEGREAT_DEVIN_REPO` instead of guessing.
- Devin's `structured_output` may contain model-maintained content — it is validated again on our
  side and displayed as untrusted remote output, never as verified state.
- Neither provider receives secrets; prompts contain the incident context (code excerpts, evidence
  summaries) only, and the repair brief sent to Devin is persisted for audit.
