"""Subsystem-scoped, bounded context packets for agents (PRD FR-04, §10.8, AC-08).

Deterministic filtering only: the selected subsystem's graph neighbourhood, the incident's evidence,
and tool output prefetched through the SAME permission-checked executor (caller="context_engine",
D-004). Ungranted categories are omitted and the omission is stated. Secrets are redacted. Never the
whole repo, full video, or unbounded logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..graph.query import scope as scope_graph
from ..models import (
    AgentName,
    ContextPacketSummary,
    DiagnosticAction,
    EdgeRelation,
    Evidence,
    EvidenceKind,
    Expectation,
    Hypothesis,
    Incident,
)
from ..tools.executor import ToolDenied, ToolFailed

if TYPE_CHECKING:
    from ..service import Service

CHARS_PER_TOKEN = 4
_SECRET = re.compile(r"(?i)(pass(word|wd)?|secret|token|api[_-]?key|ssid)(\s*[=:]\s*|\s+)(\"[^\"]*\"|'[^']*'|\S+)")

# Which prefetched tools each agent gets (all read-only, all registry tools).
AGENT_TOOLS: dict[AgentName, list[tuple[str, dict]]] = {
    AgentName.code: [("inspect_gpio_config", {"component_id": "$component"}), ("read_project_metadata", {})],
    AgentName.hardware: [("read_netlist_connections", {"component_id": "$component"}),
                         ("expand_scope", {"scope_node_id": "$component", "depth": 3})],
    AgentName.runtime_vision: [("read_test_events", {}), ("read_cv_measurements", {}),
                               ("read_serial_buffer", {"max_lines": 40})],
}
AGENT_EDGES = {
    AgentName.code: {EdgeRelation.configures, EdgeRelation.controls, EdgeRelation.calls},
    AgentName.hardware: {EdgeRelation.connected_to, EdgeRelation.powered_by, EdgeRelation.configures},
    AgentName.runtime_vision: {EdgeRelation.controls, EdgeRelation.configures},
}


def redact(text: str) -> str:
    return _SECRET.sub(lambda m: f"{m.group(1)}{m.group(3)}[REDACTED]", text)


@dataclass
class Packet:
    text: str
    summary: ContextPacketSummary
    evidence_ids: set[str]
    action_ids: set[str]
    hypothesis_ids: set[str]
    tool_call_ids: list[str] = field(default_factory=list)


async def build_packet(svc: Service, inc: Incident, agent: AgentName, max_tokens: int) -> Packet:
    project = svc.project(inc.project_id)
    exp = svc.store.get("expectation", inc.expectation_id, Expectation)
    run = svc.test_run(inc.test_run_id)
    g = svc.graph(inc.project_id)
    scoped = scope_graph(g, exp.component_id, 2)
    labels = {n.id: n.label for n in g.nodes}
    view_hyps: list[Hypothesis] = svc.store.get_many("hypothesis", inc.hypothesis_ids, Hypothesis)
    actions: list[DiagnosticAction] = svc.store.get_many("action", inc.action_ids, DiagnosticAction)
    unknowns = sorted({u for h in view_hyps for u in h.unknowns})
    omitted: list[str] = []

    # ---- prefetch tools (permission-checked, audited)
    tool_lines: list[str] = []
    tool_ev: list[str] = []
    tool_calls: list[str] = []
    for name, args in AGENT_TOOLS[agent]:
        args = {k: (exp.component_id if v == "$component" else v) for k, v in args.items()}
        try:
            call, out = await svc.tools.execute(project, inc, name, args, caller="context_engine")
        except ToolDenied as e:
            omitted.append(f"{name}: not run ({e.reason})")
            tool_calls.append(e.call.id)
            continue
        except ToolFailed as e:
            omitted.append(f"{name}: failed ({e.reason})")
            tool_calls.append(e.call.id)
            continue
        tool_calls.append(call.id)
        tool_ev += call.evidence_ids
        tool_lines.append(f"[{call.evidence_ids[0]}] {name}: {out.summary}")
        tool_lines += [f"    {ln}" for ln in out.lines[:30]]
        for ex in out.source_excerpts:
            tool_lines.append(f"    --- {ex.file}:{ex.line_start} (evidence {ex.evidence_id or 'n/a'})")
            tool_lines += [f"    {ex.line_start + i:>4}| {ln}" for i, ln in enumerate(ex.lines)]

    # ---- evidence catalog: everything the agent may cite
    ev_ids = [run.result.evidence_id] + [i for f in run.result.facts for i in f.evidence_ids]
    ev_ids += [i for h in view_hyps for i in h.supporting_evidence_ids + h.contradicting_evidence_ids]
    ev_ids += tool_ev
    ev_ids += [e.id for e in svc.store.list("evidence", Evidence, project_id=inc.project_id)
               if e.kind == EvidenceKind.engineer_assertion and e.payload.get("incident_id") == inc.id]
    for e in scoped.edges:
        if e.relation in AGENT_EDGES[agent]:
            ev_ids += e.evidence_ids
    evidence = svc.evidence(ev_ids)[:60]
    if len(set(ev_ids)) > 60:
        omitted.append(f"{len(set(ev_ids)) - 60} lower-priority evidence items")

    # ---- graph neighbourhood (only relations relevant to this agent)
    edges = [e for e in scoped.edges if e.relation in AGENT_EDGES[agent]]
    graph_lines = [f"{labels[e.source_id]} -[{e.relation.value}; {e.origin.value}; {e.verification.value}]-> "
                   f"{labels[e.target_id]}" for e in edges]
    omitted.append(f"{len(g.nodes) - len(scoped.nodes)} graph nodes outside the "
                   f"{labels.get(exp.component_id, 'component')} neighbourhood")

    sections: list[tuple[str, list[str]]] = [
        ("INCIDENT", [f"{inc.title}; fault codes: {', '.join(c.value for c in inc.fault_codes)}; state {inc.state.value}",
                      f"Expectation: send '{exp.trigger.value}' -> {labels.get(exp.component_id)} angle "
                      f"{exp.target}±{exp.tolerance} deg within {exp.deadline_ms} ms (engineer-confirmed)",
                      f"Result [{run.result.evidence_id}]: {run.result.outcome.value} — {run.result.reason}"]
         + [f"Fact {f.key}: {f.value}" + (f" ({f.note})" if f.note else "") for f in run.result.facts]
         + (["Data source: SYNTHETIC/SIMULATED, not live hardware."] if run.synthetic else [])),
        ("CURRENT HYPOTHESES (rule-based; rank is qualitative)",
         [f"{h.id} | rank {h.rank} | {h.status.value} | {h.title} | unknowns: {'; '.join(h.unknowns) or '-'}"
          for h in view_hyps]),
        ("ACTION CATALOG (you may only propose these ids)",
         [f"{a.id} | {a.kind.value} | {a.label} | {a.rationale}" for a in actions]),
        ("EVIDENCE CATALOG (cite ONLY these ids)",
         [f"{e.id} | {e.kind.value} | {e.epistemic.value} | {e.summary[:220]}" for e in evidence]),
        ("TOOL OUTPUT (prefetched read-only tools)", tool_lines or ["(none)"]),
        ("GRAPH NEIGHBOURHOOD", graph_lines or ["(none)"]),
        ("KNOWN UNKNOWNS", unknowns or ["(none)"]),
    ]
    budget = max_tokens * CHARS_PER_TOKEN
    out, used = [], 0
    for title, lines in sections:
        block = [f"## {title}"]
        for ln in lines:
            ln = redact(ln)
            if used + len(ln) > budget:
                omitted.append(f"truncated section '{title}' at token budget")
                break
            block.append(ln)
            used += len(ln) + 1
        out.append("\n".join(block))
    if omitted:
        out.append("## OMITTED CONTEXT\n" + "\n".join(omitted))
    text = "\n\n".join(out)

    summary = ContextPacketSummary(
        investigation_id=inc.id, focus_node_ids=[exp.component_id], included_node_ids=[n.id for n in scoped.nodes],
        evidence_ids=[e.id for e in evidence], tool_call_ids=tool_calls, known_unknowns=unknowns,
        omitted_context_summary="; ".join(omitted), max_token_budget=max_tokens,
        estimated_tokens=len(text) // CHARS_PER_TOKEN)
    return Packet(text=text, summary=summary, evidence_ids={e.id for e in evidence},
                  action_ids={a.id for a in actions}, hypothesis_ids={h.id for h in view_hyps},
                  tool_call_ids=tool_calls)


def excluded_from_scope(svc: Service, inc: Incident) -> list[str]:
    """Node ids NOT given to agents (used by tests to check AC-08)."""
    exp = svc.store.get("expectation", inc.expectation_id, Expectation)
    g = svc.graph(inc.project_id)
    keep = {n.id for n in scope_graph(g, exp.component_id, 2).nodes}
    return [n.id for n in g.nodes if n.id not in keep]

