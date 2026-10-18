"""Registered diagnostic tools (PRD §13.2). The ONLY things that can be executed on the engineer's behalf.

Every tool is a fixed Python function with a typed argument model. There is no shell, no LLM-authored
command string, no file write, no device write. Agents (future, D-004) may only *select* a tool by name
and supply arguments that validate against its model; execution still goes through tools/executor.py.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from ..diagnostics.rules import config_vs_wiring
from ..graph.query import scope as scope_graph
from ..ingestion.repository import SOURCE_EXTS, RepoError, resolve_inside
from ..models import EdgeOrigin, EdgeRelation, Evidence, EvidenceKind, Incident, Project, SourceExcerpt

if TYPE_CHECKING:
    from ..service import Service

MAX_EXCERPT_LINES = 80
MAX_OUTPUT_LINES = 200

# Categories that P0 never executes, even with approval (PRD §13.1: risky actions not autonomous in MVP).
RISKY_CATEGORIES = {"firmware_flash", "gpio_write", "serial_write", "file_write", "process_control", "reboot"}


@dataclass
class ToolContext:
    svc: Service
    project: Project
    incident: Incident | None
    caller: str


@dataclass
class ToolOutput:
    summary: str
    source_excerpts: list[SourceExcerpt] = field(default_factory=list)
    cited_evidence: list[Evidence] = field(default_factory=list)  # existing evidence the output refers to
    lines: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class ToolSpec:
    name: str
    permission_category: str
    is_read_only: bool
    description: str
    args_model: type[BaseModel]
    run: Callable[[BaseModel, ToolContext], Awaitable[ToolOutput]]
    available: bool = True


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, category: str, description: str, args_model: type[BaseModel], read_only: bool = True):
    def deco(fn):
        REGISTRY[name] = ToolSpec(name, category, read_only, description, args_model, fn)
        return fn
    return deco


# ---------------------------------------------------------------- helpers


def _excerpt(root: Path, file: str, center: int, before: int, after: int, evidence_id: str) -> SourceExcerpt:
    path = resolve_inside(root, file)
    if path.suffix.lower() not in SOURCE_EXTS:
        raise RepoError(f"not a source file: {file}")
    lines = path.read_text(encoding="utf-8").splitlines()
    start = max(1, center - before)
    end = min(len(lines), center + after)
    return SourceExcerpt(file=file, line_start=start, lines=lines[start - 1:end], highlight_lines=[center],
                         evidence_id=evidence_id)


# ---------------------------------------------------------------- repo_read


class InspectGpioArgs(_Args):
    component_id: str = Field(pattern=r"^component:[a-z0-9_]+$")


@tool("inspect_gpio_config", "repo_read",
      "Show the source lines that configure a component's GPIO next to its declared wiring.", InspectGpioArgs)
async def inspect_gpio_config(args: InspectGpioArgs, ctx: ToolContext) -> ToolOutput:
    g = ctx.svc.graph(ctx.project.id)
    cfg, wire, wired_pin = config_vs_wiring(args.component_id, g.nodes, g.edges)
    labels = {n.id: n.label for n in g.nodes}
    ev_ids = [i for e in cfg for i in e.evidence_ids] + (wire.evidence_ids if wire else [])
    cited = ctx.svc.evidence(ev_ids)
    root = Path(ctx.project.repo_root)
    excerpts = [_excerpt(root, e.provenance.file, e.provenance.line_start or 1, 3, 3, e.id)
                for e in cited if e.kind == EvidenceKind.source_excerpt and e.provenance.file]
    configured = sorted({labels[e.target_id] for e in cfg})
    parts = [f"Source configures {', '.join(configured) or 'no resolvable pin'}"]
    parts.append(f"declared wiring: {labels[wired_pin]} ({wire.verification.value})" if wire else "no declared signal wiring")
    if wire and configured:
        parts.append("MATCH" if configured == [labels[wired_pin]] else "MISMATCH")
    return ToolOutput(summary="; ".join(parts), source_excerpts=excerpts,
                      cited_evidence=[e for e in cited if e.kind == EvidenceKind.manifest_entry or e.kind == EvidenceKind.netlist_entry],
                      data={"configured": configured, "wired": labels.get(wired_pin) if wired_pin else None})


class ReadExcerptArgs(_Args):
    file: str = Field(min_length=1, max_length=300)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


@tool("read_source_excerpt", "repo_read", "Read a bounded line range (≤80 lines) from an imported source file.",
      ReadExcerptArgs)
async def read_source_excerpt(args: ReadExcerptArgs, ctx: ToolContext) -> ToolOutput:
    if args.line_end < args.line_start or args.line_end - args.line_start + 1 > MAX_EXCERPT_LINES:
        raise ValueError(f"line range must be 1..{MAX_EXCERPT_LINES} lines")
    ex = _excerpt(Path(ctx.project.repo_root), args.file, args.line_start, 0, args.line_end - args.line_start, "")
    return ToolOutput(summary=f"{args.file}:{args.line_start}-{args.line_end}", source_excerpts=[ex])


class SearchArgs(_Args):
    query: str = Field(min_length=2, max_length=100)
    max_results: int = Field(default=20, ge=1, le=50)


@tool("search_source", "repo_read", "Case-insensitive literal text search across imported source files.", SearchArgs)
async def search_source(args: SearchArgs, ctx: ToolContext) -> ToolOutput:
    root = Path(ctx.project.repo_root)
    q = args.query.lower()
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if len(hits) >= args.max_results:
            break
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTS or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if any(part.startswith(".") or part in {"build", ".pio"} for part in rel.split("/")[:-1]):
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if q in line.lower():
                hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                if len(hits) >= args.max_results:
                    break
    return ToolOutput(summary=f"{len(hits)} match(es) for \"{args.query}\"", lines=hits)


class NoArgs(_Args):
    pass


@tool("read_project_metadata", "repo_read", "Project name, file count, import warnings.", NoArgs)
async def read_project_metadata(args: NoArgs, ctx: ToolContext) -> ToolOutput:
    p = ctx.project
    lines = [f"{i.level.upper()} {i.code}: {i.message}" for i in p.issues if i.level != "info"]
    return ToolOutput(summary=f"{p.name}: {p.file_count} source files, {len(lines)} import warning(s)", lines=lines)


# ---------------------------------------------------------------- netlist_read


class ConnectionsArgs(_Args):
    component_id: str | None = Field(default=None, pattern=r"^component:[a-z0-9_]+$")


@tool("read_netlist_connections", "netlist_read",
      "List declared wiring/power connections (manifest or netlist), optionally for one component.", ConnectionsArgs)
async def read_netlist_connections(args: ConnectionsArgs, ctx: ToolContext) -> ToolOutput:
    g = ctx.svc.graph(ctx.project.id)
    labels = {n.id: n.label for n in g.nodes}
    prefix = f"pin:{args.component_id.removeprefix('component:')}." if args.component_id else None
    out, ev_ids = [], []
    for e in g.edges:
        if e.origin != EdgeOrigin.declared_wiring:
            continue
        if args.component_id and not (e.source_id == args.component_id or e.target_id == args.component_id
                                      or e.source_id.startswith(prefix) or e.target_id.startswith(prefix)):
            continue
        out.append(f"{labels[e.source_id]} —{e.relation.value}/{e.attributes.get('kind', '')}→ {labels[e.target_id]} "
                   f"[{e.verification.value}]")
        ev_ids += e.evidence_ids
    return ToolOutput(summary=f"{len(out)} declared connection(s)", lines=out, cited_evidence=ctx.svc.evidence(ev_ids))


# ---------------------------------------------------------------- serial_read / camera_observe


class SerialBufferArgs(_Args):
    max_lines: int = Field(default=100, ge=1, le=MAX_OUTPUT_LINES)


@tool("read_serial_buffer", "serial_read",
      "Recent serial lines: the live device buffer if connected, else this investigation's recorded runs.",
      SerialBufferArgs)
async def read_serial_buffer(args: SerialBufferArgs, ctx: ToolContext) -> ToolOutput:
    dev = ctx.svc.devices.serial
    if dev.connected:
        lines = [f"{ln.host_time_utc:%H:%M:%S.%f}"[:-3] + f"  {ln.text}" for ln in dev.recent(args.max_lines)]
        return ToolOutput(summary=f"{len(lines)} line(s) from live device {dev.port}", lines=lines,
                          data={"source": "live", "port": dev.port})
    runs = ctx.svc.runs_for_incident(ctx.incident.id) if ctx.incident else []
    lines = []
    for r in runs:
        _, serial = ctx.svc.test_data(r.id)
        lines += [f"[{r.id} {s.elapsed_ms:>5} ms] {'→' if s.direction == 'tx' else '←'} {s.raw}" for s in serial]
    lines = lines[-args.max_lines:]
    return ToolOutput(summary=f"{len(lines)} recorded serial line(s) (no live device connected)", lines=lines,
                      data={"source": "recorded"})


class RunArgs(_Args):
    test_run_id: str | None = Field(default=None, max_length=64)


@tool("read_test_events", "serial_read", "Timeline events (commands, serial, results) for a test run.", RunArgs)
async def read_test_events(args: RunArgs, ctx: ToolContext) -> ToolOutput:
    run_id = args.test_run_id or (ctx.incident.test_run_id if ctx.incident else None)
    if not run_id:
        raise ValueError("test_run_id required")
    run = ctx.svc.test_run(run_id)
    if run.project_id != ctx.project.id:
        raise ValueError("test run belongs to another project")
    obs, serial = ctx.svc.test_data(run_id)
    lines = [f"{s.elapsed_ms:>5} ms {s.direction} {s.raw}" for s in serial]
    if run.result:
        lines.append(f"result: {run.result.outcome.value} — {run.result.reason}")
    return ToolOutput(summary=f"{len(serial)} serial event(s), {len(obs)} camera sample(s) in {run_id}", lines=lines)


@tool("read_cv_measurements", "camera_observe",
      "Summary of camera angle measurements for a test run (first/last/min/max, invalid frames).", RunArgs)
async def read_cv_measurements(args: RunArgs, ctx: ToolContext) -> ToolOutput:
    run_id = args.test_run_id or (ctx.incident.test_run_id if ctx.incident else None)
    if not run_id:
        raise ValueError("test_run_id required")
    obs, _ = ctx.svc.test_data(run_id)
    valid = [o for o in obs if o.measurement_quality == "valid" and o.value is not None]
    if not valid:
        return ToolOutput(summary=f"No valid measurements ({len(obs)} frames, all invalid)",
                          data={"valid": 0, "invalid": len(obs)})
    vals = [o.value for o in valid]
    return ToolOutput(
        summary=(f"{len(valid)} valid / {len(obs) - len(valid)} invalid; first {vals[0]}°, last {vals[-1]}°, "
                 f"min {min(vals)}°, max {max(vals)}°"),
        data={"valid": len(valid), "invalid": len(obs) - len(valid), "first": vals[0], "last": vals[-1],
              "min": min(vals), "max": max(vals)})


# ---------------------------------------------------------------- graph scope (no device access)


class ScopeArgs(_Args):
    scope_node_id: str = Field(max_length=200)
    depth: int = Field(default=3, ge=1, le=5)


@tool("expand_scope", "repo_read", "Return the graph neighbourhood of a node at a larger depth.", ScopeArgs)
async def expand_scope(args: ScopeArgs, ctx: ToolContext) -> ToolOutput:
    g = ctx.svc.graph(ctx.project.id)
    s = scope_graph(g, args.scope_node_id, args.depth)
    power = [n.label for n in s.nodes if n.kind.value == "power_source"]
    wiring = [e for e in s.edges if e.relation in (EdgeRelation.powered_by, EdgeRelation.connected_to)]
    return ToolOutput(summary=f"Scope expanded to {len(s.nodes)} nodes (power: {', '.join(power) or 'none declared'}; "
                              f"{len(wiring)} wiring edge(s))", node_ids=[n.id for n in s.nodes])


def list_tools() -> list[ToolSpec]:
    return list(REGISTRY.values())


def tool_args(tool_name: str | None, arguments: dict[str, Any]) -> dict[str, Any]:
    """Only the arguments the tool's schema declares (action cards may carry UI-only metadata)."""
    spec = REGISTRY.get(tool_name or "")
    if spec is None:
        return dict(arguments)
    return {k: v for k, v in arguments.items() if k in spec.args_model.model_fields}
