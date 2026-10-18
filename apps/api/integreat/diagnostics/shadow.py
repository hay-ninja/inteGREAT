"""Digital shadow: reduced-order prediction from declared structure + expectation.

The sim rig's fault model (`SimConditions`) is the reduced-order model — used predictively
here rather than as a fake observation source. Everything emitted is `epistemic=inferred`:
model-based inference, never a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Expectation, GraphEdge, GraphNode
from ..observations.sim import SimConditions
from .rules import config_vs_wiring


@dataclass
class ShadowSignature:
    """What the shadow predicts the run's three observable facts will look like."""

    moves: bool        # the component physically responds
    acks: bool         # firmware emits the acknowledgement line
    measurable: bool   # the camera channel produces valid measurements


def nominal_conditions(exp: Expectation, nodes: list[GraphNode], edges: list[GraphEdge]) -> SimConditions:
    """Shadow parameters derived from the graph + expectation — the system *as declared*,
    including whatever GPIO the source actually configures (mismatches included)."""
    cfg, _wire, wired_pin = config_vs_wiring(exp.component_id, nodes, edges)
    gpio = {n.id: n.attributes.get("gpio") for n in nodes}
    configured = gpio.get(cfg[0].target_id) if cfg else None
    wired = gpio.get(wired_pin) if wired_pin else None
    return SimConditions(configured_gpio=configured, wired_gpio=wired)


def predict_signature(cond: SimConditions) -> ShadowSignature:
    """Deterministic forward prediction — mirrors SimSerial/SimRig behaviour exactly:
    ACK depends only on the firmware path (not on whether the drive succeeds); motion needs
    configured==wired pin AND both leads; camera output needs a visible marker."""
    driven = (cond.configured_gpio is not None and cond.configured_gpio == cond.wired_gpio
              and cond.signal_connected and cond.power_connected)
    return ShadowSignature(moves=driven, acks=cond.firmware_acks, measurable=cond.marker_visible)


def describe(cond: SimConditions) -> str:
    parts = [f"configured GPIO{cond.configured_gpio}" if cond.configured_gpio is not None else "no pin configured",
             f"wired GPIO{cond.wired_gpio}" if cond.wired_gpio is not None else "no declared signal wiring"]
    parts += ["signal connected" if cond.signal_connected else "signal disconnected",
              "power connected" if cond.power_connected else "power disconnected",
              "marker visible" if cond.marker_visible else "marker occluded",
              "firmware acks" if cond.firmware_acks else "firmware does not ack"]
    return "; ".join(parts)
