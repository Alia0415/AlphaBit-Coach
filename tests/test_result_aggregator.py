from __future__ import annotations

from backend.core.contracts import ExecutionPlan, ExpertResult
from backend.core.result_aggregator import ResultAggregator
from backend.core.evidence_validator import EvidenceValidator
from backend.core.task_spec import TaskSpec


def _plan(
    agents: list[str],
    *,
    intent: str = "analysis",
    clarification: str | None = None,
) -> ExecutionPlan:
    return ExecutionPlan.model_validate(
        {
            "goal": "完成用户请求",
            "intent": intent,
            "complexity": "medium",
            "selected_agents": [
                {"agent": agent, "reason": "任务需要"} for agent in agents
            ],
            "steps": [
                {
                    "id": f"{agent}_{index}",
                    "agent": agent,
                    "objective": f"执行 {agent} 分析",
                    "inputs": {},
                    "depends_on": [],
                    "expected_output": "结构化结果",
                }
                for index, agent in enumerate(agents, start=1)
            ],
            "needs_clarification": clarification is not None,
            "clarification_question": clarification,
        }
    )


def _result(
    task_id: str,
    agent: str,
    *,
    status: str = "completed",
    summary: str = "分析已经完成。",
    evidence: list[dict] | None = None,
    risks: list[str] | None = None,
    limitations: list[str] | None = None,
    recommendations: list[str] | None = None,
    data_sources: list[dict] | None = None,
    metadata: dict | None = None,
) -> ExpertResult:
    return ExpertResult.model_validate(
        {
            "task_id": task_id,
            "agent": agent,
            "status": status,
            "summary": summary,
            "evidence": evidence or [],
            "risks": risks or [],
            "limitations": limitations or [],
            "recommendations": recommendations or [],
            "data_sources": data_sources or [],
            "metadata": metadata or {},
            "error": "dependency blocked" if status != "completed" else None,
        }
    )


def _types(aggregation) -> list[str]:
    return [block.type for block in aggregation.content_blocks]


def test_quant_only_factor_ideas_generate_only_evidence_backed_blocks() -> None:
    plan = _plan(["quant"], intent="factor_ideation")
    result = _result(
        "quant_1",
        "quant",
        summary="生成 5 个候选并筛选 2 个。",
        evidence=[
            {
                "type": "skill_result",
                "data": {
                    "candidates": [
                        {"name": f"factor-{index}", "hypothesis": "待验证"}
                        for index in range(5)
                    ],
                    "shortlist": ["factor-0", "factor-1"],
                    "validation_status": "unverified",
                },
            }
        ],
        limitations=["尚未运行回测。"],
        metadata={"validation_status": "unverified"},
    )

    aggregation = ResultAggregator().aggregate("生成因子想法", plan, {"quant_1": result})

    assert aggregation.output_mode == "idea_generation"
    assert "factor_list" in _types(aggregation)
    assert "limitations" in _types(aggregation)
    assert not {"risk_list", "report", "comparison"} & set(_types(aggregation))
    assert "尚未经过回测或有效性验证" in aggregation.direct_answer.explanation


def test_quant_computation_is_not_described_as_validated_or_profitable() -> None:
    plan = _plan(["quant"], intent="factor_computation")
    result = _result(
        "quant_1",
        "quant",
        evidence=[
            {
                "data": {
                    "factor_id": "R020",
                    "observation_count": 726,
                    "coverage_ratio": 0.9421,
                    "validation_status": "computed_not_validated",
                }
            }
        ],
        data_sources=[
            {
                "name": "PandaData",
                "symbols": ["000001.SZ"],
                "start_date": "20240101",
                "end_date": "20241231",
            }
        ],
        metadata={"validation_status": "computed_not_validated"},
    )

    aggregation = ResultAggregator().aggregate("计算 R020", plan, {"quant_1": result})

    assert aggregation.output_mode == "data_analysis"
    assert {"metric_cards", "data_scope"} <= set(_types(aggregation))
    assert "不能据此证明方法能够稳定获利" in aggregation.direct_answer.explanation
    assert aggregation.direct_answer.confidence == "low"


