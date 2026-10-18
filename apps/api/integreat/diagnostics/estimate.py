"""Fault-parameter estimation: which shadow fault-knob settings reproduce the observed
signature — diagnosis as parameter estimation, deterministic, no LLM.

θ is a small discrete space built from `SimConditions`: the declared configuration plus
single-fault perturbations and counterfactual interventions (do()-style: force one knob to
a value and re-predict). A θ is *consistent* when every observed fact matches its predicted
signature; observed "unknown" facts constrain nothing.

Verdicts become `shadow_residual` evidence (epistemic=inferred): "consistent within our
fault model" — never presented as a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import (
    Epistemic,
    Evidence,
    EvidenceKind,
    Expectation,
    ExpectationResult,
    FaultCode,
    GraphEdge,
    GraphNode,
    Hypothesis,
    Provenance,
)
from ..observations.sim import SimConditions
from .shadow import ShadowSignature, describe, nominal_conditions, predict_signature


@dataclass
class Theta:
    """One candidate state of the world. `label` is human-facing; `patch` mutates the
    declared conditions (do(knob=value) interventions for counterfactual checks)."""

    id: str
    label: str
    patch: dict = field(default_factory=dict)


@dataclass
class ThetaVerdict:
    theta: str
    label: str
    consistent: bool
    mismatches: list[str] = field(default_factory=list)
    predicted: str = ""


def theta_space(declared: SimConditions, binary: bool = False) -> list[Theta]:
    """The declared configuration plus single-knob interventions."""
    out = [
        Theta("declared", "system as declared (config + wiring + leads as imported)"),
        Theta("signal_disconnected", "signal lead disconnected", {"signal_connected": False}),
        Theta("power_disconnected", "power/ground disconnected", {"power_connected": False}),
        Theta("marker_occluded", "camera marker occluded", {"marker_visible": False}),
        Theta("no_firmware_ack", "firmware does not acknowledge", {"firmware_acks": False}),
        Theta("pins_matched", "counterfactual: configured pin equals wired pin",
              {"configured_gpio": declared.wired_gpio}),
        Theta("healthy", "counterfactual: fully healthy (pins match, leads connected, marker visible)",
              {"configured_gpio": declared.wired_gpio, "signal_connected": True,
               "power_connected": True, "marker_visible": True, "firmware_acks": True}),
    ]
    if binary:
        # do(code drives the active level) — the intervention that fixes an inverted drive
        out.insert(-1, Theta("polarity_matched",
                             "counterfactual: code drives the wiring's active level for 'on'",
                             {"code_on_high": not declared.active_low}))
    return out


def _apply(cond: SimConditions, patch: dict) -> SimConditions:
    out = SimConditions(**{**cond.__dict__, **patch})
    return out


def observed_signature(exp: Expectation, result: ExpectationResult) -> dict[str, bool | None]:
    """The run's observable facts as a signature; None = unknown/unconstraining."""
    facts = {f.key: f.value for f in result.facts}
    tri = lambda v: None if v in (None, "unknown") else v == "yes"
    return {
        "moves": tri(facts.get("physical_motion")),
        "acks": tri(facts.get("command_acknowledged")),
        "measurable": result.valid_samples >= exp.min_valid_samples,
        "final_ok": tri(facts.get("physical_state")),
    }


def compare(pred: ShadowSignature, obs: dict[str, bool | None]) -> list[str]:
    mism = []
    if obs["moves"] is not None and obs["moves"] != pred.moves:
        mism.append(f"predicted {'a response' if pred.moves else 'no response'}, "
                    f"observed {'a response' if obs['moves'] else 'none'}")
    if obs["acks"] is not None and obs["acks"] != pred.acks:
        mism.append(f"predicted {'ack' if pred.acks else 'no ack'}, "
                    f"observed {'ack' if obs['acks'] else 'none'}")
    if obs["measurable"] != pred.measurable:
        mism.append(f"predicted {'valid measurements' if pred.measurable else 'no valid measurements'}, "
                    f"observed {'valid measurements' if obs['measurable'] else 'insufficient'}")
    if obs.get("final_ok") is not None and pred.final_ok is not None and obs["final_ok"] != pred.final_ok:
        mism.append(f"predicted final state {'reached' if pred.final_ok else 'not reached'}, "
                    f"observed {'reached' if obs['final_ok'] else 'not reached'}")
    return mism


