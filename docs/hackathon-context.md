# Hackathon context

**Recorded:** 2026-10-17. LA Hacks AI Hackathon, October 17–18, 2026, UCLA.

**Owner direction:** inteGREAT is a hackathon project targeting **Beyond the Digital** and relevant
company challenges. Judge-facing work should support the hardware/software debugging loop and a reliable
demo within the 24–36 hour build window.

## Sources and scope

This note summarizes the two event excerpts supplied by the owner: the StepFun Hacker Starter Pack
and the LA Hacks tracks/company challenges page. Additional linked rules, submission limits, deadlines,
and award details have not been independently checked. Candidate fit below is an assessment of those
excerpts, not a claim of eligibility or a commitment to add every integration.

`PRD.md` remains the product contract; `docs/STATUS.md` records implementation and verification.
This note does not change confirmed requirements or promote sponsor integrations to P0.

## Track and relevant challenges

| Track / challenge | Fit with inteGREAT | What the demo or implementation still needs |
|---|---|---|
| **Beyond the Digital — primary track** | Connects AI-assisted diagnosis to an ESP32, a physical actuator, serial observations, and camera measurements. | Demonstrate physical failure → evidence → engineer repair → measured verification on the real rig. Label simulation and replay accurately. |
| **Espressif — Best Use of Espressif** | ESP32 is the core hardware target. The excerpt emphasizes creative, meaningful, impactful use. | Show the ESP32 performing the test and explain why debugging across code and physical wiring is useful. Real hardware validation is still pending. |
| **MLH — Best Use of Gemini API** | Gemini orchestrator and specialist providers already exist in the code. | Exercise real Gemini calls and show their contribution. Only fake-provider tests are documented so far; the supplied excerpt does not include full judging rules. |
| **StepFun — Best Use of Step 5 Preview** | Evidence packets → cited hypotheses → useful next diagnostic action matches its task-completion and user-control emphasis. | Add and exercise an actual runtime call to exact model ID `step-5-preview`; explain its role alongside Gemini and identify the call in the code. No StepFun provider currently exists. |
| **Paper — Best Designed Hack** | Graph-first workspace, guided steps, restrained Astryx/Obsidian styling, and one primary action support the stated design criteria. | Demonstrate design fundamentals, ease of use, and personal craft. The supplied description does not state that using the Paper tool is mandatory. |
| **Sentry — conditional additional challenge** | Import/test/agent flows could provide useful application observability. | Actual Sentry integration must use at least **two products beyond error monitoring**, and show how observability helped improve the hack. This is additional scope, not an existing qualification. |

Other excerpts require substantial new surfaces or dependencies: Fetch.ai requires an Agentverse agent
discoverable through ASI:One; QNX requires both QNX OS and an open-source AI module from oss.qnx.com;
Even Realities requires an Even Hub app for Even G2. Those capabilities are not established by the
current ESP32/laptop implementation. Other challenges should only be pursued when their required
technology and user problem meaningfully fit the product.

## StepFun details worth retaining

- The running workflow must call **`step-5-preview`**. Other models and frameworks are permitted if their
  respective contributions are explained.
- Supplied standard endpoint: `https://api.stepfun.ai/v1/chat/completions`. API keys stay server-side.
- Judges emphasize completed tasks, reliability, and a workflow users can understand and control.
- Demonstrate the live flow or a reproducible recording and point reviewers to the model call in code.
- The pack offers a $25 API voucher, limited to 50 claims, one voucher per participant. Availability
  has not been checked. Follow the platform's displayed redemption and expiry details.
- Award details are pending organizer confirmation in the supplied pack. Its October 31 voucher-claim
  deadline is not the hackathon submission deadline.

## Current demo priorities

The status file's remaining core work still applies: real Gemini access, rig bring-up, both live faults,
real recordings, and three consecutive successful demos. Preserve provenance, manual control of repairs,
and deterministic operation when AI is unavailable. Treat the measured before/after result as the
central Beyond the Digital demo evidence.
