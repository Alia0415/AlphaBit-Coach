"""Typed contracts shared by AlphaOS planning and execution."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.core.task_spec import ResearchDimension


RESEARCH_DISCLAIMER = (
    "本结果仅用于量化投资研究与技术演示，基于指定数据范围、方法和假设生成。"
    "历史数据、模型计算、因子排序和模拟结果均不代表未来表现，"
    "不构成投资建议、证券推荐、收益承诺、交易指令或代客理财服务。"
)


class AgentId(str, Enum):
    """Stable identifiers for experts in the complete expert pool."""

    RESEARCH = "research"
    QUANT = "quant"
    RISK = "risk"
    MACRO = "macro"
    REPORT = "report"


class ValidationStatus(str, Enum):
    """How far the available evidence has actually been validated."""

    RESEARCH_DRAFT = "research_draft"
    COMPUTED_NOT_VALIDATED = "computed_not_validated"
    HISTORICALLY_ANALYZED = "historically_analyzed"
    HISTORICALLY_TESTED = "historically_tested"
    OUT_OF_SAMPLE_TESTED = "out_of_sample_tested"
    STRESS_TESTED = "stress_tested"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNAVAILABLE = "unavailable"


class AgentSelection(BaseModel):
    """An expert selected by the Manager and why it is needed."""

    agent: AgentId
    reason: str = Field(min_length=1)


class DependencyRef(BaseModel):
    """A typed dependency edge in the Manager DAG."""

    step_id: str = Field(min_length=1)
    requirement: Literal["required", "optional"] = "required"


class PlanStep(BaseModel):
    """One node in a dependency-aware execution plan."""

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    agent: AgentId
    objective: str = Field(min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    dependencies: list[DependencyRef] = Field(default_factory=list, max_length=8)
    covers_dimensions: list[ResearchDimension] = Field(default_factory=list)
    expected_output: str = Field(min_length=1)

    @field_validator("depends_on")
    @classmethod
    def dependencies_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("depends_on cannot contain duplicate step IDs")
        return values

    @field_validator("dependencies")
    @classmethod
    def typed_dependencies_must_be_unique(
        cls, values: list[DependencyRef]
    ) -> list[DependencyRef]:
        ids = [dep.step_id for dep in values]
        if len(ids) != len(set(ids)):
            raise ValueError("dependencies cannot contain duplicate step IDs")
        return values

    @field_validator("inputs")
    @classmethod
    def manager_inputs_cannot_select_skills(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        forbidden = {"skill_id", "selected_skills", "skill_plan"}

        def contains_forbidden(value: Any) -> bool:
            if isinstance(value, dict):
                return bool(forbidden & set(value)) or any(
                    contains_forbidden(item) for item in value.values()
                )
            if isinstance(value, list):
                return any(contains_forbidden(item) for item in value)
            return False

        if contains_forbidden(values):
            raise ValueError("Manager plan inputs cannot select internal Skills")
        return values

    def all_dependency_step_ids(self) -> list[str]:
        """Return merged list of step IDs from both legacy and typed deps."""
        typed_ids = [dep.step_id for dep in self.dependencies]
        # Merge legacy depends_on with typed dependencies
        all_ids = list(dict.fromkeys(self.depends_on + typed_ids))
        return all_ids

    def required_dependency_ids(self) -> list[str]:
        """Step IDs of required dependencies (legacy depends_on = required)."""
        required = set(self.depends_on)
        for dep in self.dependencies:
            if dep.requirement == "required":
                required.add(dep.step_id)
            elif dep.step_id in required:
                # typed dep overrides legacy to optional
                pass
        # Actually: typed deps are authoritative when present
        if self.dependencies:
            return [
                dep.step_id
                for dep in self.dependencies
                if dep.requirement == "required"
            ]
        return list(self.depends_on)

    def optional_dependency_ids(self) -> list[str]:
        """Step IDs of optional dependencies."""
        if self.dependencies:
            return [
                dep.step_id
                for dep in self.dependencies
                if dep.requirement == "optional"
            ]
        return []


class ClarificationGroup(BaseModel):
    """One structured clarification question the Manager can ask the user."""

    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1)
    hint: str | None = None
    multi: bool = False
    items: list[str] = Field(default_factory=list)
    default: str | None = None


class ExecutionPlan(BaseModel):
    """Validated task graph generated dynamically by the Manager Agent."""

    goal: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    task_type: str | None = None
    expected_result_type: str | None = None
    task_summary: str | None = None
    complexity: Literal["low", "medium", "high"]
    selected_agents: list[AgentSelection] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list, max_length=8)
    needs_clarification: bool = False
    clarification_question: str | None = None
    clarification_options: list[ClarificationGroup] = Field(default_factory=list)

    @model_validator(mode="after")
    def clarification_is_actionable(self) -> "ExecutionPlan":
        if self.needs_clarification and not (
            self.clarification_question and self.clarification_question.strip()
        ):
            raise ValueError(
                "clarification_question is required when needs_clarification is true"
            )
        return self


class ExpertTask(BaseModel):
    """Uniform task packet sent by the workflow executor to one expert."""

    task_id: str = Field(min_length=1)
    agent: AgentId
    objective: str = Field(min_length=1)
    original_user_request: str = Field(min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    dependency_results: dict[str, "ExpertResult"] = Field(default_factory=dict)

    @property
    def step_id(self) -> str:
        """Backward-compatible in-process name for older handlers."""

        return self.task_id


class ExpertResult(BaseModel):
    """Uniform, validated result returned by every expert."""

    task_id: str = Field(min_length=1)
    agent: AgentId
    status: Literal["completed", "failed", "blocked"]
    summary: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    data_sources: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @model_validator(mode="after")
    def failure_has_an_error(self) -> "ExpertResult":
        if self.status in {"failed", "blocked"} and not self.error:
            raise ValueError("failed and blocked expert results require an error")
        return self

    @property
    def step_id(self) -> str:
        """Backward-compatible in-process name for event ordering."""

        return self.task_id

    @property
    def output(self) -> dict[str, Any]:
        """Expose the complete structured result, never a flattened text blob."""

        return self.model_dump(mode="json")


class DirectAnswer(BaseModel):
    """The first, plain-language answer shown to a non-expert user."""

    headline: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low", "not_applicable"]
    stance: Literal[
        "positive",
        "cautiously_positive",
        "neutral",
        "mixed",
        "cautiously_negative",
        "negative",
        "insufficient_evidence",
        "not_applicable",
    ]


class ResultBlock(BaseModel):
    """One evidence-backed, dynamically selected presentation block."""

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal[
        "task_understanding",
        "validation_summary",
        "finding_cards",
        "metric_cards",
        "comparison",
        "risk_list",
        "assumption_list",
        "factor_list",
        "action_list",
        "limitations",
        "clarification",
        "failure_notice",
        "narrative",
        "report",
        "data_scope",
        "boundary_response",
    ]
    title: str = Field(min_length=1)
    description: str | None = None
    importance: Literal["primary", "secondary", "supporting"]
    source_steps: list[str] = Field(default_factory=list)
    data: dict[str, Any]


class AnalysisStep(BaseModel):
    """A compact execution-path entry for the optional execution summary."""

    step_id: str
    agent: AgentId
    objective: str
    status: Literal["completed", "failed", "blocked", "not_executed"]


class ExecutionSummary(BaseModel):
    """What actually ran, kept separate from the user-facing answer."""

    selected_agents: list[AgentId]
    completed_steps: list[str]
    failed_steps: list[str]
    blocked_steps: list[str]
    analysis_path: list[AnalysisStep]


class TechnicalEvidence(BaseModel):
    """Traceable expert contracts and validation boundaries."""

    validation_statuses: dict[str, str]
    conflicts: list[str]
    missing_evidence: list[str]
    source_results: dict[str, ExpertResult]
    warnings: list[str] = Field(default_factory=list)


class TaskUnderstanding(BaseModel):
    """What AlphaOS understood before any expert was selected."""

    task_type: str
    subject_type: str
    subjects: list[str] = Field(default_factory=list)
    research_goal: str
    time_range: str | None = None
    defaults_used: list[str] = Field(default_factory=list)
    excluded_outputs: list[str] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    """User-readable evidence maturity and claim boundary."""

    status: ValidationStatus
    label: str
    explanation: str
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


class ResultItem(BaseModel):
    """A traceable user-facing fact, judgment, risk, or research action."""

    text: str = Field(min_length=1)
    source_steps: list[str] = Field(default_factory=list)
    evidence_type: Literal[
        "fact",
        "judgment",
        "assumption",
        "risk",
        "limitation",
        "research_action",
        "policy",
    ]
    title: str | None = None


class AggregationResult(BaseModel):
    """Dynamic user-facing result composed only from actual execution evidence."""

    user_goal: str = Field(min_length=1)
    completion_status: Literal[
        "completed",
        "partially_completed",
        "needs_clarification",
        "rejected",
        "failed",
    ]
    output_mode: Literal[
        "direct_answer",
        "data_analysis",
        "idea_generation",
        "risk_review",
        "comparison",
        "formal_report",
        "clarification",
        "failure",
    ]
    result_type: Literal[
        "personal_investment_decision",
        "market_research",
        "company_research",
        "factor_research",
        "historical_analysis",
        "risk_review",
        "comparison",
        "formal_report",
        "boundary_response",
        "clarification",
        "failure",
    ] | None = None
    task_understanding: TaskUnderstanding | None = None
    validation: ValidationSummary | None = None
    direct_answer: DirectAnswer
    key_findings: list[ResultItem] = Field(default_factory=list)
    evidence_summary: list[ResultItem] = Field(default_factory=list)
    assumptions: list[ResultItem] = Field(default_factory=list)
    risks: list[ResultItem] = Field(default_factory=list)
    limitations: list[ResultItem] = Field(default_factory=list)
    data_scope: list[dict[str, Any]] = Field(default_factory=list)
    next_research_steps: list[ResultItem] = Field(default_factory=list)
    content_blocks: list[ResultBlock]
    execution_summary: ExecutionSummary | None = None
    technical_evidence: TechnicalEvidence | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = RESEARCH_DISCLAIMER


class ExecutionEvent(BaseModel):
    """Ordered, frontend-ready orchestration event."""

    type: Literal[
        "policy_checked",
        "task_interpreted",
        "plan_created",
        "clarification_required",
        "step_started",
        "tool_called",
        "skill_plan_created",
        "skill_started",
        "skill_completed",
        "skill_failed",
        "step_completed",
        "step_failed",
        "evidence_validated",
        "synthesis_started",
        "result_policy_checked",
        "task_completed",
    ]
    step_id: str | None = None
    agent: AgentId | None = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskExecutionResponse(BaseModel):
    """Complete response returned by ``POST /api/tasks``."""

    plan: ExecutionPlan | None
    events: list[ExecutionEvent]
    results: dict[str, ExpertResult]
    aggregation: AggregationResult
    final_answer: str
    duration_ms: int = Field(ge=0)
    disclaimer: str = RESEARCH_DISCLAIMER


class CompletenessMetric(BaseModel):
    """Evidence-derived execution completeness — never a quality judgement."""

    planned_steps: int = Field(ge=0)
    completed_steps: int = Field(ge=0)
    failed_steps: int = Field(ge=0)
    blocked_steps: int = Field(ge=0)
    completion_ratio: float = Field(ge=0.0, le=1.0)
    evidence_coverage_ratio: float = Field(ge=0.0, le=1.0)
    validation_summary: dict[str, int] = Field(default_factory=dict)
    note: str = "执行完成度，非质量评分"


class ExpertInfo(BaseModel):
    """Read-only expert descriptor for the roster surface."""

    id: str
    name: str
    description: str
    enabled: bool
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class SkillInfo(BaseModel):
    """Read-only skill descriptor exposed for transparency."""

    id: str
    name: str
    description: str
    mode: str
    enabled: bool
    owner_agents: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class OverviewStats(BaseModel):
    """Real counts derived from the registry and persisted tasks/reports."""

    enabled_experts: int = Field(ge=0)
    enabled_skills: int = Field(ge=0)
    total_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    report_count: int = Field(ge=0)
    average_completion: float = Field(ge=0.0, le=1.0)


class TaskSummary(BaseModel):
    """Compact task row for list views."""

    id: str
    prompt: str
    status: str
    created_at: str
    duration_ms: int | None = None


class TaskDetail(BaseModel):
    """Full persisted task including ordered events and any aggregation."""

    id: str
    prompt: str
    status: str
    created_at: str
    plan: ExecutionPlan | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    aggregation: AggregationResult | None = None
    final_answer: str | None = None
    duration_ms: int | None = None


class ReportSummary(BaseModel):
    """Compact report row for list views."""

    id: str
    task_id: str
    title: str
    created_at: str
    completeness: CompletenessMetric | None = None


class FollowupAnswer(BaseModel):
    """A persisted, evidence-bounded follow-up exchange on a report."""

    id: str
    report_id: str
    role: str
    text: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class ReportDetail(BaseModel):
    """Full persisted report with completeness, aggregation, and follow-ups."""

    id: str
    task_id: str
    title: str
    created_at: str
    completeness: CompletenessMetric | None = None
    aggregation: AggregationResult | None = None
    followups: list[FollowupAnswer] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Multidimensional evidence contracts (spec §9)
# ---------------------------------------------------------------------------

EvidenceStatus = Literal[
    "sufficient",
    "partial",
    "insufficient",
    "unavailable",
]


class DataProvenance(BaseModel):
    """Traceable origin of a single piece of financial evidence."""

    endpoint: str
    symbol: str | None = None
    industry: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    fields: list[str] = Field(default_factory=list)
    observation_count: int | None = None
    method: str | None = None


class EvidenceRecord(BaseModel):
    """A single traceable evidence item produced by an expert (spec §9.2)."""

    evidence_id: str = Field(min_length=1)
    dimension: ResearchDimension
    kind: Literal["fact", "metric", "comparison", "judgment", "risk", "limitation"]
    statement: str = Field(min_length=1)
    value: Any | None = None
    unit: str | None = None
    as_of: str | None = None
    source: DataProvenance
    method: str | None = None
    validation_status: ValidationStatus = ValidationStatus.RESEARCH_DRAFT


class EvidenceCoverage(BaseModel):
    """Coverage summary for one research dimension (spec §9.1)."""

    dimension: ResearchDimension
    status: EvidenceStatus
    expected_items: int = Field(ge=0)
    available_items: int = Field(ge=0)
    missing_items: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Structured synthesis contracts (spec §13)
# ---------------------------------------------------------------------------


class SynthesisClaim(BaseModel):
    """One claim in the aggregated synthesis referencing evidence IDs."""

    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    claim_type: Literal["finding", "risk", "limitation", "uncertainty"]


class DimensionSynthesis(BaseModel):
    """Synthesis for one research dimension."""

    dimension: ResearchDimension
    conclusion: str = Field(min_length=1)
    evidence_status: EvidenceStatus
    claims: list[SynthesisClaim] = Field(default_factory=list)


class SynthesisDraft(BaseModel):
    """Structured model output for evidence-based aggregation (spec §13.2)."""

    headline: str = Field(min_length=1)
    overall_stance: Literal[
        "positive",
        "cautiously_positive",
        "neutral",
        "mixed",
        "cautiously_negative",
        "negative",
        "insufficient_evidence",
    ]
    confidence: Literal["high", "medium", "low"]
    thesis: str = Field(min_length=1)
    dimensions: list[DimensionSynthesis] = Field(default_factory=list)
    conflicts: list[SynthesisClaim] = Field(default_factory=list)
    uncertainties: list[SynthesisClaim] = Field(default_factory=list)
    next_research_steps: list[str] = Field(default_factory=list)