def test_aggregator_adds_quant_decision_calibration_block() -> None:
    plan = _plan(["research", "quant"], intent="multidimensional_research")
    result = _result(
        "quant_2",
        "quant",
        summary="完成量化决策校验。",
        evidence=[
            {
                "type": "quant_thesis_validation",
                "claim_id": "research_1:summary",
                "claim_source_step": "research_1",
                "claim_text": "公司的竞争优势正在扩大。",
                "claim_direction": "positive",
                "assessment": "mixed",
                "assessment_scope": "historical_market_alignment",
                "metric_ids": ["period_return", "return_20d"],
                "reason": "不同时间窗口的收益方向不一致。",
                "text": "历史市场表现对该观点提供混合证据。",
                "validation_status": "historical_computation",
            }
        ],
    )

    aggregation = ResultAggregator().aggregate(
        "综合研究并进行量化校验",
        plan,
        {"quant_2": result},
    )

    block = next(
        item
        for item in aggregation.content_blocks
        if item.title == "量化决策校验"
    )
    assert block.type == "finding_cards"
    assert block.source_steps == ["quant_2"]
    assert block.data["items"][0]["assessment"] == "mixed"


def test_risk_only_does_not_create_quant_or_research_content() -> None:
    plan = _plan(["risk"], intent="risk_review")
    result = _result(
        "risk_1",
        "risk",
        risks=["市场状态切换可能使策略失效。"],
        recommendations=["补充样本外验证。"],
    )

    aggregation = ResultAggregator().aggregate("检查策略风险", plan, {"risk_1": result})

    assert aggregation.output_mode == "risk_review"
    assert {"risk_list", "action_list"} <= set(_types(aggregation))
    assert "metric_cards" not in _types(aggregation)
    assert "report" not in _types(aggregation)


def test_research_only_generates_metrics_scope_and_plain_metric_explanation() -> None:
    plan = _plan(["research"], intent="market_performance")
    result = _result(
        "research_1",
        "research",
        evidence=[
            {
                "type": "market_metrics",
                "symbol": "000001.SZ",
                "observation_count": 242,
                "period_return": -0.087,
                "maximum_drawdown": -0.223,
            }
        ],
        data_sources=[
            {
                "name": "PandaData",
                "symbols": ["000001.SZ"],
                "start_date": "20240101",
                "end_date": "20241231",
            }
        ],
    )

    aggregation = ResultAggregator().aggregate("分析市场表现", plan, {"research_1": result})
    metric_block = next(
        block for block in aggregation.content_blocks if block.type == "metric_cards"
    )

    assert {"metric_cards", "data_scope"} <= set(_types(aggregation))
    drawdown = next(
        metric
        for metric in metric_block.data["metrics"]
        if metric["metric"] == "maximum_drawdown"
    )
    assert "最大可能经历约 22.30% 的账面下跌" in drawdown["explanation"]


def test_dossier_derived_metrics_are_promoted_to_user_facing_cards() -> None:
    plan = _plan(["research"], intent="company_financials")
    result = _result(
        "research_1",
        "research",
        evidence=[
            {
                "type": "skill_result",
                "data": {
                    "symbol": "600519.SH",
                    "profitability": {
                        "derived_metrics": [
                            {
                                "metric": "gross_margin",
                                "value": 0.9193,
                                "period": "2024q4",
                                "formula": "毛利润 / 营业收入",
                                "method": "get_fina_reports",
                            }
                        ]
                    },
                },
            }
        ],
    )

    aggregation = ResultAggregator().aggregate(
        "分析公司财务质量",
        plan,
        {"research_1": result},
    )
    metric_block = next(
        block for block in aggregation.content_blocks if block.type == "metric_cards"
    )
    gross_margin = metric_block.data["metrics"][0]

    assert aggregation.output_mode == "data_analysis"
    assert "已完成所需的数据计算" not in aggregation.direct_answer.headline
    assert "毛利率 91.93%" in aggregation.direct_answer.headline
    assert gross_margin["label"] == "毛利率"
    assert gross_margin["display_value"] == "91.93%"
    assert gross_margin["subject"] == "600519.SH · 2024q4"
    assert gross_margin["formula"] == "毛利润 / 营业收入"
    assert gross_margin["method"] == "get_fina_reports"


def test_parallel_results_are_aggregated_but_missing_agent_is_not_invented() -> None:
    plan = _plan(["macro", "research"], intent="industry_opportunity")
    results = {
        "macro_1": _result("macro_1", "macro", summary="宏观需求保持平稳。"),
        "research_2": _result("research_2", "research", summary="行业估值分化明显。"),
    }

    aggregation = ResultAggregator().aggregate("分析行业机会", plan, results)

    findings = next(
        block for block in aggregation.content_blocks
        if block.type == "finding_cards"
    )
    assert len(findings.data["items"]) == 2
    assert set(aggregation.technical_evidence.source_results) == set(results)
    assert "risk_list" not in _types(aggregation)


