"""Scoped graph retrieval (PRD FR-04 / AC-08): a subsystem plus its immediate external dependencies."""

from __future__ import annotations

from ..models import EdgeRelation, GraphEdge, GraphNode, GraphSnapshot, NodeKind

# Relations we follow out of a scope. `calls` is excluded so unrelated modules don't leak in
# through shared entry points like setup()/loop().
_FOLLOW = {EdgeRelation.configures, EdgeRelation.controls, EdgeRelation.connected_to, EdgeRelation.powered_by,
           EdgeRelation.contains}


def scope(snapshot: GraphSnapshot, scope_node_id: str, depth: int = 2) -> GraphSnapshot:
    nodes = {n.id: n for n in snapshot.nodes}
    if scope_node_id not in nodes:
        raise KeyError(scope_node_id)
    root = nodes[scope_node_id]
    sub_id = root.subsystem_id if root.kind != NodeKind.subsystem else root.id
    keep = {n.id for n in snapshot.nodes if sub_id and n.subsystem_id == sub_id} | {scope_node_id}
    # hardware children (pins) of kept components
    keep |= {n.id for n in snapshot.nodes if n.parent_id in keep and n.kind == NodeKind.pin}
    frontier = set(keep)
    for _ in range(depth):
        nxt = set()
        for e in snapshot.edges:
            if e.relation not in _FOLLOW:
                continue
            if e.source_id in frontier and e.target_id not in keep:
                nxt.add(e.target_id)
            if e.target_id in frontier and e.source_id not in keep and e.relation != EdgeRelation.contains:
                nxt.add(e.source_id)
        # don't pull in other subsystems' source code via shared hardware
        nxt = {i for i in nxt if nodes[i].kind not in (NodeKind.function, NodeKind.source_module, NodeKind.subsystem)}
        keep |= nxt
        frontier = nxt
    # parents of kept pins (e.g. the MCU) so the view is coherent
    keep |= {nodes[i].parent_id for i in list(keep) if nodes[i].parent_id and nodes[nodes[i].parent_id].kind == NodeKind.mcu}
    return GraphSnapshot(
        project_id=snapshot.project_id, version=snapshot.version, created_at_utc=snapshot.created_at_utc,
        nodes=[n for n in snapshot.nodes if n.id in keep],
        edges=[e for e in snapshot.edges if e.source_id in keep and e.target_id in keep],
    )


def node_map(nodes: list[GraphNode]) -> dict[str, GraphNode]:
    return {n.id: n for n in nodes}


def edge_map(edges: list[GraphEdge]) -> dict[str, GraphEdge]:
    return {e.id: e for e in edges}
