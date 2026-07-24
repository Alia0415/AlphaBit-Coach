"""Manager Agent for dynamic expert selection and task-graph planning."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import ExecutionPlan
from backend.core.plan_validator import PlanValidationError, validate_execution_plan
from backend.core.user_profile import UserInvestmentProfile
from backend.services.ark_client import ArkClient, ArkClientError


class ManagerAgentError(RuntimeError):
    """Raised when the Manager cannot produce a valid execution plan."""


class ManagerAgent:
    """Select experts and construct a task graph; never aggregate results."""

    def __init__(
        self,
        client: ArkClient | None = None,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._client = client
        self.registry = registry or AgentRegistry()

    def create_plan(
        self,
        user_request: str,
        user_profile: UserInvestmentProfile | None = None,
    ) -> ExecutionPlan:
        request = user_request.strip()
        if not request:
            raise ManagerAgentError("规划请求不能为空。")

        profile_context = self._profile_context(user_profile)
        prompt = self._planning_prompt(request, profile_context)
        try:
            raw_response = self._get_client().chat(prompt)
        except ArkClientError as exc:
            raise ManagerAgentError(str(exc)) from None

        try:
            return self._parse_and_validate(raw_response)
        except (json.JSONDecodeError, ValidationError, PlanValidationError, ValueError) as exc:
            repair_prompt = self._repair_prompt(
                request=request,
                invalid_response=raw_response,
                error=str(exc),
                profile_context=profile_context,
            )
            try:
                repaired_response = self._get_client().chat(repair_prompt)
                return self._parse_and_validate(repaired_response)
            except ArkClientError as repair_exc:
                raise ManagerAgentError(str(repair_exc)) from None
            except (
                json.JSONDecodeError,
                ValidationError,
                PlanValidationError,
                ValueError,
            ):
                raise ManagerAgentError(
                    "Manager Agent 在一次修复后仍未返回有效的执行计划。"
                ) from None

    def _parse_and_validate(self, raw_response: str) -> ExecutionPlan:
        payload = _extract_json(raw_response)
        plan = ExecutionPlan.model_validate(payload)
        return validate_execution_plan(plan, self.registry)

    def _planning_prompt(
        self,
        request: str,
        profile_context: str | None = None,
    ) -> str:
        profile_context = profile_context or self._profile_context(None)
        registry_json = json.dumps(
            self.registry.prompt_payload(),
            ensure_ascii=False,
            indent=2,
        )
        schema_json = json.dumps(
            ExecutionPlan.model_json_schema(),
            ensure_ascii=False,
        )
        return f"""
你是 AlphaOS Manager Agent，是编排器，不属于专家池，也不能把 manager 写入计划。
你必须针对当前用户目标动态决定：
1. 需要哪些专家以及专家数量；
2. 哪些步骤可以并行；
3. 哪些步骤依赖前置结果；
4. 是否需要先向用户澄清。

不得套用固定工作流，不得只选择一个所谓主 Agent。简单目标可以只选一个专家；
复杂目标应按实际需要构建依赖图。depends_on 为空表示可立即并行执行。
最多生成 8 个步骤。selected_agents 必须与 steps 中实际使用的专家完全一致。
如果关键信息不足，将 needs_clarification 设为 true，并提供 clarification_question。
你只能选择专家和专家间依赖，绝不能选择、编排或写入专家内部的底层 Skill。
Research 和 Quant Agent 都会在各自授权 Skill 中另行动态规划；Manager 不得替它们
做这件事，plan 中不得出现 skill_id 或 a_share_stock_dossier。

始终选择完成任务所需的最小充分专家集合：
- 不得因为某个专家已实现就选择它；
- 价格/市场表现分析通常只需要 research，不得自动追加 risk 或 report；
- 独立策略风险审查可以只使用 risk，不得强制先调用 research；
- 只有用户明确要求报告、摘要、备忘录、正式输出，或复杂任务确需整合多个专家时，
  才选择 report；
- report 不是默认必经节点，risk 也不是默认必经节点；
- 不得生成 research→risk→report 或其他固定模板；依赖只能来自当前目标的业务需要；
- 每个 step.inputs 必须填写该专家需要的结构化输入。市场研究应提取 symbols、
  start_date、end_date、fields，日期格式为 YYYYMMDD。symbols 必须始终是列表，
  不能写成单数 symbol；fields 为空列表时 Research 使用默认字段，否则必须至少包含
  trade_date、symbol、close、volume，绝不能使用 price、financials、
  fundamental_metrics 等概念名代替真实字段；
- 单公司财报、基本面、尽调和财务风险问题只选择 research；应提取 symbol、
  period、scope、focus 和 research_goal。只问财报时 scope=financials，全面尽调时
  scope=full_dossier。Manager 仍然只能选择 research，绝不能写入底层 Skill；
- 行业 Research 使用 industry、time_range、research_goal 和可选 focus；不得同时
  提供 symbol、symbols 或财报 scope，也不要求市场 Research 的日期和 fields；
- 行业 Research 负责行业需求、产业链、竞争、技术成本和估值预期研究。Macro 负责
  宏观、政策、周期和流动性；只有当前目标确实同时需要两者时才选择两个专家。若两项
  分析互不依赖，应将两个 depends_on 都留空以并行执行，不得写成固定流水线；
