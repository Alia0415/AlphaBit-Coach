"""Quant Agent with internal, allowlisted dynamic skill planning."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict
from datetime import datetime
from statistics import median
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.agents.quant_cross_check import (
    CrossCheckResult,
    MarketAlignment,
    PriceRow,
    assess_market_alignment,
    cross_section_rank,
    run_cross_check,
)
from backend.core.contracts import AgentId, ExpertResult, ExpertTask
from backend.services.ark_client import ArkClient, ArkClientError, ArkJsonRequest
from backend.services.pandadata_client import PandaDataClient
from backend.skills.contracts import (
    SkillInvocation,
    SkillResult,
    SkillStatus,
)
from backend.skills.skill_registry import SkillRegistry


MAX_SKILL_STEPS = 3
PANDADATA_FIELDS = [
    "trade_date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
]
MAX_THESIS_PEER_CANDIDATES = 12
MAX_THESIS_VALID_PEERS = 5
MAX_FUNDAMENTAL_METRICS_PER_CLAIM = 3
_A_SHARE_SYMBOL_PATTERN = re.compile(r"^\d{6}\.(?:SH|SZ)$")
_GROWTH_METRICS = {
    "revenue_yoy",
    "operating_profit_yoy",
    "net_profit_yoy",
    "net_profit_excluding_nonrecurring_yoy",
}
_TREND_METRICS = {
    "gross_margin",
    "operating_margin",
    "net_margin",
    "operating_cash_flow_to_net_profit",
    "asset_liability_ratio",
    "current_ratio",
    "accounts_receivable_to_revenue",
    "inventory_to_revenue",
    "total_asset_turnover",
}
_LOWER_IS_HEALTHIER_METRICS = {
    "asset_liability_ratio",
    "accounts_receivable_to_revenue",
    "inventory_to_revenue",
}
_DOSSIER_METRICS = _GROWTH_METRICS | _TREND_METRICS


class SelectedSkill(BaseModel):
    skill_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class QuantSkillStep(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    skill_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list, max_length=MAX_SKILL_STEPS)

    @field_validator("depends_on")
    @classmethod
    def dependencies_are_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Skill step dependencies must be unique")
        return values


class QuantSkillPlan(BaseModel):
    selected_skills: list[SelectedSkill] = Field(
        default_factory=list,
        max_length=MAX_SKILL_STEPS,
    )
    steps: list[QuantSkillStep] = Field(
        default_factory=list,
        max_length=MAX_SKILL_STEPS,
    )
    needs_clarification: bool = False
    clarification_question: str | None = None


class ThesisClaimSelection(BaseModel):
    claim_id: str = Field(min_length=1)
    direction: Literal["positive", "negative", "risk", "neutral"]


class ThesisSelectionPlan(BaseModel):
    claims: list[ThesisClaimSelection] = Field(min_length=1, max_length=3)


class QuantAgent:
    """Plan and execute the minimal sufficient subset of Quant-owned skills."""

    def __init__(
        self,
        *,
        ark_client: ArkClient | None = None,
        data_client: PandaDataClient | None = None,
        skill_registry: SkillRegistry | None = None,
    ) -> None:
        self._ark_client = ark_client
        self._data_client = data_client or PandaDataClient()
        self.skills = skill_registry or SkillRegistry(ark_client=ark_client)

    def execute(self, task: ExpertTask) -> ExpertResult:
        if task.agent != AgentId.QUANT:
            return _failed(task, "Quant Agent 收到了不匹配的任务类型。")
        if task.inputs.get("analysis_mode") == "historical_cross_check":
            return self._execute_cross_check(task)
        if task.inputs.get("analysis_mode") == "thesis_validation":
            return self._execute_thesis_validation(task)
        try:
            plan = self.create_skill_plan(task)
        except QuantAgentError as exc:
            return _failed(task, str(exc))

        agent_events: list[dict[str, Any]] = [
            {
                "type": "skill_plan_created",
                "metadata": {
                    "skill_id": None,
                    "selected_skill_count": len(plan.selected_skills),
                    "skill_step_count": len(plan.steps),
                },
            }
        ]
        if plan.needs_clarification:
            question = plan.clarification_question or "请补充量化计算所需的输入。"
            return _failed(
                task,
                question,
                metadata={
                    "needs_clarification": True,
                    "clarification_question": question,
                    "skill_plan": plan.model_dump(mode="json"),
                    "agent_events": agent_events,
                },
            )

        missing = self._missing_required_inputs(plan, task)
        if missing:
            question = "请补充以下 Quant 输入：" + "、".join(sorted(missing)) + "。"
            return _failed(
                task,
                question,
                metadata={
                    "needs_clarification": True,
                    "clarification_question": question,
                    "skill_plan": plan.model_dump(mode="json"),
                    "agent_events": agent_events,
                },
            )
        if (
            _requests_cross_section(task.original_user_request)
            and len(_symbols(task.inputs.get("symbols"))) < 2
            and any(
                self.skills.get(selection.skill_id).input_schema.get(
                    "x-data-source"
                )
                == "pandadata_market_data"
                for selection in plan.selected_skills
            )
        ):
            question = "横截面排序至少需要两个 symbol；请补充标的池。"
            return _failed(
                task,
                question,
                metadata={
                    "needs_clarification": True,
                    "clarification_question": question,
                    "skill_plan": plan.model_dump(mode="json"),
                    "agent_events": agent_events,
                },
            )

        skill_results: dict[str, SkillResult] = {}
        tool_calls: list[dict[str, Any]] = []
        pending = {step.id: step for step in plan.steps}
        while pending:
            ready = [
                step
                for step in pending.values()
                if all(dependency in skill_results for dependency in step.depends_on)
            ]
            if not ready:
                return _failed(
                    task,
                    "Quant Skill Plan 没有可执行步骤。",
                    metadata={
                        "skill_plan": plan.model_dump(mode="json"),
                        "agent_events": agent_events,
                    },
                )
            for step in sorted(ready, key=lambda item: item.id):
                failed_dependency = next(
                    (
                        dependency
                        for dependency in step.depends_on
                        if skill_results[dependency].status != SkillStatus.COMPLETED
                    ),
                    None,
                )
                if failed_dependency:
                    result = SkillResult(
                        invocation_id=str(uuid4()),
                        skill_id=step.skill_id,
                        status=SkillStatus.FAILED,
                        summary="Skill 步骤因依赖失败而被阻断。",
                        limitations=[f"Required skill step failed: {failed_dependency}"],
                        error=f"Required skill step failed: {failed_dependency}",
                    )
                    skill_results[step.id] = result
                    agent_events.append(
                        _skill_event("skill_failed", step.skill_id, result.status)
                    )
                    pending.pop(step.id)
                    continue

                invocation_inputs = {
                    **task.inputs,
                    "original_user_request": task.original_user_request,
                    "dependency_results": {
                        dependency: skill_results[dependency].model_dump(mode="json")
                        for dependency in step.depends_on
                    },
                }
                data_result = self._prepare_declared_inputs(
                    step.skill_id,
                    invocation_inputs,
                    tool_calls,
                )
                agent_events.append(
                    _skill_event("skill_started", step.skill_id, None)
                )
                if isinstance(data_result, SkillResult):
                    result = data_result
                else:
                    invocation = SkillInvocation(
                        invocation_id=str(uuid4()),
                        skill_id=step.skill_id,
                        agent=AgentId.QUANT.value,
                        objective=step.objective,
                        inputs=data_result,
                    )
                    result = self.skills.execute(invocation)
                skill_results[step.id] = result
                tool_calls.append(
                    {
                        "tool": step.skill_id,
                        "status": result.status.value,
                        "arguments": {
                            "objective": step.objective,
                            "depends_on": step.depends_on,
                        },
                    }
                )
                agent_events.append(
                    _skill_event(
                        (
                            "skill_completed"
                            if result.status == SkillStatus.COMPLETED
                            else "skill_failed"
                        ),
                        step.skill_id,
                        result.status,
                    )
                )
                pending.pop(step.id)

        return _expert_result(
            task,
            plan,
            skill_results,
            tool_calls,
            agent_events,
        )

    def _execute_cross_check(self, task: ExpertTask) -> ExpertResult:
        symbols = _symbols(task.inputs.get("symbols"))
        missing = [
            name
            for name in ("symbols", "start_date", "end_date")
            if task.inputs.get(name) in (None, "", [], {})
        ]
        if missing:
            question = "请补充以下 Quant 输入：" + "、".join(missing) + "。"
            return _failed(
                task,
                question,
                metadata={
                    "needs_clarification": True,
                    "clarification_question": question,
                    "execution_path": "deterministic_cross_check",
                },
            )
        if _requests_cross_section(task.original_user_request) and len(symbols) < 2:
            question = "横截面排序至少需要两个 symbol；请补充标的池。"
            return _failed(
                task,
                question,
                metadata={
                    "needs_clarification": True,
                    "clarification_question": question,
                    "execution_path": "deterministic_cross_check",
                },
            )

        start_date = str(task.inputs["start_date"])
        end_date = str(task.inputs["end_date"])
        validation_error = _validate_market_request(
            symbols,
            start_date,
            end_date,
        )
        if validation_error:
            return _failed(
                task,
                validation_error,
                metadata={"execution_path": "deterministic_cross_check"},
            )
        tool_call = {
            "tool": "pandadata_market_data",
            "status": "started",
            "arguments": {
                "symbols": symbols,
                "start_date": start_date,
                "end_date": end_date,
                "fields": PANDADATA_FIELDS,
            },
        }
        try:
            raw_rows = self._data_client.get_market_data(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                fields=PANDADATA_FIELDS,
                indicator="000300",
                st=True,
            )
            grouped = _price_rows_by_symbol(raw_rows, symbols)
        except Exception:
            tool_call["status"] = "failed"
            return _failed(
                task,
                "PandaData OHLCV 获取失败。",
                metadata={"execution_path": "deterministic_cross_check"},
            ).model_copy(update={"tool_calls": [tool_call]})
        tool_call["status"] = "completed"

        evidence: list[dict[str, Any]] = []
        for symbol in symbols:
            target = grouped.get(symbol, [])
            peers = {
                peer: rows
                for peer, rows in grouped.items()
                if peer != symbol and rows
            }
            for metric in run_cross_check(
                target,
                peer_prices=peers if _requests_cross_section(
                    task.original_user_request
                ) else None,
            ):
                evidence.append(
                    {
                        "type": "quant_cross_check",
                        "symbol": symbol,
                        **asdict(metric),
                        "validation_status": "historical_computation",
                    }
                )
        if not evidence:
            return _failed(
                task,
                "PandaData 未返回足够的有效行情数据。",
                metadata={"execution_path": "deterministic_cross_check"},
            ).model_copy(update={"tool_calls": [tool_call]})

        return ExpertResult(
            task_id=task.task_id,
            agent=AgentId.QUANT,
            status="completed",
            summary=(
                f"Quant Agent 基于 PandaData 完成 {len(symbols)} 个标的的"
                f" {len(evidence)} 项历史量化交叉验证。"
            ),
            evidence=evidence,
            risks=["历史统计不代表未来表现，不能单独作为投资决策依据。"],
            limitations=[
                "未计算 IC，未运行回测，未生成交易信号或未来收益预测。"
            ],
            recommendations=["结合基本面、宏观和风险证据进行综合判断。"],
            tool_calls=[tool_call],
            data_sources=[
                {
                    "name": "PandaData",
                    "symbols": symbols,
                    "start_date": start_date,
                    "end_date": end_date,
                    "fields": PANDADATA_FIELDS,
                }
            ],
            metadata={
                "execution_path": "deterministic_cross_check",
                "actual_skills": [],
                "validation_status": "historical_computation",
                "calculation_engine": "quant_cross_check",
                "agent_events": [],
            },
        )

    def _execute_thesis_validation(self, task: ExpertTask) -> ExpertResult:
        candidates = _dependency_claim_candidates(task.dependency_results)
        if not candidates:
            return _failed(
                task,
                "Quant 观点校验需要至少一个已完成的上游 Research 或 Macro 结论。",
                metadata={"execution_path": "thesis_validation"},
            )

        selections, fallback_used = self._select_thesis_claims(task, candidates)
        target_symbols = _symbols(task.inputs.get("symbols"))
        peer_symbols = _dependency_peer_symbols(
            task.dependency_results,
            target_symbols,
        )
        market_task = task.model_copy(
            update={
                "inputs": {
                    **task.inputs,
                    "analysis_mode": "historical_cross_check",
                    "symbols": [*target_symbols, *peer_symbols],
                }
            }
        )
        market_result = self._execute_cross_check(market_task)
        if market_result.status != "completed":
            return market_result.model_copy(
                update={
                    "metadata": {
                        **market_result.metadata,
                        "execution_path": "thesis_validation",
                        "claim_selection_fallback_used": fallback_used,
                    }
                }
            )

        metrics_by_symbol = _cross_check_results_by_symbol(market_result.evidence)
        financial_metrics = _dependency_financial_metrics(
            task.dependency_results,
            target_symbols,
        )
        validations: list[dict[str, Any]] = []
        for selection in selections:
            claim = candidates[selection.claim_id]
            for symbol in target_symbols:
                metrics = metrics_by_symbol.get(symbol, [])
                alignment = assess_market_alignment(selection.direction, metrics)
                validations.append(
                    _thesis_validation_evidence(
                        claim=claim,
                        direction=selection.direction,
                        symbol=symbol,
                        metrics=metrics,
                        alignment=alignment,
                    )
                )
                validations.extend(
                    _fundamental_validation_evidence(
                        claim=claim,
                        direction=selection.direction,
                        symbol=symbol,
                        metrics=financial_metrics.get(
                            claim["source_step"],
                            {},
                        ).get(symbol, {}),
                    )
                )
                relative = _peer_relative_validation_evidence(
                    claim=claim,
                    direction=selection.direction,
                    symbol=symbol,
                    target_metrics=metrics,
                    peer_symbols=peer_symbols,
                    metrics_by_symbol=metrics_by_symbol,
                )
                if relative is not None:
                    validations.append(relative)

        target_market_evidence = [
            item
            for item in market_result.evidence
            if item.get("type") != "quant_cross_check"
            or item.get("symbol") in target_symbols
        ]

        return market_result.model_copy(
            update={
                "summary": (
                    f"Quant Agent 对 {len(selections)} 条上游观点完成多源"
                    f"一致性校验，形成 {len(validations)} 条量化决策证据。"
                ),
                "evidence": [*target_market_evidence, *validations],
                "limitations": list(
                    dict.fromkeys(
                        [
                            *market_result.limitations,
                            "历史市场与财务一致性不能证明观点成立或预测未来收益。",
                        ]
                    )
                ),
                "metadata": {
                    **market_result.metadata,
                    "execution_path": "thesis_validation",
                    "claim_selection_fallback_used": fallback_used,
                    "validated_claim_ids": [
                        selection.claim_id for selection in selections
                    ],
                    "peer_symbols": peer_symbols,
                },
            }
        )

    def _select_thesis_claims(
        self,
        task: ExpertTask,
        candidates: dict[str, dict[str, str]],
    ) -> tuple[list[ThesisClaimSelection], bool]:
        prompt = _thesis_selection_prompt(task, candidates)
        try:
            client = self._get_client()
            structured_chat = getattr(client, "chat_json", None)
            if callable(structured_chat):
                plan = structured_chat(
                    ArkJsonRequest[ThesisSelectionPlan](
                        prompt=prompt,
                        response_model=ThesisSelectionPlan,
                        temperature=0.0,
                        max_output_tokens=800,
                        timeout_seconds=45.0,
                        purpose="quant_thesis_selection",
                        prompt_version="quant-thesis-mvp-v1",
                    )
                )
            else:
                plan = ThesisSelectionPlan.model_validate(
                    _extract_json(client.chat(prompt))
                )
            if any(item.claim_id not in candidates for item in plan.claims):
                raise ValueError("Thesis selector returned an unknown claim ID")
            return plan.claims, False
        except Exception:
            fallback = [
                ThesisClaimSelection(claim_id=claim_id, direction="neutral")
                for claim_id, claim in candidates.items()
                if claim["kind"] == "summary"
            ][:3]
            if not fallback:
                fallback = [
                    ThesisClaimSelection(claim_id=claim_id, direction="neutral")
                    for claim_id in list(candidates)[:3]
                ]
            return fallback, True

    def __call__(self, task: ExpertTask) -> ExpertResult:
        return self.execute(task)

    def create_skill_plan(self, task: ExpertTask) -> QuantSkillPlan:
        """Ask Ark to plan over only the Quant Agent's authorized skills."""

        allowed = self.skills.prompt_payload(AgentId.QUANT.value)
        prompt = _planner_prompt(task, allowed)
        try:
            raw = self._get_client().chat(prompt)
            plan = _parse_and_validate_plan(raw, allowed)
            _validate_runtime_clarification(plan, task, allowed)
            return plan
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            try:
                repaired = self._get_client().chat(
                    _planner_repair_prompt(task, allowed, raw, str(exc))
                )
                plan = _parse_and_validate_plan(repaired, allowed)
                _validate_runtime_clarification(plan, task, allowed)
                return plan
            except (
                ArkClientError,
                json.JSONDecodeError,
                ValidationError,
                ValueError,
            ):
                raise QuantAgentError(
                    "Quant Skill Planner 在一次修复后仍未返回有效计划。"
                ) from None
        except ArkClientError:
            raise QuantAgentError("Quant Skill Planner 服务不可用。") from None

    def _missing_required_inputs(
        self,
        plan: QuantSkillPlan,
        task: ExpertTask,
    ) -> set[str]:
        required: set[str] = set()
        for selection in plan.selected_skills:
            required.update(self.skills.get(selection.skill_id).required_task_inputs)
        return {
            name
            for name in required
            if task.inputs.get(name) in (None, "", [], {})
        }

    def _prepare_declared_inputs(
        self,
        skill_id: str,
        inputs: dict[str, Any],
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any] | SkillResult:
        spec = self.skills.get(skill_id)
        if spec.input_schema.get("x-data-source") != "pandadata_market_data":
            return inputs

        call = {
            "tool": "pandadata_market_data",
            "status": "started",
            "arguments": {
                "symbols": inputs["symbols"],
                "start_date": inputs["start_date"],
                "end_date": inputs["end_date"],
                "fields": PANDADATA_FIELDS,
            },
        }
        tool_calls.append(call)
        validation_error = _validate_market_request(
            _symbols(inputs["symbols"]),
            str(inputs["start_date"]),
            str(inputs["end_date"]),
        )
        if validation_error:
            call["status"] = "failed"
            return SkillResult(
                invocation_id=str(uuid4()),
                skill_id=skill_id,
                status=SkillStatus.FAILED,
                summary="Quant 市场数据输入无效。",
                limitations=[validation_error],
                error=validation_error,
            )
        try:
            inputs["market_data"] = self._data_client.get_market_data(
                symbols=_symbols(inputs["symbols"]),
                start_date=str(inputs["start_date"]),
                end_date=str(inputs["end_date"]),
                fields=PANDADATA_FIELDS,
                indicator="000300",
                st=True,
            )
        except Exception:
            call["status"] = "failed"
            return SkillResult(
                invocation_id=str(uuid4()),
                skill_id=skill_id,
                status=SkillStatus.FAILED,
                summary="PandaData OHLCV 获取失败。",
                limitations=["外部市场数据服务请求失败。"],
                error="外部市场数据服务请求失败。",
            )
        call["status"] = "completed"
        return inputs

    def _get_client(self) -> ArkClient:
        if self._ark_client is None:
            self._ark_client = ArkClient()
        return self._ark_client


