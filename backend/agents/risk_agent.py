"""Risk Agent supporting independent and dependency-based review."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from backend.core.contracts import AgentId, ExpertResult, ExpertTask
from backend.services.ark_client import ArkClient, ArkClientError
from backend.services.pandadata_client import PandaDataClient
from backend.skills.contracts import SkillInvocation, SkillStatus
from backend.skills.skill_registry import SkillRegistry


class RiskAgent:
    """Challenge assumptions without inventing missing evidence."""

    def __init__(
        self,
        ark_client: ArkClient | None = None,
        data_client: PandaDataClient | None = None,
        skill_registry: SkillRegistry | None = None,
    ) -> None:
        self._ark_client = ark_client
        self._data_client = data_client or PandaDataClient()
        self.skills = skill_registry or SkillRegistry(
            ark_client=ark_client,
            pandadata_client=self._data_client,
        )

    def execute(self, task: ExpertTask) -> ExpertResult:
        if task.agent != AgentId.RISK:
            return _failed(task, "Risk Agent 收到了不匹配的任务类型。")

        dependency_evidence = _dependency_evidence(task.dependency_results)
        event_result = None
        tool_calls: list[dict[str, Any]] = []
        agent_events: list[dict[str, Any]] = []
        symbols = _symbols(task.inputs)
        if symbols:
            event_result = self.skills.execute(
                SkillInvocation(
                    invocation_id=str(uuid4()),
                    skill_id="event_risk_alert",
                    agent=AgentId.RISK.value,
                    objective=task.objective,
                    inputs={**task.inputs, "symbols": symbols},
                )
            )
            agent_events.append(
                {
                    "type": (
                        "skill_completed"
                        if event_result.status == SkillStatus.COMPLETED
                        else "skill_failed"
                    ),
                    "metadata": {
                        "skill_id": "event_risk_alert",
                        "status": event_result.status.value,
                    },
                }
            )
            scope = event_result.data.get("data_scope", [])
            if isinstance(scope, list):
                tool_calls.extend(
                    {
                        "tool": item.get("method", "pandadata_event_data"),
                        "status": item.get("status", "unknown"),
                        "arguments": {
                            "symbol": item.get("symbol"),
                            "query_range": item.get("query_range"),
                        },
                        "row_count": item.get("row_count"),
                    }
                    for item in scope
                    if isinstance(item, dict)
                )
            tool_calls.append(
                {
                    "tool": "event_risk_alert",
                    "status": event_result.status.value,
                    "arguments": {
                        "symbols": symbols,
                        "start_date": task.inputs.get("start_date"),
                        "end_date": task.inputs.get("end_date"),
                    },
                }
            )
            if event_result.status != SkillStatus.COMPLETED:
                return _failed(
                    task,
                    event_result.error or "事件风险 Skill 不可用。",
                    tool_calls=tool_calls,
                    metadata={
                        "actual_skills": ["event_risk_alert"],
                        "agent_events": agent_events,
                    },
                )
            dependency_evidence.extend(
                {
                    "source_step": task.task_id,
                    "source_agent": AgentId.RISK.value,
                    "fact": item,
                    "upstream_assumptions": event_result.assumptions,
                    "upstream_limitations": event_result.limitations,
                    "validation_status": event_result.data.get(
                        "validation_status"
                    ),
                    "provenance": event_result.provenance,
                }
                for item in event_result.evidence
            )
        independent_context = {
            key: value
            for key, value in task.inputs.items()
            if value not in (None, "", [], {})
        }
        if not dependency_evidence and not independent_context and not task.objective:
            return _failed(task, "Risk Agent 缺少可审查的策略、观点或上游证据。")

        assessment = _assess(task, dependency_evidence, independent_context)
        summary = (
            f"风险等级为 {assessment['risk_level']}；"
            f"识别出 {len(assessment['risk_factors'])} 个主要风险因素。"
        )
        limitations = list(assessment["missing_evidence"])
        if event_result is not None:
            limitations.extend(event_result.limitations)
        try:
            explanation = self._get_ark_client().chat(
                _risk_prompt(task, dependency_evidence, assessment)
            ).strip()
            if explanation:
                summary = explanation
        except (ArkClientError, Exception):
            limitations.append(
                "Ark 风险解释服务不可用；风险清单由结构化证据规则降级生成。"
            )

        return ExpertResult(
            task_id=task.task_id,
            agent=AgentId.RISK,
            status="completed",
            summary=summary,
            evidence=dependency_evidence,
            assumptions=assessment["challenged_assumptions"],
            risks=assessment["risk_factors"],
            limitations=limitations,
            recommendations=assessment["recommended_follow_up"],
            tool_calls=tool_calls,
            data_sources=[
                *_dependency_sources(task.dependency_results),
                *(
                    [
                        {
                            "name": "PandaData",
                            "scope": "event_risk",
                            "symbols": symbols,
                            "query_range": event_result.data.get("query_range"),
                            "successful_methods": sum(
                                1
                                for item in event_result.data.get(
                                    "data_scope",
                                    [],
                                )
                                if isinstance(item, dict)
                                and item.get("status") == "completed"
                            ),
                        }
                    ]
                    if event_result is not None
                    else []
                ),
            ],
            metadata={
                **assessment,
                "actual_skills": (
                    ["event_risk_alert"] if event_result is not None else []
                ),
                "skill_provenance": (
                    [event_result.provenance]
                    if event_result is not None
                    else []
                ),
                "agent_events": agent_events,
                "mode": "dependency" if task.dependency_results else "independent",
                "fact_judgment_boundary": {
                    "facts": dependency_evidence,
                    "model_judgment": assessment["risk_factors"],
                    "unknowns": assessment["missing_evidence"],
                },
            },
        )

    def __call__(self, task: ExpertTask) -> ExpertResult:
        return self.execute(task)

    def _get_ark_client(self) -> ArkClient:
        if self._ark_client is None:
            self._ark_client = ArkClient()
        return self._ark_client


def _dependency_evidence(
    dependencies: dict[str, ExpertResult],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for step_id, result in dependencies.items():
        for item in result.evidence:
            evidence.append(
                {
                    "source_step": step_id,
                    "source_agent": result.agent.value,
                    "fact": item,
                    "upstream_assumptions": result.assumptions,
                    "upstream_limitations": result.limitations,
                    "validation_status": result.metadata.get(
                        "validation_status",
                        item.get("validation_status")
                        if isinstance(item, dict)
                        else None,
                    ),
                    "provenance": result.metadata.get("provenance", []),
                }
            )
    return evidence


def _dependency_sources(
    dependencies: dict[str, ExpertResult],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for step_id, result in dependencies.items():
        for item in result.data_sources:
            sources.append({"source_step": step_id, **item})
    return sources


def _symbols(inputs: dict[str, Any]) -> list[str]:
    values = inputs.get("symbols")
    raw = values if isinstance(values, list) else [values] if values else []
    if inputs.get("symbol"):
        raw = [inputs["symbol"], *raw]
    return list(
        dict.fromkeys(
            str(value).strip().upper()
            for value in raw
            if str(value).strip()
        )
    )


def _assess(
    task: ExpertTask,
    evidence: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    risk_factors: list[str] = []
    challenged = [
        "历史样本中的关系能够延续到未来市场环境。",
        "当前策略描述足以覆盖交易成本、容量和执行约束。",
    ]
    missing = [
        "缺少样本外验证和不同市场状态下的稳健性证据。",
        "缺少交易成本、滑点、容量与流动性约束数据。",
    ]
    failure_scenarios = [
        "市场状态切换导致历史信号失效。",
        "换手和冲击成本吞噬名义收益。",
    ]
    recommended_follow_up = [
        "补充样本外、滚动窗口和市场状态分层检验。",
        "将手续费、滑点、冲击成本和容量约束纳入验证。",
    ]

    max_drawdowns: list[float] = []
    volatilities: list[float] = []
    observation_counts: list[int] = []
    factor_coverages: list[float] = []
    unverified_factors: list[str] = []
    event_records: dict[tuple[str, str], int] = {}
    for cited in evidence:
        fact = cited.get("fact", {})
        if not isinstance(fact, dict):
            continue
        event_method = str(fact.get("method", "")).strip()
        event_symbol = str(fact.get("symbol", "")).strip()
        if event_method and event_symbol and "record" in fact:
            key = (event_symbol, event_method)
            event_records[key] = event_records.get(key, 0) + 1
        if isinstance(fact.get("maximum_drawdown"), (int, float)):
            max_drawdowns.append(float(fact["maximum_drawdown"]))
        if isinstance(fact.get("daily_volatility"), (int, float)):
            volatilities.append(float(fact["daily_volatility"]))
        if isinstance(fact.get("observation_count"), int):
            observation_counts.append(fact["observation_count"])
        factor_data = fact.get("data", {})
        if isinstance(factor_data, dict):
            if isinstance(factor_data.get("coverage_ratio"), (int, float)):
                factor_coverages.append(float(factor_data["coverage_ratio"]))
            factor_id = factor_data.get("factor_id") or fact.get("skill_id")
            validation_status = (
                fact.get("validation_status")
                or factor_data.get("validation_status")
                or cited.get("validation_status")
            )
            if validation_status in {
                "unverified",
                "computed_not_validated",
                "mixed_unvalidated",
            }:
                unverified_factors.append(str(factor_id or "quant factor"))

    if max_drawdowns:
        worst = min(max_drawdowns)
        risk_factors.append(f"上游证据显示样本内最大回撤为 {worst:.2%}。")
    if volatilities:
        peak_vol = max(volatilities)
        risk_factors.append(f"上游证据显示最高日波动率为 {peak_vol:.2%}。")
    if observation_counts and min(observation_counts) < 60:
        risk_factors.append(
            f"最小样本仅 {min(observation_counts)} 个观测，统计稳定性有限。"
        )
    if factor_coverages:
        risk_factors.append(
            f"上游因子计算的最低非空覆盖率为 {min(factor_coverages):.2%}。"
        )
    if unverified_factors:
        risk_factors.append(
            "上游结果明确标记为尚未验证有效性："
            + "、".join(dict.fromkeys(unverified_factors))
            + "。"
        )
        missing.append("缺少因子 IC、样本外和回测有效性证据。")
    for (symbol, method), count in sorted(event_records.items()):
        risk_factors.append(
            f"{symbol} 的 {method} 返回 {count} 条披露记录，"
            "需要核对公告原文、生效日期和具体字段后判断影响。"
        )
    if event_records:
        challenged = [
            "PandaData 披露记录的字段口径与公告原文一致。",
            "同一事件的重复披露或更新时间差异不改变事实含义。",
        ]
        missing = [
            "缺少公告原文、字段定义和生效日期的逐条复核。",
            "当前记录只能作为风险线索，不能确认影响方向或因果关系。",
        ]
        failure_scenarios = [
            "同一披露被更新或重复返回，若未去重可能放大风险判断。",
            "误读记录日期、截止日期或字段单位会造成错误归因。",
        ]
        recommended_follow_up = [
            "逐条核对公告原文、字段定义、披露日期和生效日期。",
            "对重复披露按事件主键和更新时间去重后再判断变化。",
        ]
    if not evidence:
        risk_factors.extend(
            [
                "策略可能对参数、样本区间和市场状态高度敏感。",
                "高换手特征会放大交易成本与执行偏差。",
                "成交量信号可能受流动性骤降和拥挤交易影响。",
            ]
        )
        missing.insert(0, "当前为独立审查，未提供可引用的市场数据证据。")

    level = "medium"
    if (max_drawdowns and min(max_drawdowns) <= -0.2) or (
        observation_counts and min(observation_counts) < 30
    ):
        level = "high"
    elif evidence and max_drawdowns and min(max_drawdowns) > -0.08:
        level = "low"

    return {
        "risk_level": level,
        "risk_factors": risk_factors,
        "challenged_assumptions": challenged,
        "missing_evidence": missing,
        "failure_scenarios": failure_scenarios,
        "recommended_follow_up": recommended_follow_up,
        "reviewed_context": context,
    }


def _risk_prompt(
    task: ExpertTask,
    evidence: list[dict[str, Any]],
    assessment: dict[str, Any],
) -> str:
    payload = {
        "objective": task.objective,
        "cited_dependency_evidence": evidence,
        "deterministic_assessment": assessment,
    }
    return f"""
你是 AlphaOS Risk Agent。请基于给定结构化事实解释风险，不得重复冒充 Research
结论，不得补造事实。明确区分数据事实、风险判断与未知信息，并引用 source_step。
不要给出买入卖出建议。用简洁中文返回风险摘要。

风险上下文：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def _failed(task: ExpertTask, error: str, **kwargs: Any) -> ExpertResult:
    return ExpertResult(
        task_id=task.task_id,
        agent=AgentId.RISK,
        status="failed",
        summary="Risk Agent 未能完成风险审查。",
        limitations=[error],
        error=error,
        **kwargs,
    )
