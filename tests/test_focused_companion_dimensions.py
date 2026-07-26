"""Focused plans must admit the companion expert forced by the 2-expert rule."""

from __future__ import annotations

from backend.agents.manager_agent import ManagerAgent
from backend.core.contracts import (
    AgentId,
    AgentSelection,
    DependencyRef,
    ExecutionPlan,
    PlanStep,
)
from backend.core.policy_contracts import PolicyDecision
from backend.core.task_interpreter import TaskInterpreter


BROAD_INDUSTRY_PROMPT = "现在新能源行业值得投资吗？"


class _PlanArk:
    def __init__(self, *plans: ExecutionPlan) -> None:
        self.plans = list(plans)
        self.calls = 0

    def chat_json(self, request):
        self.calls += 1
        if not self.plans:
            raise AssertionError("Unexpected Manager model call")
        return self.plans.pop(0)


def _allowed_policy() -> PolicyDecision:
    return PolicyDecision(
        decision="allowed_research",
        allowed=True,
        domain="quant_investment_research",
        policy_tags=["research_only"],
        reason="请求可以在量化投资研究与证据边界内处理。",
    )


def _interpret(prompt: str):
    return TaskInterpreter().interpret(prompt, _allowed_policy())


def test_focused_industry_spec_admits_companion_review_dimensions() -> None:
    spec = _interpret(BROAD_INDUSTRY_PROMPT)

    assert spec.request_scope == "focused"
    assert spec.required_dimensions == ["industry_competition"]
    assert "risk_assessment" in spec.optional_dimensions
    assert "quantitative_cross_check" in spec.optional_dimensions


def test_focused_quant_spec_admits_risk_review_dimension() -> None:
    spec = _interpret("分析 300750.SZ 最近一年的波动和回撤")

    assert spec.request_scope == "focused"
    assert spec.required_dimensions == ["quantitative_cross_check"]
    assert "risk_assessment" in spec.optional_dimensions
    assert "quantitative_cross_check" not in spec.optional_dimensions


def test_event_risk_spec_admits_evidence_companion_dimensions() -> None:
    spec = _interpret("扫描 600519.SH 最近的事件风险")

    assert spec.required_dimensions == ["risk_assessment"]
    assert "company_fundamentals" in spec.optional_dimensions
    assert "quantitative_cross_check" in spec.optional_dimensions
    assert "risk_assessment" not in spec.optional_dimensions


def test_financial_quality_spec_keeps_curated_dimension_set() -> None:
    spec = _interpret("分析贵州茅台（600519.SH）近三个财年的盈利能力与财务质量")

    assert spec.required_dimensions == [
        "company_fundamentals",
        "risk_assessment",
    ]
    # The curated review pairing must not gain a Quant escape hatch.
    assert "quantitative_cross_check" not in spec.optional_dimensions


def _broad_industry_plan() -> ExecutionPlan:
    """The exact collaboration shape the Manager model produced in the field."""

    research = PlanStep(
        id="industry_research",
        agent=AgentId.RESEARCH,
        objective="研究新能源行业的竞争格局、产业链和市场前景",
        inputs={
            "industry": "新能源",
            "time_range": "latest_available_research_window",
            "research_goal": BROAD_INDUSTRY_PROMPT,
        },
        covers_dimensions=["industry_competition"],
        expected_output="新能源行业研究证据",
    )
    risk = PlanStep(
        id="risk_review",
        agent=AgentId.RISK,
        objective="审查行业风险因素与证据限制",
        inputs={"risk_context": "新能源行业投资价值评估"},
        depends_on=["industry_research"],
        dependencies=[
            DependencyRef(step_id="industry_research", requirement="required")
        ],
        covers_dimensions=["risk_assessment"],
        expected_output="行业风险审查",
    )
    return ExecutionPlan(
        goal="评估新能源行业的投资价值",
        intent="行业研究与独立风险审查协作",
        complexity="medium",
        selected_agents=[
            AgentSelection(agent=AgentId.RESEARCH, reason="行业研究"),
            AgentSelection(agent=AgentId.RISK, reason="独立风险审查"),
        ],
        steps=[research, risk],
    )


def test_manager_accepts_industry_research_with_risk_companion() -> None:
    spec = _interpret(BROAD_INDUSTRY_PROMPT)
    client = _PlanArk(_broad_industry_plan())

    plan = ManagerAgent(client=client).create_plan(spec, BROAD_INDUSTRY_PROMPT)

    assert client.calls == 1
    assert {selection.agent for selection in plan.selected_agents} == {
        AgentId.RESEARCH,
        AgentId.RISK,
    }
