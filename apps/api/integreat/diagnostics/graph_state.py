"""Write run observations back onto the canonical graph — the temporal state layer (DSG-lite).

Structure is built at import; run state is an overlay on top of it. Attributes are
metric-keyed, evidence-cited, and copied forward across rescans when node/edge ids resolve.

Honesty rules:
- "observed" traversal means a runtime record demonstrates the edge carried its effect —
  never that we measured a voltage or waveform.
- There is no "interrupted" state on physical edges: missing motion or missing frames
  cannot localise a break to a wire, so absence is recorded as "unobserved".
- `powered_by` edges are never marked traversed: power is never measured.
"""

from __future__ import annotations

from ..models import (
    EdgeRelation,
    Expectation,
    ExpectationResult,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    SerialEvent,
)

_COMPONENT_KEYS = ("obs_metric", "obs_value", "obs_residual", "obs_tolerance", "obs_quality",
                   "obs_outcome", "obs_run_id", "obs_evidence_id")
_FUNCTION_KEYS = ("run_executed", "run_executed_run_id", "run_executed_evidence_id")
_EDGE_KEYS = ("traversal", "traversal_run_id", "traversal_evidence_id")


def _fact(result: ExpectationResult, key: str):
    return next((f for f in result.facts if f.key == key), None)


def record_run_state(g: GraphSnapshot, exp: Expectation, result: ExpectationResult, run_id: str,
                     serial: list[SerialEvent]) -> bool:
    """Annotate g's nodes/edges with this run's observed state. Returns True if changed."""
    changed = False
    motion = _fact(result, "physical_motion")
    motion_yes = bool(motion and motion.value == "yes")

    # ---- component node: metric-keyed residual ------------------------------- Δx = observed − nominal
    node = next((n for n in g.nodes if n.id == exp.component_id), None)
    if node is not None:
        final = result.final_valid_value
        node.attributes.update({
            "obs_metric": exp.metric,
            "obs_value": final,
            "obs_residual": round(final - exp.target, 2) if final is not None else None,
            "obs_tolerance": exp.tolerance,
            "obs_quality": f"{result.valid_samples} valid / {result.invalid_samples} invalid",
            "obs_outcome": result.outcome.value,
            "obs_run_id": run_id,
            "obs_evidence_id": result.evidence_id,
        })
        if result.evidence_id not in node.evidence_ids:
            node.evidence_ids.append(result.evidence_id)
        changed = True

    # ---- function nodes: executed when a serial line matched its log literals (D-007)
    executed: set[str] = set()
    exec_ev: dict[str, str] = {}
    for se in serial:
        for fid in se.matched_function_ids:
            executed.add(fid)
            exec_ev.setdefault(fid, se.evidence_id)
    for n in g.nodes:
        if n.id not in executed:
            continue
        n.attributes.update({"run_executed": "observed", "run_executed_run_id": run_id,
                             "run_executed_evidence_id": exec_ev[n.id]})
        if exec_ev[n.id] not in n.evidence_ids:
            n.evidence_ids.append(exec_ev[n.id])
        changed = True

    # ---- edges: traversal state ----------------------------------------------
    comp_pins = {n.id for n in g.nodes if n.parent_id == exp.component_id or
                 n.id.startswith(f"pin:{exp.component_id.removeprefix('component:')}.")}
    for e in g.edges:
        if e.relation == EdgeRelation.controls and e.target_id == exp.component_id:
            state = "observed" if (motion_yes or e.source_id in executed) else "unobserved"
            ev_id = (motion.evidence_ids[0] if motion_yes and motion and motion.evidence_ids
                     else exec_ev.get(e.source_id, result.evidence_id))
        elif (e.relation == EdgeRelation.connected_to and e.attributes.get("kind") == "signal"
              and comp_pins & {e.source_id, e.target_id}):
            # Motion proves a signal reached the component; no motion cannot localise the break.
            state = "observed" if motion_yes else "unobserved"
            ev_id = result.evidence_id
        else:
            continue
        e.attributes.update({"traversal": state, "traversal_run_id": run_id,
                             "traversal_evidence_id": ev_id})
        if ev_id not in e.evidence_ids:
            e.evidence_ids.append(ev_id)
        changed = True
    return changed


def reapply_run_state(old: GraphSnapshot, new_nodes: list[GraphNode], new_edges: list[GraphEdge]) -> int:
    """Copy run-state attributes from the previous snapshot onto rebuilt elements whose ids
    still resolve (rescan keeps identity, D-019). Returns the number of elements updated."""
    old_nodes = {n.id: n for n in old.nodes}
    old_edges = {e.id: e for e in old.edges}
    count = 0
    for n in new_nodes:
        o = old_nodes.get(n.id)
        if o is None:
            continue
        copied = {k: v for k, v in o.attributes.items()
                  if k in _COMPONENT_KEYS + _FUNCTION_KEYS}
        if not copied:
            continue
        n.attributes.update(copied)
        for ev in (copied.get("obs_evidence_id"), copied.get("run_executed_evidence_id")):
            if ev and ev not in n.evidence_ids:
                n.evidence_ids.append(ev)
        count += 1
    for e in new_edges:
        o = old_edges.get(e.id)
        if o is None:
            continue
        copied = {k: v for k, v in o.attributes.items() if k in _EDGE_KEYS}
        if not copied:
            continue
        e.attributes.update(copied)
        ev = copied.get("traversal_evidence_id")
        if ev and ev not in e.evidence_ids:
            e.evidence_ids.append(ev)
        count += 1
    return count
