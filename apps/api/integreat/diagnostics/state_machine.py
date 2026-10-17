"""Test and incident state machines (PRD FR-05). Invalid transitions raise."""

from __future__ import annotations

from ..models import IncidentState as I
from ..models import TestRunState as T

TEST_TRANSITIONS = {
    T.configured: {T.running, T.cancelled},
    T.running: {T.completed, T.failed, T.cancelled},
    T.completed: set(),
    T.failed: set(),
    T.cancelled: set(),
}

INCIDENT_TRANSITIONS = {
    I.open: {I.investigating, I.awaiting_engineer, I.inconclusive},
    I.investigating: {I.awaiting_engineer, I.inconclusive},
    I.awaiting_engineer: {I.investigating, I.verifying, I.inconclusive},
    I.verifying: {I.resolved, I.awaiting_engineer, I.inconclusive},
    I.resolved: set(),
    I.inconclusive: set(),
}


class InvalidTransition(ValueError):
    pass


def check_test(cur: T, new: T) -> T:
    if new not in TEST_TRANSITIONS[cur]:
        raise InvalidTransition(f"test run cannot go {cur.value} → {new.value}")
    return new


def check_incident(cur: I, new: I) -> I:
    if new not in INCIDENT_TRANSITIONS[cur]:
        raise InvalidTransition(f"incident cannot go {cur.value} → {new.value}")
    return new
