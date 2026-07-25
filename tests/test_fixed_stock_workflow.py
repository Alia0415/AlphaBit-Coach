"""Deterministic stock-analysis workflow contract."""

from datetime import date

from backend.core.agent_registry import AgentRegistry
from backend.core.fixed_stock_workflow import build_fixed_stock_workflow


def test_fixed_stock_workflow_uses_parallel_evidence_then_risk_review() -> None:
    spec, plan = build_fixed_stock_workflow(
        symbol="600519.SH",
        name="贵州茅台",
        board="沪市主板",
        research_goal="全面分析贵州茅台。",
        registry=AgentRegistry(),
        today=date(2026, 7, 26),
    )

    assert spec.start_date == "20250726"
    assert spec.end_date == "20260726"
    assert spec.execution_decision == "execute_with_defaults"
    assert [selection.agent.value for selection in plan.selected_agents] == [
        "research",
        "quant",
        "macro",
        "risk",
    ]
    assert [step.id for step in plan.steps] == [
        "market_evidence",
        "company_dossier",
        "quant_cross_check",
        "macro_context",
        "risk_review",
    ]
    assert all(not step.all_dependency_step_ids() for step in plan.steps[:-1])
    assert {
        dependency.step_id
        for dependency in plan.steps[-1].dependencies
    } == {
        "market_evidence",
        "company_dossier",
        "quant_cross_check",
        "macro_context",
    }
    assert all(
        dependency.requirement == "optional"
        for dependency in plan.steps[-1].dependencies
    )


def test_fixed_index_workflow_skips_company_dossier() -> None:
    spec, plan = build_fixed_stock_workflow(
        symbol="000300.SH",
        name="沪深300",
        board="宽基指数",
        research_goal="全面分析沪深300。",
        registry=AgentRegistry(),
        today=date(2026, 7, 26),
    )

    assert spec.subject_type == "market"
    assert "company_fundamentals" not in spec.required_dimensions
    assert "company_dossier" not in {step.id for step in plan.steps}
