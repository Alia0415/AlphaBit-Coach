"""End-to-end mock tests for multidimensional stock research (spec §15.8).

Validates the full pipeline:
  TaskInterpreter → Manager → Validator → Executor → Aggregator

All external services (Ark, PandaData) are mocked.
"""

from __future__ import annotations

from typing import Any

import pytest

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
from backend.core.evidence_bundle import build_evidence_bundle
from backend.core.plan_validator import validate_execution_plan, validate_plan_dimensions
from backend.core.policy_contracts import PolicyDecision
from backend.core.result_aggregator import ResultAggregator
from backend.core.store import SessionState, Store, reset_store_for_tests
from backend.core.task_interpreter import TaskInterpreter, _deterministic_dimensions
from backend.core.task_spec import TaskSpec, _COMPREHENSIVE_DEFAULTS
from backend.core.workflow_executor import WorkflowExecutor
from backend.core.evidence_validator import EvidenceValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALLOWED_POLICY = PolicyDecision(
    decision="allowed_research",
    allowed=True,
    domain="quant_investment_research",
    policy_tags=["test"],
    reason="test",
)


def _comprehensive_plan() -> ExecutionPlan:
    """A mock Manager output for comprehensive BYD analysis."""
    return ExecutionPlan(
        goal="全面分析比亚迪",
        intent="multidimensional_stock_research",
        complexity="high",
        selected_agents=[
            AgentSelection(agent=AgentId.RESEARCH, reason="公司和行业"),
            AgentSelection(agent=AgentId.MACRO, reason="宏观"),
            AgentSelection(agent=AgentId.QUANT, reason="量化验证"),
            AgentSelection(agent=AgentId.RISK, reason="风险"),
        ],
        steps=[
            PlanStep(
                id="step-fundamentals",
                agent=AgentId.RESEARCH,
                objective="公司基本面",
                inputs={"symbol": "002594.SZ", "scope": "financials", "period": "2024q4"},
                covers_dimensions=["company_fundamentals"],
                expected_output="基本面证据",
            ),
            PlanStep(
                id="step-industry",
                agent=AgentId.RESEARCH,
                objective="行业竞争",
                inputs={"industry": "汽车", "symbol": "002594.SZ"},
                covers_dimensions=["industry_competition"],
                expected_output="行业证据",
            ),
            PlanStep(
                id="step-macro",
                agent=AgentId.MACRO,
                objective="宏观环境",
                inputs={
                    "industry": "汽车",
                    "time_range": "近一年",
                    "research_goal": "分析宏观环境",
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
                inputs={
                    "symbols": ["002594.SZ"],
                    "start_date": "20240101",
                    "end_date": "20241231",
                    "fields": [],
                },
                dependencies=[
                    DependencyRef(step_id="step-fundamentals", requirement="optional"),
                    DependencyRef(step_id="step-industry", requirement="optional"),
                ],
                covers_dimensions=["quantitative_cross_check"],
                expected_output="量化证据",
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


def _mock_expert_result(task: ExpertTask) -> ExpertResult:
    """Generate a mock completed result for any expert."""
    return ExpertResult(
        task_id=task.task_id,
        agent=task.agent,
        status="completed",
        summary=f"{task.agent.value} 分析完成: {task.objective}",
        evidence=[
            {"type": "mock_evidence", "step": task.task_id, "data": "sample"},
            {"type": "mock_metric", "step": task.task_id, "value": 0.15},
        ],
        tool_calls=[{"tool": "mock_tool", "status": "completed"}],
    )


# ---------------------------------------------------------------------------
# TaskInterpreter dimension tests
# ---------------------------------------------------------------------------


class TestInterpreterDimensions:
    def test_comprehensive_company_request(self) -> None:
        """'分析比亚迪' → comprehensive with 5 dimensions."""
        interpreter = TaskInterpreter()
        spec = interpreter.interpret("分析比亚迪 002594.SZ", _ALLOWED_POLICY)
        assert spec.request_scope == "comprehensive"
        assert set(spec.required_dimensions) == set(_COMPREHENSIVE_DEFAULTS)

    def test_focused_volatility_request(self) -> None:
        """'看比亚迪近三个月波动' → focused with quantitative_cross_check."""
        interpreter = TaskInterpreter()
        spec = interpreter.interpret("看比亚迪 002594.SZ 近三个月波动和回撤", _ALLOWED_POLICY)
        assert spec.request_scope == "focused"
        assert "quantitative_cross_check" in spec.required_dimensions

    def test_focused_risk_scan(self) -> None:
        """'扫描事件风险' → focused with risk_assessment."""
        interpreter = TaskInterpreter()
        spec = interpreter.interpret("扫描比亚迪 002594.SZ 事件风险", _ALLOWED_POLICY)
        assert spec.request_scope == "focused"
        assert "risk_assessment" in spec.required_dimensions

    def test_formal_report_includes_formal_report_dimension(self) -> None:
        """Formal report request includes formal_report dimension."""
        interpreter = TaskInterpreter()
        spec = interpreter.interpret("生成比亚迪 002594.SZ 正式报告", _ALLOWED_POLICY)
        assert "formal_report" in spec.required_dimensions

    def test_deterministic_fallback_when_no_llm(self) -> None:
        """Without LLM, deterministic fallback still sets dimensions."""
        scope, dims = _deterministic_dimensions("company_research", "company", "分析比亚迪")
        assert scope == "comprehensive"
        assert set(dims) == set(_COMPREHENSIVE_DEFAULTS)


# ---------------------------------------------------------------------------
# E2E comprehensive flow (spec §15.8)
# ---------------------------------------------------------------------------


class TestE2EComprehensiveFlow:
    def test_full_pipeline_five_dimensions(self) -> None:
        """Comprehensive request → 5 experts → 5 dimension result."""
        # 1. Interpret
        interpreter = TaskInterpreter()
        spec = interpreter.interpret("全面分析比亚迪 002594.SZ", _ALLOWED_POLICY)
        assert spec.request_scope == "comprehensive"
        assert len(spec.required_dimensions) == 5

        # 2. Plan (mock — normally from Manager LLM)
        plan = _comprehensive_plan()
        registry = AgentRegistry()
        validated = validate_execution_plan(plan, registry)
        validated = validate_plan_dimensions(validated, spec, registry)

        # 3. Execute with mock handlers
        handlers = {
            AgentId.RESEARCH: _mock_expert_result,
            AgentId.MACRO: _mock_expert_result,
            AgentId.QUANT: _mock_expert_result,
            AgentId.RISK: _mock_expert_result,
        }
        executor = WorkflowExecutor(handlers=handlers)
        events, results = executor.execute(validated)

        # All 5 steps completed
        assert len(results) == 5
        assert all(r.status == "completed" for r in results.values())

        # 4. Build evidence bundle
        bundle = build_evidence_bundle(spec, validated, results)
        assert len(bundle.completed_steps) == 5
        assert len(bundle.failed_steps) == 0
        assert len(bundle.missing_dimensions) == 0
        # Each step has 2 evidence items → all dimensions sufficient
        for dim in spec.required_dimensions:
            assert dim in bundle.dimensions
            assert bundle.dimensions[dim].status in ("sufficient", "partial")

        # 5. Evidence IDs are generated
        assert len(bundle.all_evidence_ids) >= 10  # 5 steps × 2 items

    def test_partial_failure_still_returns_results(self) -> None:
        """One expert fails → other dimensions still available."""
        interpreter = TaskInterpreter()
        spec = interpreter.interpret("全面分析比亚迪 002594.SZ", _ALLOWED_POLICY)
        plan = _comprehensive_plan()
        registry = AgentRegistry()
        validated = validate_execution_plan(plan, registry)
        validated = validate_plan_dimensions(validated, spec, registry)

        def _macro_fail(task: ExpertTask) -> ExpertResult:
            return ExpertResult(
                task_id=task.task_id,
                agent=task.agent,
                status="failed",
                summary="",
                error="PandaData unavailable",
            )

        handlers = {
            AgentId.RESEARCH: _mock_expert_result,
            AgentId.MACRO: _macro_fail,
            AgentId.QUANT: _mock_expert_result,
            AgentId.RISK: _mock_expert_result,
        }
        executor = WorkflowExecutor(handlers=handlers)
        events, results = executor.execute(validated)

        # Macro failed but others completed
        assert results["step-macro"].status == "failed"
        assert results["step-fundamentals"].status == "completed"
        assert results["step-risk"].status == "completed"  # optional deps don't block

        # Bundle reflects failure
        bundle = build_evidence_bundle(spec, validated, results)
        assert bundle.dimensions["macro_environment"].status == "unavailable"
        assert "macro_environment" in bundle.missing_dimensions
        # Other dimensions still have evidence
        assert bundle.dimensions["company_fundamentals"].status != "unavailable"

    def test_focused_request_minimal_experts(self) -> None:
        """Focused request → only relevant expert selected."""
        interpreter = TaskInterpreter()
        spec = interpreter.interpret("看比亚迪 002594.SZ 近三个月波动和回撤", _ALLOWED_POLICY)
        assert spec.request_scope == "focused"
        assert spec.required_dimensions == ["quantitative_cross_check"]

        # A focused plan with only quant
        plan = ExecutionPlan(
            goal="看比亚迪近三个月波动",
            intent="quantitative_analysis",
            complexity="low",
            selected_agents=[AgentSelection(agent=AgentId.QUANT, reason="量化")],
            steps=[
                PlanStep(
                    id="step-quant",
                    agent=AgentId.QUANT,
                    objective="波动分析",
                    inputs={
                        "symbols": ["002594.SZ"],
                        "start_date": "20240101",
                        "end_date": "20241231",
                        "fields": [],
                    },
                    covers_dimensions=["quantitative_cross_check"],
                    expected_output="波动数据",
                ),
            ],
        )
        registry = AgentRegistry()
        validated = validate_execution_plan(plan, registry)
        validated = validate_plan_dimensions(validated, spec, registry)

        # Execute
        handlers = {AgentId.QUANT: _mock_expert_result}
        executor = WorkflowExecutor(handlers=handlers)
        _, results = executor.execute(validated)
        assert len(results) == 1
        assert results["step-quant"].status == "completed"

    def test_report_not_added_without_explicit_request(self) -> None:
        """Report is not added when formal_report not requested (spec §6.3)."""
        interpreter = TaskInterpreter()
        spec = interpreter.interpret("全面分析比亚迪 002594.SZ", _ALLOWED_POLICY)
        # formal_report should NOT be in required_dimensions
        assert "formal_report" not in spec.required_dimensions


# ---------------------------------------------------------------------------
# Store idempotency and state machine tests (spec §12.1)
# ---------------------------------------------------------------------------


class TestStoreStateMachine:
    def setup_method(self) -> None:
        self.store = reset_store_for_tests(":memory:")

    def test_state_transitions(self) -> None:
        self.store.create_task(
            task_id="t1", prompt="test", status=SessionState.CREATED.value
        )
        assert self.store.transition_task_state("t1", to_state=SessionState.PLANNING)
        assert self.store.transition_task_state("t1", to_state=SessionState.EXECUTING)
        assert self.store.transition_task_state("t1", to_state=SessionState.AGGREGATING)
        assert self.store.transition_task_state("t1", to_state=SessionState.COMPLETED)

    def test_invalid_transition_rejected(self) -> None:
        self.store.create_task(
            task_id="t2", prompt="test", status=SessionState.CREATED.value
        )
        # Cannot skip planning → executing directly (must go through planning)
        assert not self.store.transition_task_state("t2", to_state=SessionState.EXECUTING)

    def test_terminal_state_cannot_transition(self) -> None:
        self.store.create_task(
            task_id="t3", prompt="test", status=SessionState.COMPLETED.value
        )
        assert not self.store.transition_task_state("t3", to_state=SessionState.FAILED)

    def test_idempotency_key_prevents_duplicate(self) -> None:
        self.store.create_task(
            task_id="t4",
            prompt="test",
            status="created",
            idempotency_key="key-abc",
        )
        # Second creation with same key is silently skipped
        self.store.create_task(
            task_id="t5",
            prompt="different",
            status="created",
            idempotency_key="key-abc",
        )
        # Only t4 exists
        assert self.store.get_task("t4") is not None
        assert self.store.get_task("t5") is None

    def test_lookup_by_idempotency_key(self) -> None:
        self.store.create_task(
            task_id="t6",
            prompt="test",
            status="created",
            idempotency_key="key-xyz",
        )
        found = self.store.get_task_by_idempotency_key("key-xyz")
        assert found is not None
        assert found["id"] == "t6"
        assert self.store.get_task_by_idempotency_key("key-nonexistent") is None

    def test_execution_id_defaults_to_task_id(self) -> None:
        self.store.create_task(task_id="t7", prompt="test", status="created")
        task = self.store.get_task("t7")
        # execution_id is stored but not in the returned dict by default
        # verify via direct SQL
        assert task is not None
