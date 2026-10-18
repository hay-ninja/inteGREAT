"""Single execution path for every tool call, whoever the caller is (D-004).

Order of checks: tool exists → arguments validate → category not risky → category granted for this
investigation (or the *engineer* approved this one call) → run with timeout and output caps → audit.
Every outcome, including denials and invalid arguments, is written to the audit log.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from ..models import Epistemic, Evidence, EvidenceKind, Incident, PermissionGrant, Project, Provenance, ToolCall, utcnow
from .registry import MAX_OUTPUT_LINES, REGISTRY, RISKY_CATEGORIES, ToolContext, ToolOutput

if TYPE_CHECKING:
    from ..service import Service

K_GRANT, K_TOOLCALL = "permission_grant", "tool_call"
TOOL_TIMEOUT_S = 5.0


class ToolDenied(Exception):
    def __init__(self, call: ToolCall, reason: str, category: str):
        super().__init__(reason)
        self.call, self.reason, self.category = call, reason, category


class ToolFailed(Exception):
    def __init__(self, call: ToolCall, reason: str):
        super().__init__(reason)
        self.call, self.reason = call, reason


class Permissions:
    """Per-investigation category grants (PRD §13.1). Grants end when the investigation closes."""

    def __init__(self, svc: Service):
        self.svc = svc

    def active(self, incident_id: str) -> list[PermissionGrant]:
        inc = self.svc.store.get("incident", incident_id, Incident)
        if inc is None or inc.state.value in ("resolved", "inconclusive"):
            return []
        return [g for g in self.svc.store.list(K_GRANT, PermissionGrant, parent_id=incident_id) if g.revoked_at_utc is None]

    def is_granted(self, incident_id: str | None, category: str, target: str = "local") -> bool:
        if incident_id is None:
            return False
        return any(g.category == category and g.target == target for g in self.active(incident_id))

    def set(self, inc: Incident, category: str, granted: bool) -> list[PermissionGrant]:
        current = [g for g in self.active(inc.id) if g.category == category]
        if granted and not current:
            g = PermissionGrant(id=f"grant:{uuid.uuid4().hex[:10]}", project_id=inc.project_id, incident_id=inc.id,
                                category=category)
            self.svc.store.put(K_GRANT, g, parent_id=inc.id)
        if not granted:
            for g in current:
                g.revoked_at_utc = utcnow()
                self.svc.store.put(K_GRANT, g, parent_id=inc.id)
        self.svc._emit("permissions.updated", inc.project_id, {"category": category, "granted": granted},
                       investigation_id=inc.id)
        return self.active(inc.id)


class ToolExecutor:
    def __init__(self, svc: Service):
        self.svc = svc
        self.permissions = Permissions(svc)

    def _audit(self, call: ToolCall) -> ToolCall:
        self.svc.store.put(K_TOOLCALL, call, parent_id=call.incident_id or call.project_id)
        self.svc._emit("tool.called", call.project_id, call.model_dump(mode="json"), investigation_id=call.incident_id)
        return call

    def calls(self, incident_id: str) -> list[ToolCall]:
        return self.svc.store.list(K_TOOLCALL, ToolCall, parent_id=incident_id)

    async def execute(self, project: Project, incident: Incident | None, tool_name: str, raw_args: dict[str, Any],
                      caller: str, approve_once: bool = False) -> tuple[ToolCall, ToolOutput | None]:
        base = dict(id=f"toolcall:{uuid.uuid4().hex[:10]}", project_id=project.id,
                    incident_id=incident.id if incident else None, tool_name=tool_name,
                    arguments=dict(raw_args), caller=caller)
        spec = REGISTRY.get(tool_name)
        if spec is None:
            call = self._audit(ToolCall(**base, permission_category="unknown", decision="unavailable",
                                        status="denied", error=f"unknown tool {tool_name!r}"))
            raise ToolDenied(call, call.error, "unknown")
        base["permission_category"] = spec.permission_category

        try:
            args = spec.args_model.model_validate(raw_args)
        except ValidationError as e:
            call = self._audit(ToolCall(**base, decision="invalid", status="denied",
                                        error=f"invalid arguments: {e.errors(include_url=False)}"[:1000]))
            raise ToolDenied(call, "invalid arguments", spec.permission_category) from e

        if spec.permission_category in RISKY_CATEGORIES or not spec.is_read_only or not spec.available:
            call = self._audit(ToolCall(**base, decision="unavailable", status="denied",
                                        error="risky/non-read-only tools are not executable in this MVP"))
            raise ToolDenied(call, call.error, spec.permission_category)

        if self.permissions.is_granted(incident.id if incident else None, spec.permission_category):
            decision = "granted"
        elif approve_once and caller == "engineer":
            decision = "approved_once"  # individual engineer approval; agents can never do this
        else:
            call = self._audit(ToolCall(**base, decision="denied", status="denied",
                                        error=f"category '{spec.permission_category}' not granted for this investigation"))
            raise ToolDenied(call, call.error, spec.permission_category)

        t0 = time.perf_counter()
        ctx = ToolContext(svc=self.svc, project=project, incident=incident, caller=caller)
        try:
            out = await asyncio.wait_for(spec.run(args, ctx), timeout=TOOL_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001 — every failure is audited and surfaced, never swallowed
            call = self._audit(ToolCall(**base, decision=decision, status="failed",
                                        duration_ms=int((time.perf_counter() - t0) * 1000),
                                        error=f"{type(e).__name__}: {e}"[:500]))
            raise ToolFailed(call, call.error) from e

        out.lines = out.lines[:MAX_OUTPUT_LINES]
        out.summary = out.summary[:1000]
        ev = Evidence(id=f"evidence:tool:{base['id'].split(':')[1]}", project_id=project.id,
                      kind=EvidenceKind.tool_output, epistemic=Epistemic.observed,
                      summary=f"{tool_name}: {out.summary}",
                      provenance=Provenance(source_id=f"tool:{tool_name}", captured_at_utc=utcnow()),
                      payload={"incident_id": incident.id if incident else None, "tool_call_id": base["id"],
                               "caller": caller,
                               "arguments": dict(raw_args), "lines": out.lines[:50], "data": out.data,
                               "excerpts": [x.evidence_id for x in out.source_excerpts]})
        self.svc.store.put("evidence", ev)
        call = self._audit(ToolCall(**base, decision=decision, status="completed",
                                    duration_ms=int((time.perf_counter() - t0) * 1000), summary=out.summary,
                                    evidence_ids=[ev.id]))
        return call, out
