"""Deterministic planning for the stock-chart analysis shortcut."""

from __future__ import annotations

import re
from datetime import date, timedelta

from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import (
    AgentId,
    AgentSelection,
    DependencyRef,
    ExecutionPlan,
    PlanStep,
)
from backend.core.plan_validator import (
    validate_execution_plan,
    validate_global_collaboration,
)
from backend.core.task_spec import TaskSpec


_A_SHARE_SYMBOL = re.compile(r"^\d{6}\.(?:SH|SZ)$")
_INDEX_BOARD = "宽基指数"


def build_fixed_stock_workflow(
    *,
    symbol: str,
    name: str,
    board: str,
    research_goal: str,
    registry: AgentRegistry,
    today: date | None = None,
) -> tuple[TaskSpec, ExecutionPlan]:
    """Build the fixed, two-wave stock research DAG used by the chart CTA."""

    normalized_symbol = str(symbol or "").strip().upper()
    if _A_SHARE_SYMBOL.fullmatch(normalized_symbol) is None:
        raise ValueError("固定股票分析需要有效的 A 股代码，例如 600519.SH。")
    normalized_name = str(name or "").strip() or normalized_symbol
    normalized_board = str(board or "").strip()
    goal = str(research_goal or "").strip()
    if not goal:
        raise ValueError("固定股票分析需要明确的研究目标。")

    end = today or date.today()
    start = end - timedelta(days=365)
    start_date = start.strftime("%Y%m%d")
    end_date = end.strftime("%Y%m%d")
    is_index = normalized_board == _INDEX_BOARD
    subject_type = "market" if is_index else "company"
    task_type = "market_research" if is_index else "company_research"
    subject_label = f"{normalized_name}（{normalized_symbol}）"
    macro_scope = (
        "中国 A 股市场、主要行业与风格"
        if is_index
        else f"{normalized_name}所属行业与中国 A 股市场"
    )

    task_spec = TaskSpec(
        task_type=task_type,
        subject_type=subject_type,
        subjects=[normalized_symbol],
        market="A股",
        research_goal=goal,
        expected_result_type="多维股票研究报告",
        start_date=start_date,
        end_date=end_date,
        time_range_description="最近一年及最新可得数据",
        evidence_requirements=[
            "价格、成交量与量化指标",
            "基本面与行业证据" if not is_index else "行业与风格暴露证据",
            "宏观与政策证据",
            "公告、事件与风险证据",
            "数据截止日期、来源、不确定性与缺失信息",
        ],
        requested_validation_level="research_draft",
        assumptions=["固定股票分析预设默认观察最近一年。"],
        defaulted_fields=["start_date", "end_date"],
        missing_fields=[],
        execution_decision="execute_with_defaults",
        clarification_question=None,
        request_scope="comprehensive",
        required_dimensions=[
            *(
                ["industry_competition"]
                if is_index
                else ["company_fundamentals", "industry_competition"]
            ),
            "macro_environment",
            "quantitative_cross_check",
            "risk_assessment",
        ],
        optional_dimensions=[],
    )

    steps = [
        PlanStep(
            id="market_evidence",
            agent=AgentId.RESEARCH,
            objective=f"核验 {subject_label} 最近一年的价格、均线与成交量事实",
            inputs={
                "symbols": [normalized_symbol],
                "start_date": start_date,
                "end_date": end_date,
                "fields": ["trade_date", "symbol", "close", "volume"],
            },
            covers_dimensions=[],
            expected_output="带日期与来源的历史行情证据",
        ),
        PlanStep(
            id="quant_cross_check",
            agent=AgentId.QUANT,
            objective=f"计算 {subject_label} 的收益、波动、回撤与成交量交叉验证",
            inputs={
                "analysis_mode": "historical_cross_check",
                "symbols": [normalized_symbol],
                "start_date": start_date,
                "end_date": end_date,
                "fields": ["trade_date", "symbol", "close", "volume"],
            },
            covers_dimensions=["quantitative_cross_check"],
            expected_output="可复算的历史量化指标与限制说明",
        ),
        PlanStep(
            id="macro_context",
            agent=AgentId.MACRO,
            objective=f"分析影响 {subject_label} 的宏观、政策、周期与流动性环境",
            inputs={
                "industry": macro_scope,
                "time_range": "最近一年及最新可得数据",
                "research_goal": goal,
                "start_date": start_date,
                "end_date": end_date,
            },
            covers_dimensions=["macro_environment"],
            expected_output="与研究对象相关的宏观证据、传导路径与不确定性",
        ),
    ]

    if not is_index:
        steps.insert(
            1,
            PlanStep(
                id="company_dossier",
                agent=AgentId.RESEARCH,
                objective=f"核验 {subject_label} 的基本面、重要事项与行业竞争位置",
                inputs={
                    "symbol": normalized_symbol,
                    "period": "latest",
                    "scope": "full_dossier",
                    "focus": "基本面、重要公告或事件、行业竞争与证据缺口",
                    "research_goal": goal,
                },
                covers_dimensions=[
                    "company_fundamentals",
                    "industry_competition",
                ],
                expected_output="公司基本面、重要事项和行业竞争的可追溯证据",
            ),
        )

    upstream_ids = [step.id for step in steps]
    steps.append(
        PlanStep(
            id="risk_review",
            agent=AgentId.RISK,
            objective=f"综合审查 {subject_label} 的事件风险、证据冲突与主要不确定性",
            inputs={
                "symbol": normalized_symbol,
                "start_date": start_date,
                "end_date": end_date,
                "risk_context": "固定股票分析预设：审查全部上游证据并补充事件风险。",
            },
            dependencies=[
                DependencyRef(step_id=step_id, requirement="optional")
                for step_id in upstream_ids
            ],
            covers_dimensions=["risk_assessment"],
            expected_output="基于上游证据与事件数据的风险清单及待核查项",
        )
    )

    plan = ExecutionPlan(
        goal=goal,
        intent="使用固定股票研究预设并行采集证据，再集中进行风险审查",
        task_type=task_spec.task_type,
        expected_result_type=task_spec.expected_result_type,
        task_summary=f"{subject_label}固定多维研究",
        complexity="high",
        selected_agents=[
            AgentSelection(
                agent=AgentId.RESEARCH,
                reason="固定负责行情事实以及基本面与行业证据",
            ),
            AgentSelection(
                agent=AgentId.QUANT,
                reason="固定负责收益、波动、回撤和成交量交叉验证",
            ),
            AgentSelection(
                agent=AgentId.MACRO,
                reason="固定负责宏观、政策、周期与流动性环境",
            ),
            AgentSelection(
                agent=AgentId.RISK,
                reason="固定在上游完成后审查事件风险与证据缺口",
            ),
        ],
        steps=steps,
        needs_clarification=False,
        clarification_question=None,
        clarification_options=[],
    )
    validated = validate_execution_plan(plan, registry)
    return task_spec, validate_global_collaboration(validated)