class QuantAgentError(RuntimeError):
    """Raised when the internal skill planner cannot produce a valid DAG."""


def _parse_and_validate_plan(
    raw: str,
    allowed_payload: list[dict[str, Any]],
) -> QuantSkillPlan:
    plan = QuantSkillPlan.model_validate(_extract_json(raw))
    if plan.needs_clarification:
        if not plan.clarification_question or not plan.clarification_question.strip():
            raise ValueError("Clarification plans require a question")
        if plan.steps or plan.selected_skills:
            raise ValueError("Clarification plans cannot contain skill steps")
        return plan
    if not plan.steps or not plan.selected_skills:
        raise ValueError("Executable Quant plans require selected skills and steps")
    allowed = {item["id"] for item in allowed_payload}
    selected = [item.skill_id for item in plan.selected_skills]
    if len(selected) != len(set(selected)):
        raise ValueError("selected_skills contains duplicates")
    if not set(selected).issubset(allowed):
        raise ValueError("Quant planner selected an unauthorized skill")
    step_ids = [step.id for step in plan.steps]
    if len(step_ids) != len(set(step_ids)):
        raise ValueError("Skill step IDs must be unique")
    used = {step.skill_id for step in plan.steps}
    if used != set(selected):
        raise ValueError("selected_skills must exactly match skills used by steps")
    known_ids = set(step_ids)
    dependencies: dict[str, list[str]] = {}
    for step in plan.steps:
        if step.skill_id not in allowed:
            raise ValueError("Skill step is unauthorized")
        if step.id in step.depends_on:
            raise ValueError("Skill step cannot depend on itself")
        if not set(step.depends_on).issubset(known_ids):
            raise ValueError("Skill step references an unknown dependency")
        dependencies[step.id] = step.depends_on
    _assert_acyclic(dependencies)
    return plan


