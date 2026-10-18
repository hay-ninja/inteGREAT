"""Canonical data contracts (PRD §10, plus D-003 additions).

Single source of truth: the frontend types are generated from the OpenAPI schema these produce.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class Model(BaseModel):
    # Defaults are always present in responses, so mark them required in the output schema (typed TS client).
    model_config = ConfigDict(extra="forbid", use_enum_values=False, json_schema_serialization_defaults_required=True)


# ---------------------------------------------------------------- enums


class Verification(StrEnum):
    """Confidence category for graph nodes/edges (PRD FR-03)."""

    observed = "observed"
    verified = "verified"
    inferred = "inferred"
    unverified = "unverified"
    conflicting = "conflicting"


class Epistemic(StrEnum):
    """What kind of knowledge a piece of evidence is (PRD §9.3)."""

    observed = "observed"
    verified = "verified"
    inferred = "inferred"
    unknown = "unknown"


class NodeKind(StrEnum):
    subsystem = "subsystem"
    source_module = "source_module"
    function = "function"
    mcu = "mcu"
    pin = "pin"
    component = "component"
    power_source = "power_source"
    interface = "interface"
    test = "test"
    observation = "observation"


class EdgeRelation(StrEnum):
    contains = "contains"
    calls = "calls"
    configures = "configures"
    controls = "controls"
    connected_to = "connected_to"
    powered_by = "powered_by"
    reads_from = "reads_from"
    observed_by = "observed_by"
    depends_on = "depends_on"


class EdgeOrigin(StrEnum):
    """Where an edge came from. FR-03: call graph, declared wiring and inferred dependency must differ."""

    structural = "structural"
    source_call_graph = "source_call_graph"
    source_config = "source_config"
    declared_wiring = "declared_wiring"
    inferred_dependency = "inferred_dependency"


class GraphLayer(StrEnum):
    """Projection of the ONE canonical graph (D-023). Ids/provenance are unchanged per layer."""

    combined = "combined"
    hardware = "hardware"
    software = "software"


class EvidenceKind(StrEnum):
    source_excerpt = "source_excerpt"
    manifest_entry = "manifest_entry"
    netlist_entry = "netlist_entry"
    serial_line = "serial_line"
    host_command = "host_command"
    cv_measurement = "cv_measurement"
    tool_output = "tool_output"
    engineer_assertion = "engineer_assertion"
    rule_result = "rule_result"
    shadow_residual = "shadow_residual"  # digital-shadow model output; always epistemic=inferred


# ---------------------------------------------------------------- evidence (D-003)


class Provenance(Model):
    source_id: str  # e.g. "repo", "manifest", "serial:replay/good", "camera:0"
    file: str | None = None  # repo-relative, forward slashes
    line_start: int | None = None
    line_end: int | None = None
    captured_at_utc: datetime | None = None
    monotonic_ns: int | None = None


class Evidence(Model):
    id: str
    project_id: str
    kind: EvidenceKind
    epistemic: Epistemic
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
    test_run_id: str | None = None
    raw_ref: str | None = None


# ---------------------------------------------------------------- graph


AttrValue = str | int | float | bool | None


class GraphNode(Model):
    id: str
    project_id: str
    kind: NodeKind
    label: str
    subsystem_id: str | None = None
    parent_id: str | None = None  # structural parent for expand/collapse
    attributes: dict[str, AttrValue] = Field(default_factory=dict)
    verification: Verification
    evidence_ids: list[str] = Field(default_factory=list)


class GraphEdge(Model):
    id: str
    project_id: str
    source_id: str
    target_id: str
    relation: EdgeRelation
    origin: EdgeOrigin
    verification: Verification
    label: str | None = None
    attributes: dict[str, AttrValue] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class ImportIssue(Model):
    level: Literal["info", "warning", "error"]
    code: str
    message: str
    file: str | None = None
    line: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    related_edge_ids: list[str] = Field(default_factory=list)


class GraphSnapshot(Model):
    project_id: str
    version: int
    created_at_utc: datetime = Field(default_factory=utcnow)
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class Project(Model):
    id: str
    name: str
    repo_root: str
    manifest_path: str | None
    created_at_utc: datetime = Field(default_factory=utcnow)
    graph_version: int = 1
    issues: list[ImportIssue] = Field(default_factory=list)
    file_count: int = 0
    hardware_source: Literal["manifest", "netlist", "none"] = "manifest"
    netlist_path: str | None = None
    netlist_mapping: dict[str, Any] | None = None  # engineer-confirmed NetlistMapping
    wiring_overrides: dict[str, Literal["verified", "unverified"]] = Field(default_factory=dict)  # edge id → state
    context: str = ""                             # engineer notes fed into agent packets + repair briefs
    subsystem_names: dict[str, str] = Field(default_factory=dict)  # subsystem id → display-name override


class Subsystem(Model):
    id: str
    label: str
    module_ids: list[str]
    component_ids: list[str]


# ---------------------------------------------------------------- tests & expectations


class ExpectationTrigger(Model):
    kind: Literal["configured_serial_command", "external_sequence"]
    value: str


class Expectation(Model):
    id: str
    project_id: str
    test_definition_id: str
    component_id: str
    trigger: ExpectationTrigger
    metric: str = "servo_angle_deg"  # free-form; known: "servo_angle_deg" (deg), "led_state" (0/1)
    unit: str = "deg"
    target: float
    tolerance: float
    deadline_ms: int
    measurement_source: str = "camera"
    ack_pattern: str | None = None  # serial line prefix that counts as firmware acknowledgement
    on_level: str | None = None  # level the code drives for the "on" state (binary metrics; None = unresolved)
    # steady = end-state check (current behaviour); toggle = oscillation must reach
    # min_transitions within the window (FLICKER/BLINK-style commands — D-060).
    pattern: Literal["steady", "toggle"] = "steady"
    min_transitions: int = 4  # state changes required for a toggle pattern to pass
    min_motion_deg: float = 5.0  # displacement below this counts as "no physical motion" (analog metrics)
    min_valid_samples: int = 3
    confirmed_by_engineer: bool = False
    proposed_from_evidence_ids: list[str] = Field(default_factory=list)
    rationale: str | None = None


class ExpectationEdit(Model):
    target: float | None = None
    tolerance: float | None = None
    deadline_ms: int | None = None
    trigger_value: str | None = None
    pattern: Literal["steady", "toggle"] | None = None
    min_transitions: int | None = None


class ProposeExpectationRequest(Model):
    """Optional targeting for rigs with more than one testable component (D-057)."""

    component_id: str | None = None  # graph node id; default = first known component
    command: str | None = None       # command literal; default = the preferred ON command


class ObservationSourceSpec(Model):
    """replay = recorded/synthetic file; sim = simulated environment through the live pipeline; live = real devices."""

    kind: Literal["replay", "live", "sim"]
    scenario: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")


class TestRunState(StrEnum):
    configured = "configured"
    running = "running"
    completed = "completed"
    failed = "failed"  # the run itself errored (not "expectation failed")
    cancelled = "cancelled"


class ExpectationOutcome(StrEnum):
    passed = "pass"
    failed = "fail"
    inconclusive = "inconclusive"


class Fact(Model):
    """The three distinct facts PRD §5.3 says must never be conflated. `physical_motion` is the
    analog form (displacement), `physical_state` the binary form (state reached) — same slot,
    different metric family."""

    key: Literal["command_sent", "command_acknowledged", "physical_motion", "physical_state",
                 "state_transitions", "first_response"]
    label: str
    value: Literal["yes", "no", "unknown"]
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class ExpectationResult(Model):
    outcome: ExpectationOutcome
    reason: str
    final_valid_value: float | None
    max_displacement: float | None
    valid_samples: int
    invalid_samples: int
    facts: list[Fact]
    evidence_id: str  # rule_result evidence for this evaluation


class TestRun(Model):
    __test__ = False  # not a pytest class
    id: str
    project_id: str
    expectation_id: str
    attempt_kind: Literal["initial", "repeat", "verify"] = "initial"
    verifies_test_run_id: str | None = None
    source: ObservationSourceSpec
    synthetic: bool = False
    state: TestRunState = TestRunState.configured
    started_at_utc: datetime | None = None
    ended_at_utc: datetime | None = None
    result: ExpectationResult | None = None
    incident_id: str | None = None
    error: str | None = None


class Observation(Model):
    id: str
    project_id: str
    test_run_id: str
    source_type: Literal["opencv", "replay_cv", "sim_cv"]
    source_id: str
    component_id: str
    timestamp_utc: datetime
    elapsed_ms: int
    metric: str
    value: float | None
    unit: str
    measurement_quality: Literal["valid", "marker_not_found", "led_not_found",
                                 "calibration_invalid", "dropped"]
    evidence_ref: str
    evidence_id: str


class SerialEvent(Model):
    id: str
    project_id: str
    test_run_id: str
    direction: Literal["rx", "tx"]
    timestamp_utc: datetime
    elapsed_ms: int
    raw: str
    evidence_id: str
    matched_function_ids: list[str] = Field(default_factory=list)  # D-007 log-literal matching


# ---------------------------------------------------------------- event flow (D-024)


class FlowLane(StrEnum):
    """Chronological lanes for one test run. Lanes describe *what kind of record* an event is,
    not a fictional execution DAG (D-024)."""

    command = "command"      # host test command / external trigger
    software = "software"    # serial traffic and other software-side records
    hardware = "hardware"    # camera observations
    result = "result"        # evaluation, incidents, verification


class FlowEventKind(StrEnum):
    command_sent = "command_sent"
    external_trigger = "external_trigger"
    serial_rx = "serial_rx"
    missing_ack = "missing_ack"
    cv_segment = "cv_segment"          # aggregated consecutive camera samples
    evaluation = "evaluation"
    incident_opened = "incident_opened"
    run_completed = "run_completed"


class FlowEvent(Model):
    """One item on the persisted chronological Event flow. Derived deterministically from
    persisted records (D-024); ids stay stable across reloads."""

    id: str
    test_run_id: str
    lane: FlowLane
    kind: FlowEventKind
    label: str
    detail: str | None = None
    timestamp_utc: datetime | None = None   # None = host never recorded one
    elapsed_ms: int | None = None           # None = unknown; `order` is the fallback sort
    elapsed_end_ms: int | None = None       # end of an aggregated segment
    order: int                              # stable secondary ordering; never claims precision
    state: Literal["observed", "expected", "inferred"] = "observed"
    quality: str | None = None              # e.g. valid / marker_not_found / fail
    evidence_ids: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    aggregated_ids: list[str] = Field(default_factory=list)  # underlying obs/serial record ids
    note: str | None = None


class EventFlow(Model):
    run_id: str
    project_id: str
    attempt_kind: Literal["initial", "repeat", "verify"]
    run_state: TestRunState
    source: ObservationSourceSpec
    synthetic: bool
    correlation: str  # honest timing semantics, e.g. "host-clock correlated (not synchronized)"
    deadline_ms: int
    lanes: list[FlowLane]
    events: list[FlowEvent]
    gaps: list[str] = Field(default_factory=list)  # e.g. "no firmware acknowledgement observed"


# ---------------------------------------------------------------- remote repair (Devin) — D-025


class RepairState(StrEnum):
    """Local lifecycle mapped from Devin session states. `uncertain` = create timed out; the
    session may exist remotely but we cannot know without a session id."""

    preparing = "preparing"
    queued = "queued"
    working = "working"
    needs_input = "needs_input"
    ready_for_review = "ready_for_review"
    failed = "failed"
    uncertain = "uncertain"


class RepoSnapshot(Model):
    """What the repair was based on (D-025). `dirty_files` are NOT included in the remote session."""

    repo_root: str
    git_toplevel: str | None = None          # enclosing git repo if repo_root is nested
    remote_url: str | None = None
    repo_ref: str | None = None              # "owner/name" derived from remote_url or configured
    base_revision: str | None = None         # commit SHA
    relative_path: str | None = None         # repo_root path inside git_toplevel, if nested
    dirty_files: list[str] = Field(default_factory=list)
    checked_at_utc: datetime = Field(default_factory=utcnow)


class RepairResult(Model):
    """Remote result, reviewable. Never treated as a hardware fix (D-025)."""

    pull_requests: list[str] = Field(default_factory=list)
    structured_output: dict[str, Any] | None = None
    acus_consumed: float | None = None
    session_status_detail: str | None = None


class RepairJob(Model):
    id: str
    project_id: str
    incident_id: str
    attempt: int = 1
    state: RepairState = RepairState.preparing
    snapshot: RepoSnapshot
    devin_session_id: str | None = None
    session_url: str | None = None
    brief_text: str                          # exact prompt sent — audit of "what data was sent"
    brief_evidence_ids: list[str] = Field(default_factory=list)
    requested_by: Literal["engineer"] = "engineer"
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    result: RepairResult | None = None
    created_at_utc: datetime = Field(default_factory=utcnow)
    updated_at_utc: datetime = Field(default_factory=utcnow)


class RepairPreflight(Model):
    """What `POST .../repairs` would need to succeed — precise missing prerequisites, not guessing."""

    ready: bool
    devin_configured: bool
    unavailable_reason: str | None = None
    issues: list[str] = Field(default_factory=list)    # blocking prerequisites
    warnings: list[str] = Field(default_factory=list)  # non-blocking
    snapshot: RepoSnapshot | None = None
    software_evidence: bool = False                    # incident has evidence of a software issue
    active_job_id: str | None = None                   # a non-terminal job already exists


class RepairRequest(Model):
    acknowledge_uncommitted: bool = False  # required when snapshot has dirty files


# ---------------------------------------------------------------- incidents, hypotheses, actions


class IncidentState(StrEnum):
    open = "open"
    investigating = "investigating"
    awaiting_engineer = "awaiting_engineer"
    verifying = "verifying"
    resolved = "resolved"
    inconclusive = "inconclusive"


class FaultCode(StrEnum):
    GPIO_CONFIG_MISMATCH = "GPIO_CONFIG_MISMATCH"
    NO_PHYSICAL_MOTION = "NO_PHYSICAL_MOTION"
    MISSING_SERIAL_ACK = "MISSING_SERIAL_ACK"
    CAMERA_MEASUREMENT_UNAVAILABLE = "CAMERA_MEASUREMENT_UNAVAILABLE"
    POSSIBLE_POWER_OR_SIGNAL_FAULT = "POSSIBLE_POWER_OR_SIGNAL_FAULT"
    INVERTED_LOGIC = "INVERTED_LOGIC"  # code's on-level doesn't match the declared wiring polarity
    AGENT_PROPOSED = "AGENT_PROPOSED"  # hypothesis proposed by an LLM agent; always starts unverified


class HypothesisStatus(StrEnum):
    plausible = "plausible"
    unverified = "unverified"
    supported = "supported"
    weakened = "weakened"
    ruled_out = "ruled_out"


class Hypothesis(Model):
    id: str
    incident_id: str
    fault_code: FaultCode
    title: str
    explanation: str
    rank: int  # qualitative order; ties allowed. No probabilities (PRD FR-07).
    status: HypothesisStatus
    origin: Literal["rule", "agent"] = "rule"
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    recommended_action_ids: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    related_edge_ids: list[str] = Field(default_factory=list)


class ActionKind(StrEnum):
    run_readonly_tool = "run_readonly_tool"
    request_manual_check = "request_manual_check"
    repeat_test = "repeat_test"
    expand_scope = "expand_scope"
    inspect_source = "inspect_source"
    inspect_connection = "inspect_connection"
    verify_fix = "verify_fix"
    ask_clarification = "ask_clarification"
    prepare_software_fix = "prepare_software_fix"  # remote Devin proposal workflow (D-025)


class ExpectedOutcome(Model):
    result: str  # e.g. "Connected"
    interpretation: str


class DiagnosticAction(Model):
    id: str
    incident_id: str
    kind: ActionKind
    label: str
    rationale: str
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    permission_category: str | None = None
    approval_required: bool = False
    status: Literal["proposed", "running", "completed", "denied", "failed"] = "proposed"
    expected_outcomes: list[ExpectedOutcome] = Field(default_factory=list)
    manual_instructions: list[str] = Field(default_factory=list)
    result_choices: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    recommended: bool = False


class Incident(Model):
    id: str
    project_id: str
    test_run_id: str
    expectation_id: str
    state: IncidentState
    title: str
    fault_codes: list[FaultCode]
    hypothesis_ids: list[str]
    action_ids: list[str]
    created_at_utc: datetime = Field(default_factory=utcnow)
    resolved_by_test_run_id: str | None = None
    agent_rounds_used: int = 0
    agent_summary: str | None = None
    agent_contradictions: list[str] = Field(default_factory=list)
    agent_check_explanation: str = ""  # what the recommended check would establish, per outcome
    agent_recommended_action_id: str | None = None


class Highlight(Model):
    element_id: str  # node or edge id
    style: Literal["failed_expectation", "conflict", "observed", "unknown", "suspect"]
    reason: str


class CausalStep(Model):
    """One link in the fixed cyber-physical causal chain for a run (diagnostics/causal.py)."""

    key: str  # command_sent | command_acknowledged | signal_path | physical_motion | observed
    label: str
    value: Literal["yes", "no", "unknown", "unmeasured"]
    inferred: bool = False  # True when the value was deduced, not directly observed
    evidence_ids: list[str] = Field(default_factory=list)
    breaks_if: str | None = None  # which fault state would interrupt this link


class InvestigationView(Model):
    incident: Incident
    test_run: TestRun  # the run that opened the incident
    followup_runs: list[TestRun] = Field(default_factory=list)  # repeat/verify runs, oldest first
    hypotheses: list[Hypothesis]
    actions: list[DiagnosticAction]
    evidence: list[Evidence]  # every evidence item referenced above
    highlights: list[Highlight]
    permissions: list[PermissionGrant] = Field(default_factory=list)  # active grants
    tool_calls: list[ToolCall] = Field(default_factory=list)  # audit trail, newest last
    messages: list[Evidence] = Field(default_factory=list)  # engineer free-text inputs
    agent_runs: list["AgentRun"] = Field(default_factory=list)
    repair_jobs: list[RepairJob] = Field(default_factory=list)
    causal_chain: list[CausalStep] = Field(default_factory=list)


# ---------------------------------------------------------------- API payloads


class ImportRequest(Model):
    repo_path: str
    manifest_path: str | None = None
    netlist_path: str | None = None
    netlist_mapping: dict[str, Any] | None = None  # confirmed mapping from /netlist/preview; required with netlist
    name: str | None = None


class ProjectUpdate(Model):
    """Engineer edits to an existing project. Any *_path change (or rescan=True) rebuilds the graph
    from the new inputs in place — same project id, graph_version + 1, wiring confirmations kept.
    Fields left as None keep their current value."""

    name: str | None = Field(default=None, max_length=200)
    context: str | None = Field(default=None, max_length=8000)
    subsystem_names: dict[str, str] | None = None  # subsystem id → display name ("" clears the override)
    repo_path: str | None = None
    manifest_path: str | None = None
    netlist_path: str | None = None
    netlist_mapping: dict[str, Any] | None = None
    rescan: bool = False


class StartTestRequest(Model):
    expectation_id: str
    source: ObservationSourceSpec


class ManualResultRequest(Model):
    action_id: str
    result: str
    note: str | None = Field(default=None, max_length=2000)


class ExecuteActionRequest(Model):
    """`source` overrides the observation source for repeat/verify runs. `approve_once` is the engineer
    individually approving one tool call whose category is not granted (never available to agents)."""

    source: ObservationSourceSpec | None = None
    approve_once: bool = False


class LogLiteral(Model):
    function_id: str | None
    text: str
    evidence_id: str


class ProjectAnalysis(Model):
    """Parsed facts needed at test time (e.g. D-007 log-literal matching). Stored per project."""

    id: str  # == project_id
    project_id: str
    log_literals: list[LogLiteral]


class SourceExcerpt(Model):
    file: str
    line_start: int
    lines: list[str]
    highlight_lines: list[int]
    evidence_id: str


class ActionResult(Model):
    action_id: str
    status: Literal["completed", "denied", "failed"]
    summary: str
    source_excerpts: list[SourceExcerpt] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    test_run_id: str | None = None
    tool_call_id: str | None = None
    node_ids: list[str] = Field(default_factory=list)  # e.g. expanded scope
    lines: list[str] = Field(default_factory=list)  # e.g. serial buffer output


# ---------------------------------------------------------------- tools & permissions (PRD §13, D-004)

PermissionCategory = Literal["repo_read", "netlist_read", "serial_read", "camera_observe", "host_diagnostics_read"]


class PermissionGrant(Model):
    id: str
    project_id: str
    incident_id: str
    category: PermissionCategory
    target: str = "local"  # host/device the grant applies to
    granted_by: Literal["engineer"] = "engineer"
    granted_at_utc: datetime = Field(default_factory=utcnow)
    revoked_at_utc: datetime | None = None


class PermissionUpdate(Model):
    category: PermissionCategory
    granted: bool


class ToolInfo(Model):
    name: str
    permission_category: str
    is_read_only: bool
    available: bool
    description: str
    args_schema: dict[str, Any]


class ToolCall(Model):
    """Audit record for every tool invocation, grant decision and denial (PRD §13.3)."""

    id: str
    project_id: str
    incident_id: str | None
    tool_name: str
    permission_category: str
    arguments: dict[str, Any]
    caller: str  # "engineer" | "context_engine" | "agent:<name>"
    decision: Literal["granted", "approved_once", "denied", "unavailable", "invalid"]
    status: Literal["completed", "denied", "failed"]
    started_at_utc: datetime = Field(default_factory=utcnow)
    duration_ms: int = 0
    summary: str = ""
    error: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class WiringVerificationRequest(Model):
    edge_id: str
    verification: Literal["verified", "unverified"]
    note: str | None = Field(default=None, max_length=2000)


class MessageRequest(Model):
    text: str = Field(min_length=1, max_length=2000)


class DemoFixture(Model):
    label: str
    repo_path: str
    manifest_path: str


class ReplayInfo(Model):
    id: str
    description: str
    synthetic: bool


class IntegreatEvent(Model):
    """WebSocket envelope (PRD §15)."""

    seq: int = 0
    type: str
    project_id: str
    investigation_id: str | None = None
    test_run_id: str | None = None
    timestamp_utc: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------- agents (PRD §10.5, §11)


class AgentName(StrEnum):
    orchestrator = "orchestrator"
    code = "code"
    hardware = "hardware"
    telemetry = "telemetry"
    vision = "vision"
    critic = "critic"  # adversarial pass: tries to invalidate leading hypotheses
    runtime_vision = "runtime_vision"  # legacy: persisted AgentRuns may still carry this


class AgentFinding(Model):
    statement: str
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    epistemic_status: Literal["inferred", "hypothesis"] = "inferred"


class AgentReport(Model):
    agent: AgentName
    investigation_id: str
    scope_node_ids: list[str]
    findings: list[AgentFinding]
    unknowns: list[str] = Field(default_factory=list)
    proposed_action_ids: list[str] = Field(default_factory=list)


class ContextPacketSummary(Model):
    """What an agent was shown (PRD §10.8) — stored for audit; the full text is not persisted."""

    investigation_id: str
    focus_node_ids: list[str]
    included_node_ids: list[str]
    evidence_ids: list[str]
    tool_call_ids: list[str]
    known_unknowns: list[str]
    omitted_context_summary: str
    max_token_budget: int
    estimated_tokens: int


class AgentRun(Model):
    id: str
    incident_id: str
    project_id: str
    round: int
    agent: AgentName
    status: Literal["completed", "failed", "timeout", "invalid", "skipped"]
    started_at_utc: datetime = Field(default_factory=utcnow)
    duration_ms: int = 0
    model: str | None = None
    provider: str | None = None  # "stepfun" | "gemini" | None (deterministic fallback)
    context: ContextPacketSummary | None = None
    report: AgentReport | None = None
    summary: str | None = None  # orchestrator synthesis text
    dispatched: list[AgentName] = Field(default_factory=list)  # orchestrator triage
    validation_errors: list[str] = Field(default_factory=list)
    error: str | None = None


class ProviderStatus(Model):
    """Per-stage provider attribution (D-023): orchestration may come from a different
    provider than the specialists."""

    role: str  # "orchestrator" | "specialists"
    provider: str  # "stepfun" | "gemini" | "none"
    model: str | None
    available: bool
    reason: str | None = None


class AgentStatus(Model):
    available: bool  # at least one stage has a live provider
    provider: str  # short label for the header chip, e.g. "stepfun+gemini" / "deterministic"
    model: str | None
    reason: str | None = None
    stages: list[ProviderStatus] = Field(default_factory=list)


# ---------------------------------------------------------------- devices (PRD FR-06)


class SerialPortInfo(Model):
    port: str
    description: str
    hwid: str


class SerialStatus(Model):
    connected: bool
    port: str | None
    baud: int
    last_error: str | None
    ports: list[SerialPortInfo]


class CameraStatus(Model):
    connected: bool
    source_id: str | None
    fps: float
    calibrated: bool
    calibrations: list[str] = Field(default_factory=list)  # "metric:component_id" keys ready to measure
    offset_deg: float | None
    last_error: str | None


class DeviceStatus(Model):
    serial: SerialStatus
    camera: CameraStatus


class SerialConnectRequest(Model):
    port: str = Field(max_length=64)
    baud: int = Field(default=115200, ge=1200, le=2_000_000)


class CameraConnectRequest(Model):
    index: int = Field(default=0, ge=0, le=16)
    stream_url: str | None = Field(default=None, min_length=1, max_length=512)


class BrowserCameraPairing(Model):
    url: str
    expires_in_seconds: int


class VisualRegion(Model):
    x: float = Field(ge=0, lt=1, allow_inf_nan=False)
    y: float = Field(ge=0, lt=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)


class VisualCaptureRequest(Model):
    component_id: str
    region: VisualRegion
    state: Literal["off", "on"]


class VisualReference(Model):
    id: str
    project_id: str
    component_id: str
    camera_id: str
    region: VisualRegion
    state: Literal["off", "on"]
    frame_width: int
    frame_height: int
    contrast: float
    background: float
    evidence_id: str


class VisualConfigRequest(Model):
    reference_ids: list[str] = Field(min_length=4, max_length=4)
    duration_ms: int = Field(default=8000, ge=6000, le=20000)
    confirmed: bool


class VisualConfig(Model):
    id: str
    project_id: str
    references: list[VisualReference]
    duration_ms: int
    evidence_id: str


class VisualRunRequest(Model):
    config_id: str
    verifies_run_id: str | None = None


class VisualSample(Model):
    component_id: str
    elapsed_ms: int
    brightness: float | None
    quality: Literal["valid", "unavailable"]
    evidence_id: str


class VisualRun(Model):
    id: str
    project_id: str
    config_id: str
    source_id: str
    synthetic: bool = False
    state: Literal["running", "completed", "failed"] = "running"
    outcome: Literal["pass", "fail", "inconclusive"] | None = None
    summary: str = "Observing camera; no board command is sent."
    samples: list[VisualSample] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    verifies_run_id: str | None = None
    resolved_by_run_id: str | None = None
    checks: dict[str, str] = Field(default_factory=dict)


class CalibrateRequest(Model):
    mode: Literal["angle", "led_baseline"] = "angle"
    component_id: str | None = None
    known_angle_deg: float | None = Field(default=None, ge=-90, le=270)


class LocateLedRequest(Model):
    """Blink-to-find (D-054): engineer-initiated serial toggles; the camera diffs on vs off
    frames and the changed blob is the LED. Commands are engineer-confirmed fixed strings."""
    component_id: str
    on_command: str = Field(min_length=1, max_length=64)
    off_command: str = Field(min_length=1, max_length=64)
    cycles: int = Field(default=2, ge=1, le=5)


class LedLocateResult(Model):
    found: bool
    roi: list[int] | None = None          # accepted ROI when exactly one candidate
    candidates: list[list[int]] = []      # all candidate ROIs when ambiguous, largest first
    message: str = ""


class LedRoiRequest(Model):
    """Manual or pick-a-candidate LED region for one component (D-054)."""
    component_id: str
    roi: list[int] = Field(min_length=4, max_length=4)  # [x, y, w, h] in frame pixels
    calibrate_baseline: bool = True  # assert the LED is currently OFF and record baseline


class SaveReplayRequest(Model):
    name: str = Field(pattern=r"^[a-z0-9_]{3,60}$")


class NetlistPreviewRequest(Model):
    netlist_path: str
    repo_path: str | None = None


class NetlistPreview(Model):
    file: str
    components: list[dict[str, Any]]
    nets: list[dict[str, Any]]
    proposed_mapping: dict[str, Any]
    warnings: list[str]


class RunRecording(Model):
    """Raw event stream of a completed run, kept so it can be saved as a replay fixture."""

    id: str  # test run id
    project_id: str
    events: list[dict[str, Any]]
    command: str | None = None


InvestigationView.model_rebuild()
