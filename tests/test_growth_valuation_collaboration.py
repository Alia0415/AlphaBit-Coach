"""Focused multi-agent collaboration for growth-and-valuation research."""

from __future__ import annotations

import pytest

from backend.agents.manager_agent import ManagerAgent, ManagerAgentError
from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import (
    AgentId,
    AgentSelection,
    ExecutionPlan,
    PlanStep,
)
from backend.core.plan_validator import (
    PlanValidationError,
    validate_execution_plan,
    validate_plan_dimensions,
)
from backend.core.policy_contracts import PolicyDecision
from backend.core.task_interpreter import TaskInterpreter


PROMPT = "评估宁德时代（300750.SZ）的成长性与估值水平"


class _SingleDimensionArk:
    def chat_json(self, request):
        return request.response_model.model_validate(
            {
                "request_scope": "focused",
                "required_dimensions": ["company_fundamentals"],
                "optional_dimensions": [],
                "reasoning": "公司基本面问题",
            }
        )


class _CapturingDimensionArk(_SingleDimensionArk):
    def __init__(self) -> None:
        self.requests = []

    def chat_json(self, request):
        self.requests.append(request)
        return super().chat_json(request)


class _ResearchOnlyPlanArk:
    def __init__(self, plan: ExecutionPlan) -> None:
        self.plan = plan
        self.calls = 0

    def chat_json(self, request):
        self.calls += 1
        return self.plan


def _allowed_policy() -> PolicyDecision:
    return PolicyDecision(
        decision="allowed_research",
        allowed=True,
        domain="quant_investment_research",
        policy_tags=["company_research"],
        reason="Company research is allowed.",
    )


def test_growth_valuation_dimensions_survive_model_underclassification() -> None:
    spec = TaskInterpreter(ark_client=_SingleDimensionArk()).interpret(
        PROMPT,
        _allowed_policy(),
    )

    assert spec.request_scope == "focused"
    assert spec.required_dimensions == [
        "company_fundamentals",
        "industry_competition",
        "quantitative_cross_check",
        "risk_assessment",
    ]


@pytest.mark.parametrize(
    "prompt",
    [
        "评估宁德时代（300750.SZ）的成长性",
        "评估宁德时代（300750.SZ）的估值水平",
    ],
)
def test_single_goal_does_not_force_growth_valuation_collaboration(
    prompt: str,
) -> None:
    spec = TaskInterpreter(ark_client=_SingleDimensionArk()).interpret(
        prompt,
        _allowed_policy(),
    )

    assert spec.required_dimensions == ["company_fundamentals"]


def test_ambiguous_dimension_analysis_disables_thinking() -> None:
    ark = _CapturingDimensionArk()

    TaskInterpreter(ark_client=ark).interpret(
        "评估宁德时代（300750.SZ）的成长性",
        _allowed_policy(),
    )

    assert ark.requests[0].thinking_mode == "disabled"


def test_growth_valuation_request_rejects_research_only_plan() -> None:
    spec = TaskInterpreter(ark_client=_SingleDimensionArk()).interpret(
        PROMPT,
        _allowed_policy(),
    )
    plan = ExecutionPlan(
        goal=PROMPT,
        intent="只做公司基本面",
        complexity="low",
        selected_agents=[
            AgentSelection(agent=AgentId.RESEARCH, reason="公司研究"),
        ],
        steps=[
            PlanStep(
                id="research_fundamentals",
                agent=AgentId.RESEARCH,
                objective="分析成长性",
                inputs={
                    "symbol": "300750.SZ",
                    "period": "latest_available",
                    "scope": "financials",
                    "focus": "成长性",
                    "research_goal": PROMPT,
                },
                covers_dimensions=["company_fundamentals"],
                expected_output="成长性基本面证据",
            ),
        ],
    )
    registry = AgentRegistry()
    validated = validate_execution_plan(plan, registry)

    with pytest.raises(
        PlanValidationError,
        match="does not cover required dimensions",
    ):
        validate_plan_dimensions(validated, spec, registry)


def test_manager_never_accepts_research_only_growth_valuation_plan() -> None:
    spec = TaskInterpreter(ark_client=_SingleDimensionArk()).interpret(
        PROMPT,
        _allowed_policy(),
    )
    research_only = ExecutionPlan(
        goal=PROMPT,
        intent="只做公司基本面",
        complexity="low",
        selected_agents=[
            AgentSelection(agent=AgentId.RESEARCH, reason="公司研究"),
        ],
        steps=[
            PlanStep(
                id="research_fundamentals",
                agent=AgentId.RESEARCH,
                objective="分析成长性",
                inputs={
                    "symbol": "300750.SZ",
                    "period": "latest_available",
                    "scope": "financials",
                    "focus": "成长性",
                    "research_goal": PROMPT,
                },
                covers_dimensions=["company_fundamentals"],
                expected_output="成长性基本面证据",
            ),
        ],
    )
    client = _ResearchOnlyPlanArk(research_only)

    with pytest.raises(ManagerAgentError):
        ManagerAgent(client=client).create_plan(spec, PROMPT)

    assert client.calls == 2


def test_manager_prompt_assigns_growth_valuation_collaboration_boundaries() -> None:
    spec = TaskInterpreter(ark_client=_SingleDimensionArk()).interpret(
        PROMPT,
        _allowed_policy(),
    )

    prompt = ManagerAgent(registry=AgentRegistry())._planning_prompt(
        spec,
        PROMPT,
    )

    assert "成长性与估值" in prompt
    assert "Research、Quant 和 Risk" in prompt
    assert "市场行为交叉验证不能替代估值指标" in prompt
    assert "不得把价格表现表述为估值高低" in prompt