def _assert_acyclic(dependencies: dict[str, list[str]]) -> None:
    state: dict[str, int] = {}

    def visit(step_id: str) -> None:
        if state.get(step_id) == 1:
            raise ValueError("Skill plan contains a dependency cycle")
        if state.get(step_id) == 2:
            return
        state[step_id] = 1
        for dependency in dependencies[step_id]:
            visit(dependency)
        state[step_id] = 2

    for step_id in dependencies:
        visit(step_id)


def _planner_prompt(
    task: ExpertTask,
    allowed: list[dict[str, Any]],
) -> str:
    context = {
        "objective": task.objective,
        "original_user_request": task.original_user_request,
        "task_inputs": task.inputs,
        "dependency_results": {
            step_id: result.model_dump(mode="json")
            for step_id, result in task.dependency_results.items()
        },
    }
    schema = QuantSkillPlan.model_json_schema()
    return f"""
你是 AlphaOS Quant Agent 内部的 Quant Skill Planner。
你只能从下列 allowed Skills 中动态选择完成当前 Quant 任务所需的最小充分集合。
不得使用关键词 if/else 固定路由，不得建立固定 Skill 流水线，最多 3 个步骤。
步骤顺序和依赖必须由当前目标决定；简单任务只选一个 Skill。
不得调用未启用或未授权 Skill。Manager 不参与本层 Skill 选择。

若计算型 Skill 缺少 symbols、start_date 或 end_date，返回澄清计划，不得猜测。
若用户要求横截面排序但只有一个 symbol，应要求补充标的池或明确限制。
不得规划完整回测、自动交易、买卖建议，或声称未实际计算的 IC/绩效。

重要运行时约定：
- pandadata_market_data 是 Quant Agent 自动调用的受控数据工具，不是 Skill，
  不得放入 selected_skills 或 steps。
- 对 input_schema 标记 x-data-source=pandadata_market_data 的 Skill，
  只要任务已有 symbols、start_date 和 end_date，运行时会在执行 Skill 前自动获取
  market_data；不得因此要求用户补充 market_data、安装数据 Skill 或授权 PandaData。

只返回严格 JSON，不要 Markdown。selected_skills 必须与 steps 使用的 Skill 完全一致。

allowed Skills：
{json.dumps(allowed, ensure_ascii=False)}

JSON Schema：
{json.dumps(schema, ensure_ascii=False)}

任务上下文：
{json.dumps(context, ensure_ascii=False)}
""".strip()