- Quant 因子实际计算同样必须提取 symbols、start_date、end_date；缺少任一项时
  必须要求澄清，不能猜测。因子创意任务不要求先获取市场数据；
- 不得因为 Quant 可用就强制加入所有任务，也不得为 Quant 任务自动追加 risk 或
  report。只有用户明确要求风险审查或报告时才选相应专家并建立业务依赖。
- 当任务明确要求评估经济周期、利率、流动性、政策或行业宏观环境时，可以选择
  macro；Macro 使用 PandaData 自行规划内部宏观指标，Manager 不得选择指标或 API；
- 纯历史收益、因子计算、股票技术指标或公司财务任务不得自动追加 macro；
- Macro 输入应提取 industry、time_range、research_goal。用户给出明确历史区间时
  同时填写 start_date、end_date；只有前瞻期限时不猜测历史日期，由 Macro 使用
  截至执行日的最近 24 个月数据；
- 不得自动追加 macro。Macro 与其他专家的依赖只能来自当前任务的真实业务需要。

用户画像使用边界：
- 用户画像只是经 Pydantic 验证的用户事实，不是 Expert Agent。不得创建 profile
  Agent，不得把画像加入 selected_agents、steps 或固定工作流；
- 只能使用画像中明确提供的事实和确定性派生指标，任何 null 都表示未知，不得猜测或
  按零处理；
- 最大可接受亏损只反映风险意愿。风险承受能力相关事实包括每月结余、应急资金月数、
  债务负担、未来大额支出、期限、流动性和已知持仓集中度，两者不得混为一谈；
- 不得根据画像生成“激进型、稳健型、保守型”等综合标签，也不得仅凭投资经验推高
  风险承受判断；
- 如果当前任务与缺失画像字段无关，照常规划。如果个人决策确实依赖缺失信息，只询问
  当前决策所需的一项或一组紧密相关信息，不得重新启动整套画像问答；此时将
  needs_clarification 设为 true，并让 clarification_question 以“画像信息不足：”开头；
- 本阶段不得规划或生成个性化买入、卖出或资产配置建议。画像只用于理解研究目标、
  约束、证据边界和是否缺少关键信息。

当前用户画像（服务端验证后的 JSON；derived_metrics 为确定性计算结果）：
{profile_context}

可用专家注册表：
{registry_json}

只返回一个严格符合下列 JSON Schema 的 JSON 对象，不要 Markdown、解释或代码围栏：
{schema_json}

用户请求：
{request}
""".strip()

    def _repair_prompt(
        self,
        request: str,
        invalid_response: str,
        error: str,
        profile_context: str,
    ) -> str:
        schema_json = json.dumps(
            ExecutionPlan.model_json_schema(),
            ensure_ascii=False,
        )
        registry_json = json.dumps(
            self.registry.prompt_payload(),
            ensure_ascii=False,
        )
        return f"""
你上一次为 AlphaOS 生成的计划无效。仅进行这一次修复。
保持用户目标不变，修正 JSON 语法、字段类型和任务图约束。
只返回严格 JSON，不要 Markdown 或解释。

用户请求：
{request}

验证错误：
{error}

无效响应：
{invalid_response[:20_000]}

目标 JSON Schema：
{schema_json}

当前唯一可用的专家注册表（不得使用列表外或 enabled=false 的专家）：
{registry_json}

当前用户画像（仍须遵守未知值不猜测、不生成风险标签、不生成买卖或配置建议）：
{profile_context}

Agent 输入契约：
- 市场 Research 必须使用 symbols 列表、YYYYMMDD 的 start_date/end_date；fields
  为空列表或至少包含 trade_date、symbol、close、volume；
- 财报/尽调 Research 才能使用 symbol，并必须提供 financials、financial_risk
  或 full_dossier scope；
- 行业 Research 必须使用非空 industry；time_range、research_goal、focus 如提供
  必须为非空字符串；不得同时提供 symbol、symbols 或财报 scope；
- Report 必须声明至少一个上游 depends_on；
- 不要为了修复契约而增加不需要的专家或改成固定流程。
""".strip()

    @staticmethod
    def _profile_context(user_profile: UserInvestmentProfile | None) -> str:
        if user_profile is None:
            return json.dumps(
                {
                    "available": False,
                    "message": "本次请求未提供用户画像快照。",
                },
                ensure_ascii=False,
            )
        payload = user_profile.model_dump(mode="json", exclude_computed_fields=True)
        payload["derived_metrics"] = {
            "monthly_surplus_cny": user_profile.monthly_surplus_cny,
            "emergency_fund_months": user_profile.emergency_fund_months,
            "debt_payment_ratio": user_profile.debt_payment_ratio,
            "known_asset_concentration": user_profile.known_asset_concentration,
            "profile_completeness": user_profile.profile_completeness,
        }
        payload["missing_fields"] = user_profile.missing_fields()
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _get_client(self) -> ArkClient:
        if self._client is None:
            self._client = ArkClient()
        return self._client


def _extract_json(value: str) -> Any:
    """Accept strict JSON and tolerate a single surrounding code fence."""

    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)
