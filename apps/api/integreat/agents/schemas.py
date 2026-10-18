"""Model-facing output schemas. Deliberately flat (strings, lists, simple objects) so Gemini's
structured-output schema conversion handles them; validated again on our side before use."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FindingOut(BaseModel):
    statement: str = Field(max_length=600)
    supporting_evidence_ids: list[str] = Field(max_length=12)
    contradicting_evidence_ids: list[str] = Field(default_factory=list, max_length=12)
    epistemic_status: Literal["inferred", "hypothesis"]


class ProposedHypothesisOut(BaseModel):
    title: str = Field(max_length=120)
    explanation: str = Field(max_length=600)
    supporting_evidence_ids: list[str] = Field(max_length=12)


class AgentReportOut(BaseModel):
    findings: list[FindingOut] = Field(max_length=8)
    unknowns: list[str] = Field(default_factory=list, max_length=8)
    proposed_action_ids: list[str] = Field(default_factory=list, max_length=4)
    proposed_hypotheses: list[ProposedHypothesisOut] = Field(default_factory=list, max_length=3)


class TriageOut(BaseModel):
    agents: list[Literal["code", "hardware", "runtime_vision"]] = Field(min_length=1, max_length=3)
    rationale: str = Field(max_length=400)


class SynthesisOut(BaseModel):
    summary: str = Field(max_length=900)
    recommended_action_id: str
    contradictions: list[str] = Field(default_factory=list, max_length=5)