def _planner_repair_prompt(
    task: ExpertTask,
    allowed: list[dict[str, Any]],
    raw: str,
    error: str,
) -> str:
    return f"""
上一次 Quant Skill Plan 无效。仅修复一次。
只能使用这些 Skill ID：{json.dumps([item["id"] for item in allowed])}。
最多 3 步，检查 depends_on，selected_skills 必须与 steps 完全一致。
缺少计算所需的 symbols/start_date/end_date 时返回空步骤澄清计划。
pandadata_market_data 是运行时自动调用的数据工具而不是可选 Skill。对于声明
x-data-source=pandadata_market_data 的 Skill，只要任务已有 symbols、start_date
和 end_date，就直接选择合适的已授权 Skill；不要要求 market_data、数据 Skill
或 PandaData 授权。
只返回严格 JSON。

任务：{task.objective}
验证错误：{error}
无效输出：{raw[:20_000]}
""".strip()


def _validate_runtime_clarification(
    plan: QuantSkillPlan,
    task: ExpertTask,
    allowed: list[dict[str, Any]],
) -> None:
    """Reject clarifications that contradict the declared runtime data contract."""

    if not plan.needs_clarification:
        return
    if any(
        task.inputs.get(name) in (None, "", [], {})
        for name in ("symbols", "start_date", "end_date")
    ):
        return
    has_automatic_market_data = any(
        isinstance(item.get("input_schema"), dict)
        and item["input_schema"].get("x-data-source")
        == "pandadata_market_data"
        for item in allowed
    )
    if not has_automatic_market_data:
        return
    question = (plan.clarification_question or "").lower()
    data_contract_terms = (
        "market_data",
        "pandadata",
        "市场数据",
        "数据获取",
        "数据 skill",
        "数据授权",
    )
    if any(term in question for term in data_contract_terms):
        raise ValueError(
            "Clarification contradicts the automatic PandaData runtime contract"
        )


