"""Global minimum collaboration contract for executable Manager plans."""

from __future__ import annotations

from datetime import date

import pytest

from backend.agents.manager_agent import ManagerAgent, ManagerAgentError
from backend.core import fixed_stock_workflow
from backend.core import plan_validator
from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import (
    AgentId,
    AgentSelection,
    ExecutionPlan,
    PlanStep,
)
from backend.core.plan_validator import PlanValidationError
from backend.core.task_spec import TaskSpec


class _PlanArk:
    def __init__(self, *plans: ExecutionPlan) -> None:
        self.plans = list(plans)
        self.calls = 0

    def chat_json(self, request):
        self.calls += 1
        if not self.plans:
            raise AssertionError("Unexpected Manager model call")
        return self.plans.pop(0)


def _step(
    step_id: str,
    agent: AgentId,
    *,
    depends_on: list[str] | None = None,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        agent=agent,
        objective=f"{agent.value} work",
        inputs={},
        depends_on=depends_on or [],
        expected_output=f"{agent.value} evidence",
    )


def _plan(*steps: PlanStep) -> ExecutionPlan:
    agents = list(dict.fromkeys(step.agent for step in steps))
    return ExecutionPlan(
        goal="研究目标",
        intent="动态协作研究",
        complexity="medium",
        selected_agents=[
            AgentSelection(agent=agent, reason="承担独立研究职责")
            for agent in agents
        ],
        steps=list(steps),
    )


def _quant_spec() -> TaskSpec:
    return TaskSpec(
        task_type="historical_analysis",
        subject_type="company",
        subjects=["300750.SZ"],
        research_goal="分析宁德时代 2024 年的历史波动",
        expected_result_type="historical_analysis",
        execution_decision="execute",
        request_scope="focused",
        required_dimensions=["quantitative_cross_check"],
    )


def _quant_step() -> PlanStep:
    return PlanStep(
        id="quant_1",
        agent=AgentId.QUANT,
        objective="计算历史波动和回撤",
        inputs={
            "analysis_mode": "historical_cross_check",
            "symbols": ["300750.SZ"],
            "start_date": "20240101",
            "end_date": "20241231",
            "fields": [],
        },
        covers_dimensions=["quantitative_cross_check"],
        expected_output="历史波动证据",
    )


def _risk_review_step() -> PlanStep:
    return PlanStep(
        id="risk_1",
        agent=AgentId.RISK,
        objective="审查窗口选择、下行风险和证据限制",
        inputs={"symbols": ["300750.SZ"]},
        depends_on=["quant_1"],
        expected_output="独立风险审查",
    )


def test_single_expert_execution_plan_is_rejected() -> None:
    plan = _plan(_step("research_1", AgentId.RESEARCH))

    with pytest.raises(
        PlanValidationError,
        match="at least two distinct experts",
    ):
        plan_validator.validate_global_collaboration(plan)


def test_two_isolated_experts_are_rejected() -> None:
    plan = _plan(
        _step("research_1", AgentId.RESEARCH),
        _step("risk_1", AgentId.RISK),
    )

    with pytest.raises(
        PlanValidationError,
        match="cross-expert dependency",
    ):
        plan_validator.validate_global_collaboration(plan)


def test_two_experts_with_cross_expert_dependency_are_accepted() -> None:
    plan = _plan(
        _step("research_1", AgentId.RESEARCH),
        _step("risk_1", AgentId.RISK, depends_on=["research_1"]),
    )

    assert plan_validator.validate_global_collaboration(plan) is plan


def test_clarification_plan_is_exempt_from_expert_minimum() -> None:
    plan = ExecutionPlan(
        goal="需要澄清",
        intent="收集缺失信息",
        complexity="low",
        needs_clarification=True,
        clarification_question="请补充研究对象。",
    )

    assert plan_validator.validate_global_collaboration(plan) is plan


def test_manager_rejects_single_expert_after_one_repair() -> None:
    single = _plan(_quant_step())
    client = _PlanArk(single, single)

    with pytest.raises(ManagerAgentError):
        ManagerAgent(client=client).create_plan(_quant_spec())

    assert client.calls == 2


def test_manager_accepts_repaired_cross_expert_plan() -> None:
    single = _plan(_quant_step())
    collaborative = _plan(_quant_step(), _risk_review_step())
    client = _PlanArk(single, collaborative)

    result = ManagerAgent(client=client).create_plan(_quant_spec())

    assert {selection.agent for selection in result.selected_agents} == {
        AgentId.QUANT,
        AgentId.RISK,
    }
    assert client.calls == 2


def test_fixed_stock_shortcut_applies_global_collaboration_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated: list[ExecutionPlan] = []

    def record(plan: ExecutionPlan) -> ExecutionPlan:
        validated.append(plan)
        return plan

    monkeypatch.setattr(
        fixed_stock_workflow,
        "validate_global_collaboration",
        record,
    )

    _task_spec, plan = fixed_stock_workflow.build_fixed_stock_workflow(
        symbol="300750.SZ",
        name="宁德时代",
        board="电池",
        research_goal="评估宁德时代",
        registry=AgentRegistry(),
        today=date(2026, 7, 26),
    )

    assert validated == [plan]