def assess(exp: Expectation, nodes: list[GraphNode], edges: list[GraphEdge],
           result: ExpectationResult, run_id: str) -> tuple[list[ThetaVerdict], Evidence]:
    """Run the sweep. Returns per-θ verdicts and one persisted shadow_residual evidence record."""
    binary = exp.unit == "state"
    declared = nominal_conditions(exp, nodes, edges)
    obs = observed_signature(exp, result)
    verdicts: list[ThetaVerdict] = []
    for t in theta_space(declared, binary):
        pred = predict_signature(_apply(declared, t.patch), binary)
        mism = compare(pred, obs)
        verdicts.append(ThetaVerdict(
            theta=t.id, label=t.label, consistent=not mism, mismatches=mism,
            predicted=f"moves={pred.moves} acks={pred.acks} measurable={pred.measurable}"
                      + (f" final_ok={pred.final_ok}" if binary else "")))
    consistent = [v.label for v in verdicts if v.consistent]
    refuted = [f"{v.label} ({'; '.join(v.mismatches)})" for v in verdicts if not v.consistent]
    summary = (f"Shadow sweep on declared system ({describe(declared, binary)}): "
               f"consistent scenarios — {', '.join(consistent) or 'none'}."
               + (f" Ruled inconsistent — {' | '.join(refuted)}." if refuted else ""))
    ev = Evidence(
        id=f"evidence:shadow:{run_id}", project_id=exp.project_id,
        kind=EvidenceKind.shadow_residual, epistemic=Epistemic.inferred,
        summary=summary[:600],
        provenance=Provenance(source_id="shadow_sim", captured_at_utc=None), test_run_id=run_id,
        payload={"conditions": declared.__dict__, "observed_signature": obs,
                 "final_residual": (result.final_valid_value - exp.target
                                    if result.final_valid_value is not None else None),
                 "verdicts": [v.__dict__ for v in verdicts]})
    return verdicts, ev


# Hypothesis → the θ whose consistency supports it. Signal/power hyps are keyed by id suffix.
def _theta_for(h: Hypothesis) -> str | None:
    if h.id.endswith("_signal"):
        return "signal_disconnected"
    if h.id.endswith("_power"):
        return "power_disconnected"
    return {
        FaultCode.GPIO_CONFIG_MISMATCH: "declared",
        FaultCode.INVERTED_LOGIC: "declared",  # the declared system already carries the polarity mismatch
        FaultCode.MISSING_SERIAL_ACK: "no_firmware_ack",
        FaultCode.CAMERA_MEASUREMENT_UNAVAILABLE: "marker_occluded",
    }.get(h.fault_code)


# Hypothesis → the counterfactual θ where its fault knob is forced back to nominal
# (do(knob=ok)). For lead faults the declared system already has the knob nominal; for a
# GPIO mismatch, nominal means "configured pin equals wired pin"; for inverted logic it
# means "code drives the wiring's active level".
def _counterfactual_theta(h: Hypothesis) -> str | None:
    if h.fault_code == FaultCode.GPIO_CONFIG_MISMATCH:
        return "pins_matched"
    if h.fault_code == FaultCode.INVERTED_LOGIC:
        return "polarity_matched"
    return "declared"


def attach_verdicts(hyps: list[Hypothesis], verdicts: list[ThetaVerdict], evidence_id: str,
                    observed_desc: str) -> list[str]:
    """Cite the shadow verdict on each mapped hypothesis and append a one-line model check +
    counterfactual to the explanation. Statuses/ranks are untouched — evidence only."""
    by_id = {v.theta: v for v in verdicts}
    notes: list[str] = []
    for h in hyps:
        tid = _theta_for(h)
        v = by_id.get(tid) if tid else None
        if v is None:
            continue
        if v.consistent:
            if evidence_id not in h.supporting_evidence_ids:
                h.supporting_evidence_ids.append(evidence_id)
            h.explanation += (" Model check (inferred): the shadow reproduces the observed signature "
                              "with this fault — consistent within our fault model, not measured.")
        else:
            if evidence_id not in h.contradicting_evidence_ids:
                h.contradicting_evidence_ids.append(evidence_id)
            h.explanation += (" Model check (inferred): the shadow predicts a different signature under "
                              f"this fault ({'; '.join(v.mismatches)}).")
            notes.append(f"{h.title}: shadow predicts {v.predicted}")
        cf = counterfactual_note(verdicts, _counterfactual_theta(h), observed_desc)
        if cf:
            h.explanation += f" Counterfactual: {cf}"
    return notes


def counterfactual_note(verdicts: list[ThetaVerdict], theta: str, observed_desc: str) -> str | None:
    """Human-readable counterfactual: 'had <knob>, the model predicts <sig> — but we observed …'."""
    v = next((v for v in verdicts if v.theta == theta), None)
    if v is None:
        return None
    return (f"Under '{v.label}' the shadow predicts {v.predicted}; observed: {observed_desc} — "
            + ("so this intervention would still reproduce the observation."
               if v.consistent else "so this intervention alone does not explain the observation."))