def _extract_json(value: str) -> Any:
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)


def _dependency_claim_candidates(
    dependencies: dict[str, ExpertResult],
) -> dict[str, dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    for step_id, result in dependencies.items():
        if result.status != "completed":
            continue
        summary = result.summary.strip()
        if summary:
            claim_id = f"{step_id}:summary"
            candidates[claim_id] = {
                "claim_id": claim_id,
                "source_step": step_id,
                "text": summary[:1_000],
                "kind": "summary",
            }
        for index, risk in enumerate(result.risks[:3], start=1):
            text = str(risk).strip()
            if text:
                claim_id = f"{step_id}:risk:{index}"
                candidates[claim_id] = {
                    "claim_id": claim_id,
                    "source_step": step_id,
                    "text": text[:1_000],
                    "kind": "risk",
                }
        if len(candidates) >= 12:
            break
    return dict(list(candidates.items())[:12])


def _dependency_peer_symbols(
    dependencies: dict[str, ExpertResult],
    target_symbols: list[str],
) -> list[str]:
    targets = set(target_symbols)
    peers: list[str] = []
    for result in dependencies.values():
        if result.status != "completed" or result.agent != AgentId.RESEARCH:
            continue
        for evidence in result.evidence:
            if evidence.get("type") != "competitor_candidates":
                continue
            values = evidence.get("competitors")
            if not isinstance(values, list):
                continue
            for value in values:
                symbol = str(value).strip().upper()
                if (
                    not _A_SHARE_SYMBOL_PATTERN.fullmatch(symbol)
                    or symbol in targets
                    or symbol in peers
                ):
                    continue
                peers.append(symbol)
                if len(peers) == MAX_THESIS_PEER_CANDIDATES:
                    return peers
    return peers


def _dependency_financial_metrics(
    dependencies: dict[str, ExpertResult],
    target_symbols: list[str],
) -> dict[str, dict[str, dict[str, list[dict[str, Any]]]]]:
    grouped: dict[
        str,
        dict[str, dict[str, list[dict[str, Any]]]],
    ] = {}
    for step_id, result in dependencies.items():
        if result.status != "completed" or result.agent != AgentId.RESEARCH:
            continue
        for evidence in result.evidence:
            if evidence.get("type") != "skill_result":
                continue
            data = evidence.get("data")
            if not isinstance(data, dict):
                continue
            symbol = str(data.get("symbol") or "").strip().upper()
            if not symbol and len(target_symbols) == 1:
                symbol = target_symbols[0]
            if symbol not in target_symbols:
                continue
            by_metric = grouped.setdefault(step_id, {}).setdefault(symbol, {})
            for section in data.values():
                if not isinstance(section, dict):
                    continue
                metrics = section.get("derived_metrics")
                if not isinstance(metrics, list):
                    continue
                for item in metrics:
                    normalized = _normalize_financial_metric(item)
                    if normalized is None:
                        continue
                    observations = by_metric.setdefault(
                        normalized["metric"],
                        [],
                    )
                    key = (normalized["period"], normalized["value"])
                    if not any(
                        (existing["period"], existing["value"]) == key
                        for existing in observations
                    ):
                        observations.append(normalized)
    for by_symbol in grouped.values():
        for by_metric in by_symbol.values():
            for observations in by_metric.values():
                observations.sort(key=lambda item: _period_sort_key(item["period"]))
    return grouped


def _normalize_financial_metric(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    metric = str(value.get("metric") or "").strip()
    raw_value = value.get("value")
    period = str(value.get("period") or "").strip()
    if (
        metric not in _DOSSIER_METRICS
        or isinstance(raw_value, bool)
        or not isinstance(raw_value, (int, float))
        or not math.isfinite(float(raw_value))
        or not period
    ):
        return None
    return {
        "metric": metric,
        "value": float(raw_value),
        "period": period,
        "comparison_period": value.get("comparison_period"),
    }


def _period_sort_key(period: str) -> tuple[tuple[int, ...], str]:
    return tuple(int(item) for item in re.findall(r"\d+", period)), period


def _fundamental_validation_evidence(
    *,
    claim: dict[str, str],
    direction: Literal["positive", "negative", "risk", "neutral"],
    symbol: str,
    metrics: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if direction == "neutral":
        return []
    evidence: list[dict[str, Any]] = []
    for metric_id, observations in metrics.items():
        assessed = _assess_fundamental_metric(
            metric_id,
            observations,
            direction,
        )
        if assessed is None:
            continue
        assessment, reason, snapshot = assessed
        label = "方向一致" if assessment == "aligned" else "方向背离"
        evidence.append(
            {
                "type": "quant_thesis_validation",
                "claim_id": claim["claim_id"],
                "claim_source_step": claim["source_step"],
                "claim_text": claim["text"],
                "claim_direction": direction,
                "symbol": symbol,
                "assessment": assessment,
                "assessment_scope": "fundamental_metric_alignment",
                "metric_ids": [metric_id],
                "metric_snapshot": snapshot,
                "reason": reason,
                "text": (
                    f"{claim['text']}：{metric_id} 的财务数据校验为"
                    f"“{label}”。{reason}该结果仅说明财务方向一致性，"
                    "不证明观点成立。"
                ),
                "falsification_conditions": [
                    "若后续同口径财务指标转向相反方向，该一致性将减弱。"
                ],
                "limitations": [
                    "财务指标可能受会计口径、基数和报告期时点影响。"
                ],
                "validation_status": "historical_computation",
            }
        )
        if len(evidence) == MAX_FUNDAMENTAL_METRICS_PER_CLAIM:
            break
    return evidence


def _assess_fundamental_metric(
    metric_id: str,
    observations: list[dict[str, Any]],
    direction: Literal["positive", "negative", "risk", "neutral"],
) -> tuple[
    Literal["aligned", "divergent"],
    str,
    list[dict[str, Any]],
] | None:
    if direction == "neutral" or not observations:
        return None
    if metric_id in _GROWTH_METRICS:
        latest = observations[-1]
        value = float(latest["value"])
        if value == 0:
            return None
        health_signal = 1 if value > 0 else -1
        snapshot = [latest]
        reason = (
            f"最新报告期 {latest['period']} 的 {metric_id} 为 {value:.2%}。"
        )
    elif metric_id in _TREND_METRICS and len(observations) >= 2:
        previous, latest = observations[-2:]
        change = float(latest["value"]) - float(previous["value"])
        if change == 0:
            return None
        trend_signal = 1 if change > 0 else -1
        health_signal = (
            -trend_signal
            if metric_id in _LOWER_IS_HEALTHIER_METRICS
            else trend_signal
        )
        snapshot = [previous, latest]
        reason = (
            f"{metric_id} 从 {previous['period']} 的 "
            f"{float(previous['value']):.4f} 变为 {latest['period']} 的 "
            f"{float(latest['value']):.4f}。"
        )
    else:
        return None
    expected = 1 if direction == "positive" else -1
    assessment: Literal["aligned", "divergent"] = (
        "aligned" if health_signal == expected else "divergent"
    )
    return assessment, reason, snapshot


def _peer_relative_validation_evidence(
    *,
    claim: dict[str, str],
    direction: Literal["positive", "negative", "risk", "neutral"],
    symbol: str,
    target_metrics: list[CrossCheckResult],
    peer_symbols: list[str],
    metrics_by_symbol: dict[str, list[CrossCheckResult]],
) -> dict[str, Any] | None:
    target_return = _metric_value(target_metrics, "period_return")
    valid_peers = [
        (peer, value)
        for peer in peer_symbols
        if (
            value := _metric_value(
                metrics_by_symbol.get(peer, []),
                "period_return",
            )
        )
        is not None
    ][:MAX_THESIS_VALID_PEERS]
    if target_return is None or len(valid_peers) < 2:
        return None
    peer_values = [value for _, value in valid_peers]
    peer_median = float(median(peer_values))
    rank = cross_section_rank(target_return, peer_values, "period_return")
    relative_difference = target_return - peer_median
    if direction in {"neutral", "risk"} or relative_difference == 0:
        assessment: Literal[
            "aligned", "divergent", "mixed", "inconclusive"
        ] = "inconclusive"
        reason = "同行相对收益只能提供市场背景，无法验证该类定性观点。"
    else:
        observed = 1 if relative_difference > 0 else -1
        expected = 1 if direction == "positive" else -1
        assessment = "aligned" if observed == expected else "divergent"
        reason = (
            f"目标区间收益率为 {target_return:.2%}，同行中位数为 "
            f"{peer_median:.2%}，相对差为 {relative_difference:.2%}。"
        )
    labels = {
        "aligned": "方向一致",
        "divergent": "方向背离",
        "inconclusive": "证据不足",
    }
    return {
        "type": "quant_thesis_validation",
        "claim_id": claim["claim_id"],
        "claim_source_step": claim["source_step"],
        "claim_text": claim["text"],
        "claim_direction": direction,
        "symbol": symbol,
        "assessment": assessment,
        "assessment_scope": "peer_relative_performance",
        "metric_ids": ["period_return", rank.metric_id],
        "metric_snapshot": [
            {
                "symbol": symbol,
                "metric_id": "period_return",
                "value": target_return,
            },
            *[
                {
                    "symbol": peer,
                    "metric_id": "period_return",
                    "value": value,
                }
                for peer, value in valid_peers
            ],
        ],
        "target_return": target_return,
        "peer_median_return": peer_median,
        "percentile": rank.value,
        "peer_sample_size": len(valid_peers),
        "peer_symbols": [peer for peer, _ in valid_peers],
        "reason": reason,
        "text": (
            f"{claim['text']}：同行相对表现校验为"
            f"“{labels[assessment]}”。{reason}"
            "该结果仅描述历史相对表现，不代表未来收益。"
        ),
        "falsification_conditions": [
            "若目标与同行的相对收益方向反转，该一致性将减弱。"
        ],
        "limitations": [
            "同行样本来自 Research 候选池，未校正规模、估值或业务结构差异。"
        ],
        "validation_status": "historical_computation",
    }


def _metric_value(
    metrics: list[CrossCheckResult],
    metric_id: str,
) -> float | None:
    for item in metrics:
        if item.metric_id == metric_id and item.value is not None:
            return float(item.value)
    return None


def _thesis_selection_prompt(
    task: ExpertTask,
    candidates: dict[str, dict[str, str]],
) -> str:
    payload = [
        {
            "claim_id": claim_id,
            "source_step": claim["source_step"],
            "kind": claim["kind"],
            "text": claim["text"],
        }
        for claim_id, claim in candidates.items()
    ]
    return f"""
你是 AlphaOS Quant Agent 的观点校验选择器。
从给定候选中选择最多 3 条最值得用历史市场数据校准的观点，并标注方向：
positive、negative、risk 或 neutral。

只能原样返回候选中的 claim_id，不得生成新观点或改写 ID。
这里只选择观点，不计算指标，不判断观点真伪，不输出投资建议。
只返回符合 JSON Schema 的严格 JSON。

任务目标：
{task.objective}

候选观点：
{json.dumps(payload, ensure_ascii=False)}

JSON Schema：
{json.dumps(ThesisSelectionPlan.model_json_schema(), ensure_ascii=False)}
""".strip()


def _cross_check_results_by_symbol(
    evidence: list[dict[str, Any]],
) -> dict[str, list[CrossCheckResult]]:
    grouped: dict[str, list[CrossCheckResult]] = {}
    for item in evidence:
        if item.get("type") != "quant_cross_check":
            continue
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(
            CrossCheckResult(
                metric_id=str(item["metric_id"]),
                method=str(item["method"]),
                description=str(item["description"]),
                value=item.get("value"),
                unit=item.get("unit"),
                window=str(item.get("window") or ""),
                sample_count=int(item.get("sample_count") or 0),
                benchmark=item.get("benchmark"),
                direction=item.get("direction"),
                limitations=list(item.get("limitations") or []),
            )
        )
    return grouped


def _thesis_validation_evidence(
    *,
    claim: dict[str, str],
    direction: Literal["positive", "negative", "risk", "neutral"],
    symbol: str,
    metrics: list[CrossCheckResult],
    alignment: MarketAlignment,
) -> dict[str, Any]:
    labels = {
        "aligned": "方向一致",
        "divergent": "方向背离",
        "mixed": "窗口结论混合",
        "inconclusive": "证据不足",
    }
    metric_snapshot = [
        {
            "metric_id": item.metric_id,
            "value": item.value,
            "unit": item.unit,
            "window": item.window,
        }
        for item in metrics
        if item.metric_id in set(alignment.metric_ids)
    ]
    text = (
        f"{claim['text']}：历史市场校验为“{labels[alignment.assessment]}”。"
        f"{alignment.reason}该结果只描述历史市场一致性，不证明观点本身成立。"
    )
    return {
        "type": "quant_thesis_validation",
        "claim_id": claim["claim_id"],
        "claim_source_step": claim["source_step"],
        "claim_text": claim["text"],
        "claim_direction": direction,
        "symbol": symbol,
        "assessment": alignment.assessment,
        "assessment_scope": "historical_market_alignment",
        "metric_ids": alignment.metric_ids,
        "metric_snapshot": metric_snapshot,
        "reason": alignment.reason,
        "text": text,
        "falsification_conditions": alignment.falsification_conditions,
        "limitations": ["历史价格表现不能验证基本面因果或预测未来收益。"],
        "validation_status": "historical_computation",
    }


def _symbols(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().upper() for item in value if str(item).strip()]


def _price_rows_by_symbol(
    raw_rows: Any,
    requested_symbols: list[str],
) -> dict[str, list[PriceRow]]:
    if not isinstance(raw_rows, list):
        raise ValueError("PandaData market data must be a list")
    grouped: dict[str, list[PriceRow]] = {symbol: [] for symbol in requested_symbols}
    default_symbol = requested_symbols[0] if len(requested_symbols) == 1 else ""
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or default_symbol).strip().upper()
        date = str(row.get("trade_date") or row.get("date") or "").strip()
        if symbol not in grouped or not date:
            continue
        try:
            grouped[symbol].append(
                PriceRow(
                    date=date,
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                    high=float(row.get("high") or 0),
                    low=float(row.get("low") or 0),
                    open=float(row.get("open") or 0),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    for rows in grouped.values():
        rows.sort(key=lambda item: item.date)
    return grouped


def _validate_market_request(
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> str | None:
    if not symbols:
        return "Quant 计算需要至少一个 symbol。"
    try:
        start = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.strptime(end_date, "%Y%m%d")
    except ValueError:
        return "start_date 和 end_date 必须是 YYYYMMDD 格式的有效日期。"
    if start > end:
        return "start_date 不能晚于 end_date。"
    return None


def _requests_cross_section(user_request: str) -> bool:
    normalized = user_request.lower()
    return any(
        phrase in normalized
        for phrase in ("横截面", "cross-sectional", "cross section")
    )


def _skill_event(
    event_type: str,
    skill_id: str,
    status: SkillStatus | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"skill_id": skill_id}
    if status is not None:
        metadata["status"] = status.value
    return {"type": event_type, "skill_id": skill_id, "metadata": metadata}


def _expert_result(
    task: ExpertTask,
    plan: QuantSkillPlan,
    results: dict[str, SkillResult],
    tool_calls: list[dict[str, Any]],
    agent_events: list[dict[str, Any]],
) -> ExpertResult:
    completed = [
        result for result in results.values()
        if result.status == SkillStatus.COMPLETED
    ]
    failed = [
        result for result in results.values()
        if result.status != SkillStatus.COMPLETED
    ]
    evidence = [
        {
            "type": "skill_result",
            "skill_id": result.skill_id,
            "status": result.status.value,
            "summary": result.summary,
            "data": result.data,
            "validation_status": result.data.get(
                "validation_status",
                "unverified",
            ),
        }
        for result in results.values()
    ]
    assumptions = list(
        dict.fromkeys(
            assumption
            for result in results.values()
            for assumption in result.assumptions
        )
    )
    limitations = list(
        dict.fromkeys(
            limitation
            for result in results.values()
            for limitation in result.limitations
        )
    )
    provenance = [
        result.provenance
        for result in results.values()
        if result.provenance
    ]
    data_sources = [
        {
            "name": "PandaData",
            "symbols": _symbols(task.inputs.get("symbols")),
            "start_date": task.inputs.get("start_date"),
            "end_date": task.inputs.get("end_date"),
        }
    ] if any(call["tool"] == "pandadata_market_data" for call in tool_calls) else []
    data_sources.extend(
        {
            "name": item.get("source_repository"),
            "commit": item.get("source_commit"),
            "license": item.get("license"),
        }
        for item in provenance
    )
    statuses = {
        item["validation_status"]
        for item in evidence
        if item["status"] == SkillStatus.COMPLETED.value
    }
    validation_status = (
        next(iter(statuses))
        if len(statuses) == 1
        else "mixed_unvalidated"
    )
    status: Literal["completed", "failed"] = "failed" if failed else "completed"
    return ExpertResult(
        task_id=task.task_id,
        agent=AgentId.QUANT,
        status=status,
        summary=(
            f"Quant Agent 实际完成 {len(completed)}/{len(results)} 个 Skill 步骤。"
        ),
        evidence=evidence,
        assumptions=assumptions,
        risks=["量化因子假设和计算结果尚未完成实证有效性验证。"],
        limitations=limitations,
        recommendations=[
            "后续验证应独立设计，不能把当前结果视为交易信号。"
        ],
        tool_calls=tool_calls,
        data_sources=data_sources,
        metadata={
            "skill_plan": plan.model_dump(mode="json"),
            "actual_skills": [result.skill_id for result in results.values()],
            "skill_results": {
                step_id: result.model_dump(mode="json")
                for step_id, result in results.items()
            },
            "validation_status": validation_status,
            "provenance": provenance,
            "agent_events": agent_events,
        },
        error=(
            "; ".join(result.error or "Skill failed" for result in failed)
            if failed
            else None
        ),
    )


def _failed(
    task: ExpertTask,
    error: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> ExpertResult:
    return ExpertResult(
        task_id=task.task_id,
        agent=AgentId.QUANT,
        status="failed",
        summary="Quant Agent 未能完成量化任务。",
        limitations=[error],
        metadata=metadata or {},
        error=error,
    )
