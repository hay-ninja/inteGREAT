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
    metric: Literal["servo_angle_deg"] = "servo_angle_deg"
    unit: Literal["deg"] = "deg"
    target: float
    tolerance: float
    deadline_ms: int
    measurement_source: str = "camera"
    ack_pattern: str | None = None  # serial line prefix that counts as firmware acknowledgement
    min_motion_deg: float = 5.0  # displacement below this counts as "no physical motion"
    min_valid_samples: int = 3
    confirmed_by_engineer: bool = False
    proposed_from_evidence_ids: list[str] = Field(default_factory=list)
    rationale: str | None = None


class ExpectationEdit(Model):
    target: float | None = None
    tolerance: float | None = None
    deadline_ms: int | None = None
    trigger_value: str | None = None


class ObservationSourceSpec(Model):
    kind: Literal["replay", "live"]
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
    """The three distinct facts PRD §5.3 says must never be conflated."""

    key: Literal["command_sent", "command_acknowledged", "physical_motion"]
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
    source_type: Literal["opencv", "replay_cv"]
    source_id: str
    component_id: str
    timestamp_utc: datetime
    elapsed_ms: int
    metric: str
    value: float | None
    unit: str
    measurement_quality: Literal["valid", "marker_not_found", "calibration_invalid", "dropped"]
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


class Highlight(Model):
    element_id: str  # node or edge id
    style: Literal["failed_expectation", "conflict", "observed", "unknown", "suspect"]
    reason: str


class InvestigationView(Model):
    incident: Incident
    test_run: TestRun  # the run that opened the incident
    followup_runs: list[TestRun] = Field(default_factory=list)  # repeat/verify runs, oldest first
    hypotheses: list[Hypothesis]
    actions: list[DiagnosticAction]
    evidence: list[Evidence]  # every evidence item referenced above
    highlights: list[Highlight]


# ---------------------------------------------------------------- API payloads


class ImportRequest(Model):
    repo_path: str
    manifest_path: str | None = None
    name: str | None = None


class StartTestRequest(Model):
    expectation_id: str
    source: ObservationSourceSpec


class ManualResultRequest(Model):
    action_id: str
    result: str
    note: str | None = Field(default=None, max_length=2000)


class ExecuteActionRequest(Model):
    """Optional override of the observation source for repeat/verify runs (e.g. pick a replay)."""

    source: ObservationSourceSpec | None = None


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
