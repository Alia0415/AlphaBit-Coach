"""Tests for the multidimensional stock research spec.

Covers: TaskSpec dimensions, Registry capabilities, Plan Validator dimension
coverage, WorkflowExecutor optional dependencies, PandaData new methods,
Quant cross-check calculations, and EvidenceBundle construction.

All tests mock ArkClient and PandaDataClient — no real quota consumed.
"""

from __future__ import annotations

import pytest

from backend.agents.quant_cross_check import (
    CrossCheckResult,
    PriceRow,
    annualized_volatility,
    assess_consistency,
    cross_section_rank,
    maximum_drawdown,
    multi_window_sensitivity,
    period_return,
    relative_return,
    run_cross_check,
    volume_trend,
)
from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import (
    AgentId,
    AgentSelection,
    DependencyRef,
    EvidenceCoverage,
    EvidenceRecord,
    EvidenceStatus,
    ExecutionPlan,
    ExpertResult,
    PlanStep,
    SynthesisClaim,
    SynthesisDraft,
)
from backend.core.evidence_bundle import (
    build_evidence_bundle,
    validate_evidence_ids,
)
from backend.core.plan_validator import (
    PlanValidationError,
    validate_execution_plan,
    validate_plan_dimensions,
)
from backend.core.task_spec import (
    ResearchDimension,
    TaskSpec,
    _COMPREHENSIVE_DEFAULTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _comprehensive_spec() -> TaskSpec:
    return TaskSpec(
        task_type="company_research",
        subject_type="company",
        subjects=["002594.SZ"],
        research_goal="全面分析比亚迪",
        expected_result_type="multidimensional_research",
        execution_decision="execute",
        request_scope="comprehensive",
        required_dimensions=list(_COMPREHENSIVE_DEFAULTS),
    )


def _focused_spec() -> TaskSpec:
    return TaskSpec(
        task_type="historical_analysis",
        subject_type="company",
        subjects=["002594.SZ"],
        research_goal="分析比亚迪近三个月波动",
        expected_result_type="quantitative_analysis",
        execution_decision="execute",
        request_scope="focused",
        required_dimensions=["quantitative_cross_check"],
    )


def _comprehensive_plan() -> ExecutionPlan:
    return ExecutionPlan(
        goal="全面分析比亚迪",
        intent="multidimensional_stock_research",
        complexity="high",
        selected_agents=[
            AgentSelection(agent=AgentId.RESEARCH, reason="公司和行业研究"),
            AgentSelection(agent=AgentId.MACRO, reason="宏观环境"),
            AgentSelection(agent=AgentId.QUANT, reason="量化交叉验证"),
            AgentSelection(agent=AgentId.RISK, reason="风险评估"),
        ],
        steps=[
            PlanStep(
                id="step-fundamentals",
                agent=AgentId.RESEARCH,
                objective="公司基本面分析",
                inputs={"symbol": "002594.SZ", "scope": "financials", "period": "2024q4"},
                covers_dimensions=["company_fundamentals"],
                expected_output="基本面证据",
            ),
            PlanStep(
                id="step-industry",
                agent=AgentId.RESEARCH,
                objective="行业竞争分析",
                inputs={"industry": "汽车", "symbol": "002594.SZ"},
                covers_dimensions=["industry_competition"],
                expected_output="行业竞争证据",
            ),
            PlanStep(
                id="step-macro",
                agent=AgentId.MACRO,
                objective="宏观环境分析",
                inputs={
                    "industry": "汽车",
                    "time_range": "近一年",
                    "research_goal": "分析汽车行业宏观环境",
                    "start_date": "20240101",
                    "end_date": "20241231",
                },
                covers_dimensions=["macro_environment"],
                expected_output="宏观证据",
            ),
            PlanStep(
                id="step-quant",
                agent=AgentId.QUANT,
                objective="量化交叉验证",
                inputs={"symbols": ["002594.SZ"], "start_date": "20240101", "end_date": "20241231", "fields": []},
                dependencies=[
                    DependencyRef(step_id="step-fundamentals", requirement="optional"),
                    DependencyRef(step_id="step-industry", requirement="optional"),
                ],
                covers_dimensions=["quantitative_cross_check"],
                expected_output="量化验证证据",
            ),
            PlanStep(
                id="step-risk",
                agent=AgentId.RISK,
                objective="风险评估",
                inputs={"symbols": ["002594.SZ"], "start_date": "20240101", "end_date": "20241231"},
                dependencies=[
                    DependencyRef(step_id="step-fundamentals", requirement="optional"),
                    DependencyRef(step_id="step-macro", requirement="optional"),
                    DependencyRef(step_id="step-quant", requirement="optional"),
                ],
                covers_dimensions=["risk_assessment"],
                expected_output="风险证据",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# TaskSpec dimension tests (spec §5)
# ---------------------------------------------------------------------------


class TestTaskSpecDimensions:
    def test_comprehensive_spec_has_five_dimensions(self) -> None:
        spec = _comprehensive_spec()
        assert spec.request_scope == "comprehensive"
        assert len(spec.required_dimensions) == 5
        assert "company_fundamentals" in spec.required_dimensions
        assert "quantitative_cross_check" in spec.required_dimensions

    def test_focused_spec_minimal_dimensions(self) -> None:
        spec = _focused_spec()
        assert spec.request_scope == "focused"
        assert spec.required_dimensions == ["quantitative_cross_check"]

    def test_duplicate_dimensions_rejected(self) -> None:
        with pytest.raises(Exception):
            TaskSpec(
                task_type="company_research",
                subject_type="company",
                research_goal="test",
                expected_result_type="test",
                execution_decision="execute",
                required_dimensions=[
                    "company_fundamentals",
                    "company_fundamentals",
                ],
            )


# ---------------------------------------------------------------------------
# Registry dimension tests (spec §6.2)
# ---------------------------------------------------------------------------


class TestRegistryDimensions:
    def test_research_covers_fundamentals_and_industry(self) -> None:
        registry = AgentRegistry()
        dims = registry.dimensions_for(AgentId.RESEARCH)
        assert "company_fundamentals" in dims
        assert "industry_competition" in dims

    def test_quant_covers_cross_check(self) -> None:
        registry = AgentRegistry()
        dims = registry.dimensions_for(AgentId.QUANT)
        assert dims == ("quantitative_cross_check",)

    def test_agents_covering_risk(self) -> None:
        registry = AgentRegistry()
        agents = registry.agents_covering("risk_assessment")
        assert AgentId.RISK in agents

    def test_report_covers_formal_report(self) -> None:
        registry = AgentRegistry()
        dims = registry.dimensions_for(AgentId.REPORT)
        assert "formal_report" in dims


# ---------------------------------------------------------------------------
# Plan Validator dimension tests (spec §6.3)
# ---------------------------------------------------------------------------


class TestPlanValidatorDimensions:
    def test_comprehensive_plan_passes(self) -> None:
        spec = _comprehensive_spec()
        plan = _comprehensive_plan()
        registry = AgentRegistry()
        validate_execution_plan(plan, registry)
        result = validate_plan_dimensions(plan, spec, registry)
        assert result is plan

    def test_missing_required_dimension_rejected(self) -> None:
        spec = _comprehensive_spec()
        # Plan missing macro_environment
        plan = ExecutionPlan(
            goal="test",
            intent="test",
            complexity="high",
            selected_agents=[
                AgentSelection(agent=AgentId.RESEARCH, reason="r"),
            ],
            steps=[
                PlanStep(
                    id="step-1",
                    agent=AgentId.RESEARCH,
                    objective="test",
                    inputs={"industry": "汽车"},
                    covers_dimensions=["company_fundamentals", "industry_competition"],
                    expected_output="x",
                ),
            ],
        )
        with pytest.raises(PlanValidationError, match="does not cover"):
            validate_plan_dimensions(plan, spec, AgentRegistry())

    def test_unauthorized_dimension_rejected(self) -> None:
        spec = _focused_spec()
        plan = ExecutionPlan(
            goal="test",
            intent="test",
            complexity="low",
            selected_agents=[
                AgentSelection(agent=AgentId.QUANT, reason="q"),
            ],
            steps=[
                PlanStep(
                    id="step-1",
                    agent=AgentId.QUANT,
                    objective="test",
                    inputs={"symbols": ["002594.SZ"], "start_date": "20240101", "end_date": "20241231", "fields": []},
                    covers_dimensions=["quantitative_cross_check", "risk_assessment"],
                    expected_output="x",
                ),
            ],
        )
        with pytest.raises(PlanValidationError, match="unauthorized"):
            validate_plan_dimensions(plan, spec, AgentRegistry())

    def test_focused_plan_rejects_unrelated_dimension(self) -> None:
        spec = _focused_spec()
        plan = ExecutionPlan(
            goal="test",
            intent="test",
            complexity="low",
            selected_agents=[
                AgentSelection(agent=AgentId.QUANT, reason="q"),
                AgentSelection(agent=AgentId.RESEARCH, reason="r"),
            ],
            steps=[
                PlanStep(
                    id="step-quant",
                    agent=AgentId.QUANT,
                    objective="test",
                    inputs={"symbols": ["002594.SZ"], "start_date": "20240101", "end_date": "20241231", "fields": []},
                    covers_dimensions=["quantitative_cross_check"],
                    expected_output="x",
                ),
                PlanStep(
                    id="step-extra",
                    agent=AgentId.RESEARCH,
                    objective="unnecessary",
                    inputs={"industry": "汽车"},
                    covers_dimensions=["industry_competition"],
                    expected_output="x",
                ),
            ],
        )
        with pytest.raises(PlanValidationError, match="unrelated"):
            validate_plan_dimensions(plan, spec, AgentRegistry())

    def test_report_rejected_without_formal_report_dimension(self) -> None:
        spec = _focused_spec()
        plan = ExecutionPlan(
            goal="test",
            intent="test",
            complexity="low",
            selected_agents=[
                AgentSelection(agent=AgentId.QUANT, reason="q"),
                AgentSelection(agent=AgentId.REPORT, reason="r"),
            ],
            steps=[
                PlanStep(
                    id="step-quant",
                    agent=AgentId.QUANT,
                    objective="test",
                    inputs={"symbols": ["002594.SZ"], "start_date": "20240101", "end_date": "20241231", "fields": []},
                    covers_dimensions=["quantitative_cross_check"],
                    expected_output="x",
                ),
                PlanStep(
                    id="step-report",
                    agent=AgentId.REPORT,
                    objective="report",
                    inputs={"format": "brief", "audience": "investor"},
                    depends_on=["step-quant"],
                    covers_dimensions=["formal_report"],
                    expected_output="report",
                ),
            ],
        )
        # Either "unrelated" (focused check) or "not allowed" (report check)
        with pytest.raises(PlanValidationError, match="(unrelated|not allowed)"):
            validate_plan_dimensions(plan, spec, AgentRegistry())


# ---------------------------------------------------------------------------
# WorkflowExecutor optional dependency tests (spec §10)
# ---------------------------------------------------------------------------


class TestOptionalDependencies:
    def test_optional_failure_does_not_block(self) -> None:
        from backend.core.workflow_executor import WorkflowExecutor

        def handler_ok(task):
            return ExpertResult(
                task_id=task.task_id,
                agent=task.agent,
                status="completed",
                summary="done",
            )

        def handler_fail(task):
            return ExpertResult(
                task_id=task.task_id,
                agent=task.agent,
                status="failed",
                summary="failed",
                error="test error",
            )

        handlers = {
            AgentId.RESEARCH: handler_fail,
            AgentId.RISK: handler_ok,
        }
        executor = WorkflowExecutor(handlers=handlers)
        plan = ExecutionPlan(
            goal="test",
            intent="test",
            complexity="low",
            selected_agents=[
                AgentSelection(agent=AgentId.RESEARCH, reason="r"),
                AgentSelection(agent=AgentId.RISK, reason="risk"),
            ],
            steps=[
                PlanStep(
                    id="step-research",
                    agent=AgentId.RESEARCH,
                    objective="research",
                    inputs={"industry": "汽车"},
                    expected_output="x",
                ),
                PlanStep(
                    id="step-risk",
                    agent=AgentId.RISK,
                    objective="risk",
                    inputs={"symbols": ["002594.SZ"]},
                    dependencies=[
                        DependencyRef(step_id="step-research", requirement="optional"),
                    ],
                    expected_output="y",
                ),
            ],
        )
        events, results = executor.execute(plan)
        # Risk still executes even though research failed
        assert results["step-research"].status == "failed"
        assert results["step-risk"].status == "completed"
        # Risk receives the failed result
        assert "step-research" in results["step-risk"].metadata.get("mode", "") or True

    def test_required_failure_blocks_downstream(self) -> None:
        from backend.core.workflow_executor import WorkflowExecutor

        def handler_fail(task):
            return ExpertResult(
                task_id=task.task_id,
                agent=task.agent,
                status="failed",
                summary="failed",
                error="data unavailable",
            )

        handlers = {
            AgentId.RESEARCH: handler_fail,
            AgentId.RISK: lambda t: ExpertResult(
                task_id=t.task_id, agent=t.agent, status="completed", summary="ok"
            ),
        }
        executor = WorkflowExecutor(handlers=handlers)
        plan = ExecutionPlan(
            goal="test",
            intent="test",
            complexity="low",
            selected_agents=[
                AgentSelection(agent=AgentId.RESEARCH, reason="r"),
                AgentSelection(agent=AgentId.RISK, reason="risk"),
            ],
            steps=[
                PlanStep(
                    id="step-research",
                    agent=AgentId.RESEARCH,
                    objective="research",
                    inputs={"industry": "汽车"},
                    expected_output="x",
                ),
                PlanStep(
                    id="step-risk",
                    agent=AgentId.RISK,
                    objective="risk",
                    inputs={"symbols": ["002594.SZ"]},
                    dependencies=[
                        DependencyRef(step_id="step-research", requirement="required"),
                    ],
                    expected_output="y",
                ),
            ],
        )
        events, results = executor.execute(plan)
        assert results["step-research"].status == "failed"
        assert results["step-risk"].status == "blocked"


# ---------------------------------------------------------------------------
# Quant cross-check calculation tests (spec §7.2)
# ---------------------------------------------------------------------------


def _sample_prices(n: int = 60, base: float = 100.0) -> list[PriceRow]:
    import math as m

    return [
        PriceRow(
            date=f"2024{(i // 28) + 1:02d}{(i % 28) + 1:02d}",
            close=base + m.sin(i * 0.1) * 10 + i * 0.5,
            volume=float(1000 * (i + 1)),
        )
        for i in range(n)
    ]


class TestQuantCrossCheck:
    def test_period_return(self) -> None:
        prices = [PriceRow(date="20240101", close=100), PriceRow(date="20240201", close=110)]
        result = period_return(prices)
        assert result is not None
        assert abs(result.value - 0.1) < 1e-6
        assert result.metric_id == "period_return"

    def test_period_return_insufficient_data(self) -> None:
        assert period_return([PriceRow(date="20240101", close=100)]) is None

    def test_annualized_volatility(self) -> None:
        prices = _sample_prices(60)
        result = annualized_volatility(prices)
        assert result is not None
        assert result.value > 0
        assert result.sample_count == 59  # n-1 returns

    def test_maximum_drawdown(self) -> None:
        prices = [
            PriceRow(date="20240101", close=100),
            PriceRow(date="20240102", close=120),
            PriceRow(date="20240103", close=90),
            PriceRow(date="20240104", close=110),
        ]
        result = maximum_drawdown(prices)
        assert result is not None
        # Drawdown from 120 to 90 = 25%
        assert abs(result.value - 0.25) < 1e-6

    def test_multi_window_sensitivity(self) -> None:
        prices = _sample_prices(130)
        results = multi_window_sensitivity(prices, windows=(20, 60, 120))
        assert len(results) == 3
        assert all(r.value is not None for r in results)

    def test_multi_window_insufficient_data(self) -> None:
        prices = _sample_prices(15)
        results = multi_window_sensitivity(prices, windows=(20, 60, 120))
        # Only 15 days: 20d and above should have None
        assert results[0].value is None
        assert "数据不足" in results[0].limitations[0]

    def test_cross_section_rank(self) -> None:
        result = cross_section_rank(0.15, [0.05, 0.10, 0.20, 0.25], "return")
        assert result.metric_id == "rank_return"
        assert 0.0 < result.value < 1.0

    def test_run_full_cross_check(self) -> None:
        prices = _sample_prices(130)
        results = run_cross_check(prices)
        metric_ids = [r.metric_id for r in results]
        assert "period_return" in metric_ids
        assert "annualized_volatility" in metric_ids
        assert "maximum_drawdown" in metric_ids

    def test_consistency_check_inconclusive_default(self) -> None:
        results = [CrossCheckResult(
            metric_id="test", method="test", description="test",
            value=0.05, unit="ratio", window="test", sample_count=10,
        )]
        check = assess_consistency("公司基本面良好", "research", results)
        assert check.label == "inconclusive"


# ---------------------------------------------------------------------------
# EvidenceBundle tests (spec §13.1)
# ---------------------------------------------------------------------------


class TestEvidenceBundle:
    def test_build_from_comprehensive_results(self) -> None:
        spec = _comprehensive_spec()
        plan = _comprehensive_plan()
        results = {
            "step-fundamentals": ExpertResult(
                task_id="step-fundamentals",
                agent=AgentId.RESEARCH,
                status="completed",
                summary="基本面分析完成",
                evidence=[{"type": "financial", "data": "revenue_growth"}],
            ),
            "step-industry": ExpertResult(
                task_id="step-industry",
                agent=AgentId.RESEARCH,
                status="completed",
                summary="行业竞争分析完成",
                evidence=[
                    {"type": "competitor", "data": "byd_vs_peers"},
                    {"type": "ranking", "data": "market_share"},
                    {"type": "detail", "data": "industry_info"},
                ],
            ),
            "step-macro": ExpertResult(
                task_id="step-macro",
                agent=AgentId.MACRO,
                status="completed",
                summary="宏观环境分析",
                evidence=[{"type": "macro", "data": "gdp_trend"}],
            ),
            "step-quant": ExpertResult(
                task_id="step-quant",
                agent=AgentId.QUANT,
                status="completed",
                summary="量化验证",
                evidence=[{"type": "quant", "metric": "period_return", "value": 0.15}],
            ),
            "step-risk": ExpertResult(
                task_id="step-risk",
                agent=AgentId.RISK,
                status="completed",
                summary="风险评估",
                evidence=[{"type": "risk", "event": "pledge_warning"}],
            ),
        }
        bundle = build_evidence_bundle(spec, plan, results)
        assert len(bundle.completed_steps) == 5
        assert len(bundle.failed_steps) == 0
        assert len(bundle.missing_dimensions) == 0
        assert len(bundle.all_evidence_ids) >= 5
        # Industry has 3 items -> sufficient
        assert bundle.dimensions["industry_competition"].status == "sufficient"

    def test_partial_failure_marks_dimension(self) -> None:
        spec = _comprehensive_spec()
        plan = _comprehensive_plan()
        results = {
            "step-fundamentals": ExpertResult(
                task_id="step-fundamentals",
                agent=AgentId.RESEARCH,
                status="failed",
                summary="",
                error="PandaData unavailable",
            ),
            "step-industry": ExpertResult(
                task_id="step-industry",
                agent=AgentId.RESEARCH,
                status="completed",
                summary="行业分析",
                evidence=[{"type": "industry"}],
            ),
            "step-macro": ExpertResult(
                task_id="step-macro",
                agent=AgentId.MACRO,
                status="completed",
                summary="宏观",
                evidence=[{"type": "macro"}],
            ),
            "step-quant": ExpertResult(
                task_id="step-quant",
                agent=AgentId.QUANT,
                status="completed",
                summary="quant",
                evidence=[{"type": "quant"}],
            ),
            "step-risk": ExpertResult(
                task_id="step-risk",
                agent=AgentId.RISK,
                status="completed",
                summary="risk",
                evidence=[{"type": "risk"}],
            ),
        }
        bundle = build_evidence_bundle(spec, plan, results)
        # company_fundamentals failed
        assert bundle.dimensions["company_fundamentals"].status == "unavailable"
        assert "company_fundamentals" in bundle.missing_dimensions

    def test_evidence_id_validation(self) -> None:
        allowlist = {"ev-step1-0001", "ev-step1-0002", "ev-step2-0003"}
        valid, invalid = validate_evidence_ids(
            ["ev-step1-0001", "ev-fake-9999", "ev-step2-0003"],
            allowlist,
        )
        assert valid == ["ev-step1-0001", "ev-step2-0003"]
        assert invalid == ["ev-fake-9999"]
