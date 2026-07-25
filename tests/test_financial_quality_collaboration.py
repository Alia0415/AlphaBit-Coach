"""Focused multi-agent collaboration for company financial-quality research."""

from __future__ import annotations

import pytest

from backend.agents.manager_agent import ManagerAgent
from backend.agents.risk_agent import RiskAgent
from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import (
    AgentId,
    AgentSelection,
    DependencyRef,
    ExecutionPlan,
    ExpertResult,
    ExpertTask,
    PlanStep,
)
from backend.core.plan_validator import (
    PlanValidationError,
    validate_execution_plan,
    validate_plan_dimensions,
)
from backend.core.policy_contracts import PolicyDecision
from backend.core.task_interpreter import TaskInterpreter


PROMPT = "分析贵州茅台（600519.SH）近三个财年的盈利能力与财务质量"


class _UnavailableArk:
    def chat(self, prompt: str, model: str | None = None) -> str:
        raise RuntimeError("model unavailable")


class _SingleDimensionArk:
    def chat_json(self, request):
        return request.response_model.model_validate(
            {
                "request_scope": "focused",
                "required_dimensions": ["company_fundamentals"],
                "optional_dimensions": [],
                "reasoning": "财务请求",
            }
        )


def _allowed_policy() -> PolicyDecision:
    return PolicyDecision(
        decision="allowed_research",
        allowed=True,
        domain="quant_investment_research",
        policy_tags=["company_research"],
        reason="Company research is allowed.",
    )


def _financial_quality_spec():
    return TaskInterpreter().interpret(PROMPT, _allowed_policy())


def _research_step() -> PlanStep:
    return PlanStep(
        id="research_financials",
        agent=AgentId.RESEARCH,
        objective="计算近三个财年的盈利能力与财务质量指标",
        inputs={
            "symbol": "600519.SH",
            "period": "latest_3_fiscal_years",
            "scope": "financials",
            "research_goal": PROMPT,
        },
        covers_dimensions=["company_fundamentals"],
        expected_output="结构化财务事实",
    )


def _risk_step(*, dependency: bool) -> PlanStep:
    return PlanStep(
        id="risk_financial_quality",
        agent=AgentId.RISK,
        objective="独立审查盈利质量、异常趋势与证据缺口",
        inputs={"symbol": "600519.SH"},
        dependencies=(
            [
                DependencyRef(
                    step_id="research_financials",
                    requirement="required",
                )
            ]
            if dependency
            else []
        ),
        covers_dimensions=["risk_assessment"],
        expected_output="财务质量风险与缺失证据",
    )


def _plan(*, dependency: bool) -> ExecutionPlan:
    return ExecutionPlan(
        goal=PROMPT,
        intent="财务事实研究与独立质量审查",
        complexity="medium",
        selected_agents=[
            AgentSelection(agent=AgentId.RESEARCH, reason="计算财务事实"),
            AgentSelection(agent=AgentId.RISK, reason="独立审查财务质量"),
        ],
        steps=[_research_step(), _risk_step(dependency=dependency)],
    )


def test_financial_quality_request_requires_research_and_risk_dimensions() -> None:
    spec = _financial_quality_spec()

    assert spec.request_scope == "focused"
    assert spec.required_dimensions == [
        "company_fundamentals",
        "risk_assessment",
    ]


def test_financial_quality_dimensions_survive_model_underclassification() -> None:
    spec = TaskInterpreter(ark_client=_SingleDimensionArk()).interpret(
        PROMPT,
        _allowed_policy(),
    )

    assert spec.request_scope == "focused"
    assert spec.required_dimensions == [
        "company_fundamentals",
        "risk_assessment",
    ]


def test_manager_prompt_requires_financial_quality_risk_dependency() -> None:
    spec = _financial_quality_spec()

    prompt = ManagerAgent(
        client=_UnavailableArk(),
        registry=AgentRegistry(),
    )._planning_prompt(spec, PROMPT)

    assert (
        "财务质量或盈利质量请求必须同时选择 Research 和 Risk"
        in prompt
    )
    assert "Risk 必须把 Research 财务步骤声明为 required 依赖" in prompt


