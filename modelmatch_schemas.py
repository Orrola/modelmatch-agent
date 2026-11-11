"""Structured agent contracts. Agent outputs never carry model scores."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StatedNumber(StrictOutput):
    value: float
    source_quote: str


class ParsedConstraint(StrictOutput):
    metric: Literal["input_price", "output_price", "monthly_cost_usd", "ttft", "output_speed",
                    "context_window", "max_input_tokens", "max_output_tokens", "deployment", "data_residency", "other"]
    target: float | str | None = None
    hard: bool = False
    statistic: str | None = None
    source_quote: str
    hard_source_quote: str | None = None


class ParsedWorkload(StrictOutput):
    monthly_requests: StatedNumber | None = None
    avg_input_tokens: StatedNumber | None = None
    avg_output_tokens: StatedNumber | None = None


class ParsedPlan(StrictOutput):
    industry: str | None = None
    task_description: str
    task_quote: str
    task_type: Literal["general_assistant", "tool_agent", "reasoning_analysis", "coding_assistant", "specialized_domain", "mixed_or_unknown"]
    user_alpha: StatedNumber | None = None
    constraints: list[ParsedConstraint] = Field(default_factory=list)
    workload: ParsedWorkload = Field(default_factory=ParsedWorkload)
    clarification_questions: list[str] = Field(default_factory=list, description="Suggestions only. Python validates which missing inputs are essential.")


class Followup(StrictOutput):
    role: Literal["A", "B", "C"]
    task: str
    reason: str
    model_ids: list[str] = Field(default_factory=list)


class Review(StrictOutput):
    summary: str
    followups: list[Followup] = Field(default_factory=list)
    stopping_reason: str


class DispatchComplete(StrictOutput):
    """Acknowledgment only; it cannot choose a workflow transition."""
    completed: Literal[True]


class FinalReview(StrictOutput):
    """The follow-up cap is enforced in the schema as well as Python."""
    summary: str
    stopping_reason: str


LEAD_OUTPUT_TYPES = {
    "parse": ParsedPlan,
    "dispatch": DispatchComplete,
    "review": Review,
    "followup": DispatchComplete,
    "review_final": FinalReview,
}


class ResearcherOutput(StrictOutput):
    evidence_ids: list[str] = Field(default_factory=list)
    observations: list[Literal["evidence_available", "missing_evidence", "partial_relevance", "unsupported_domain", "unknown_specifications"]] = Field(default_factory=list)


ValidationStep = Literal["task_pilot", "tool_use_pilot", "verify_context", "verify_deployment", "measure_workload", "check_index_versions"]


class WriterOutput(StrictOutput):
    """Writer selects grounded report content; code owns all numbers and order."""
    candidate_ids: list[str]
    evidence_ids: list[str]
    validation_steps: list[ValidationStep]


@dataclass
class AgentCallContext:
    coordinator: Any
    role: str
    context_id: str
    stage: str = "research"
    round_number: int = 0
    model_ids: list[str] = field(default_factory=list)
    tool_calls: int = 0
    retrieved: bool = False
    evidence_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class OrchestrationLimits:
    max_researcher_runs: int = 6
    max_followup_rounds: int = 1
    max_data_calls_per_researcher: int = 2
    max_agent_turns: int = 6
    timeout_seconds: float = 300
    evidence_preview_size: int = 12
    shortlist_size: int = 20

    def __post_init__(self):
        if self.max_researcher_runs < 3 or self.max_researcher_runs > 6:
            raise ValueError("Phase 3A permits 3 to 6 researcher runs.")
        if self.max_followup_rounds not in (0, 1):
            raise ValueError("Phase 3A permits at most one follow-up round.")
        if min(self.max_data_calls_per_researcher, self.max_agent_turns, self.evidence_preview_size) < 1 or self.timeout_seconds <= 0 or self.shortlist_size < 0:
            raise ValueError("Execution limits must be positive; shortlist size may be zero.")