def test_report_result_is_primary_and_not_rewritten() -> None:
    plan = _plan(["research", "report"], intent="formal_report")
    report_text = "# 正式报告\n\n这是 Report Agent 的原始正文。"
    results = {
        "research_1": _result("research_1", "research", summary="上游研究完成。"),
        "report_2": _result(
            "report_2",
            "report",
            summary=report_text,
            metadata={"report": report_text},
        ),
    }

    aggregation = ResultAggregator().aggregate("生成正式报告", plan, results)

    assert aggregation.output_mode == "formal_report"
    assert aggregation.content_blocks[0].type == "report"
    assert aggregation.content_blocks[0].data["content"] == report_text


def test_clarification_returns_only_clarification_block() -> None:
    plan = _plan([], clarification="请提供股票代码和日期范围。")

    aggregation = ResultAggregator().aggregate("帮我分析", plan, {})

    assert aggregation.completion_status == "needs_clarification"
    assert aggregation.output_mode == "clarification"
    assert _types(aggregation) == ["clarification"]


def test_partial_failure_preserves_success_and_adds_failure_notice() -> None:
    plan = _plan(["macro", "research"], intent="parallel_analysis")
    results = {
        "macro_1": _result("macro_1", "macro", summary="宏观分析完成。"),
        "research_2": _result(
            "research_2",
            "research",
            status="failed",
            summary="行业数据分析失败。",
        ),
    }

    aggregation = ResultAggregator().aggregate("分析行业", plan, results)

    assert aggregation.completion_status == "partially_completed"
    assert "narrative" in _types(aggregation)
    assert "failure_notice" in _types(aggregation)
    assert "部分分析已完成" in aggregation.direct_answer.explanation


def test_all_failed_is_user_readable_and_does_not_fabricate_results() -> None:
    plan = _plan(["research"], intent="analysis")
    results = {
        "research_1": _result(
            "research_1",
            "research",
            status="failed",
            summary="市场数据获取失败。",
        )
    }

    aggregation = ResultAggregator().aggregate("分析股票", plan, results)

    assert aggregation.completion_status == "failed"
    assert aggregation.output_mode == "failure"
    assert "系统没有使用模拟数据" in aggregation.direct_answer.explanation
    assert _types(aggregation) == ["failure_notice"]
    assert "metric_cards" not in _types(aggregation)


def test_governed_all_failed_returns_only_execution_failure_details() -> None:
    spec = TaskSpec(
        task_type="company_research",
        subject_type="company",
        subjects=["600519.SH"],
        research_goal="分析公司财务质量",
        expected_result_type="company_research",
        evidence_requirements=["最近三年财务数据"],
        execution_decision="execute",
    )
    plan = _plan(["research", "risk"], intent="company_research")
    results = {
        "research_1": _result(
            "research_1",
            "research",
            status="failed",
            summary="财务数据查询未完成。",
            limitations=["财务报告期必须使用类似 2024q4 的实际值。"],
        ),
        "risk_2": _result(
            "risk_2",
            "risk",
            status="blocked",
            summary="前置分析未完成，本步骤无法继续。",
        ),
    }
    validation = EvidenceValidator().validate(spec, plan, results)

    aggregation = ResultAggregator().aggregate(spec, plan, validation)

    assert aggregation.completion_status == "failed"
    assert _types(aggregation) == ["failure_notice"]
    assert aggregation.key_findings == []
    assert aggregation.evidence_summary == []
    assert aggregation.risks == []
    assert aggregation.limitations == []
    assert aggregation.next_research_steps == []


def test_empty_blocks_are_never_returned() -> None:
    plan = _plan(["research"])
    result = _result("research_1", "research", summary="")

    aggregation = ResultAggregator().aggregate("直接回答", plan, {"research_1": result})

    assert all(
        any(value not in (None, "", [], {}) for value in block.data.values())
        for block in aggregation.content_blocks
    )


def test_raw_expert_result_remains_traceable_in_technical_evidence() -> None:
    plan = _plan(["research"])
    result = _result(
        "research_1",
        "research",
        evidence=[{"symbol": "000001.SZ", "observation_count": 10}],
    )

    aggregation = ResultAggregator().aggregate("分析", plan, {"research_1": result})

    traced = aggregation.technical_evidence.source_results["research_1"]
    assert traced == result
    assert traced.evidence[0]["symbol"] == "000001.SZ"


def test_aggregator_has_deterministic_fallback_without_ark_client() -> None:
    plan = _plan(["risk"], intent="risk_review")
    result = _result("risk_1", "risk", risks=["流动性可能不足。"])

    aggregation = ResultAggregator().aggregate("检查风险", plan, {"risk_1": result})

    assert aggregation.direct_answer.headline
    assert aggregation.content_blocks