def test_financial_quality_risk_step_requires_research_dependency() -> None:
    spec = _financial_quality_spec()
    registry = AgentRegistry()
    plan = validate_execution_plan(_plan(dependency=False), registry)

    with pytest.raises(
        PlanValidationError,
        match="financial-quality Risk step.*required Research dependency",
    ):
        validate_plan_dimensions(plan, spec, registry)

    valid = validate_execution_plan(_plan(dependency=True), registry)
    assert validate_plan_dimensions(valid, spec, registry) is valid


def test_risk_reviews_financial_quality_from_dossier_evidence() -> None:
    research = ExpertResult(
        task_id="research_financials",
        agent=AgentId.RESEARCH,
        status="completed",
        summary="三年财务分析完成。",
        evidence=[
            {
                "type": "skill_result",
                "skill_id": "a_share_stock_dossier",
                "validation_status": "calculated_from_disclosed_financial_data",
                "data": {
                    "periods": ["2023q4", "2024q4", "2025q4"],
                    "growth": {
                        "derived_metrics": [
                            {
                                "metric": "revenue_yoy",
                                "period": "2025q4",
                                "value": -0.0121,
                            },
                            {
                                "metric": "net_profit_yoy",
                                "period": "2025q4",
                                "value": -0.0453,
                            },
                        ]
                    },
                    "profitability": {
                        "derived_metrics": [
                            {
                                "metric": "net_margin",
                                "period": "2024q4",
                                "value": 0.5046,
                            },
                            {
                                "metric": "net_margin",
                                "period": "2025q4",
                                "value": 0.4876,
                            },
                        ]
                    },
                    "cash_flow_quality": {
                        "derived_metrics": [
                            {
                                "metric": "operating_cash_flow_to_net_profit",
                                "period": "2024q4",
                                "value": 1.07,
                            },
                            {
                                "metric": "operating_cash_flow_to_net_profit",
                                "period": "2025q4",
                                "value": 0.75,
                            },
                        ]
                    },
                    "operating_efficiency": {
                        "derived_metrics": [
                            {
                                "metric": "inventory_to_revenue",
                                "period": "2024q4",
                                "value": 0.318,
                            },
                            {
                                "metric": "inventory_to_revenue",
                                "period": "2025q4",
                                "value": 0.3638,
                            },
                        ]
                    },
                    "missing_information": [],
                    "data_scope": [
                        {
                            "method": "get_fina_reports",
                            "missing_status": "available",
                            "latest_report_period": "2025q4",
                        },
                        {
                            "method": "get_fina_performance",
                            "missing_status": "no_data",
                            "latest_report_period": None,
                        },
                        {
                            "method": "get_audit_opinion",
                            "missing_status": "available",
                            "latest_report_period": "2025q1",
                        },
                    ],
                },
            }
        ],
        data_sources=[{"name": "PandaData", "method": "get_fina_reports"}],
    )
    task = ExpertTask(
        task_id="risk_financial_quality",
        agent=AgentId.RISK,
        objective="独立审查盈利质量、异常趋势与证据缺口",
        original_user_request=PROMPT,
        inputs={"symbol": "600519.SH"},
        dependency_results={"research_financials": research},
    )

    result = RiskAgent(ark_client=_UnavailableArk()).execute(task)

    assert result.status == "completed"
    assert result.metadata["review_type"] == "financial_quality"
    assert any("经营现金流" in item and "0.75" in item for item in result.risks)
    assert any("净利率" in item for item in result.risks)
    assert any("存货" in item for item in result.risks)
    assert any(
        "2025q4 缺少对应年度审计意见" in item
        and "2025q1" in item
        for item in result.limitations
    )
    assert any(
        "get_fina_performance 未返回可用数据" in item
        for item in result.limitations
    )
    assert not any("交易成本" in item for item in result.risks)
