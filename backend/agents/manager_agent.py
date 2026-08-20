"""Manager Agent for dynamic expert selection and task-graph planning."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import ExecutionPlan
from backend.core.plan_validator import (
    PlanValidationError,
    validate_execution_plan,
    validate_global_collaboration,
    validate_plan_dimensions,
)
from backend.core.policy_contracts import PolicyDecision
from backend.core.task_interpreter import TaskInterpreter
from backend.core.task_spec import TaskSpec
from backend.services.ark_client import (
    ArkClient,
    ArkClientError,
    ArkErrorKind,
    ArkJsonRequest,
)


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
        task_spec: TaskSpec | str,
        original_user_request: str | None = None,
        profile_context: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        """Plan from a validated TaskSpec.

        A string is still accepted for the deprecated in-process caller contract;
        it is normalized before being supplied to the planning prompt.
        """

        if isinstance(task_spec, str):
            request = task_spec.strip()
            normalized_spec = _legacy_task_spec(request)
        else:
            normalized_spec = TaskSpec.model_validate(task_spec)
            request = (original_user_request or normalized_spec.research_goal).strip()
        if not request:
            raise ManagerAgentError("规划请求不能为空。")

        prompt = self._planning_prompt(
            normalized_spec,
            request,
            profile_context,
        )
        try:
            candidate = self._request_plan(prompt, purpose="manager_plan")
            return self._validate(candidate, normalized_spec)
        except (
            json.JSONDecodeError,
            ValidationError,
            PlanValidationError,
            ValueError,
            ArkClientError,
        ) as exc:
            if isinstance(exc, ArkClientError) and exc.kind != ArkErrorKind.SCHEMA_VALIDATION:
                raise ManagerAgentError(str(exc)) from None
            repair_prompt = self._repair_prompt(
                request=request,
                task_spec=normalized_spec,
                profile_context=profile_context,
                invalid_response=candidate.model_dump_json() if "candidate" in locals() else "",
                error=str(exc),
            )
            try:
                repaired = self._request_plan(
                    repair_prompt,
                    purpose="manager_plan_repair",
                    attempt=2,
                )
                return self._validate(repaired, normalized_spec)
            except ArkClientError as repair_exc:
                if repair_exc.kind != ArkErrorKind.SCHEMA_VALIDATION:
                    raise ManagerAgentError(str(repair_exc)) from None
                raise ManagerAgentError(
                    "Manager Agent 在一次修复后仍未返回有效的执行计划。"
                ) from None
            except (
                json.JSONDecodeError,
                ValidationError,
                PlanValidationError,
                ValueError,
            ):
                raise ManagerAgentError(
                    "Manager Agent 在一次修复后仍未返回有效的执行计划。"
                ) from None

    def _request_plan(
        self,
        prompt: str,
        *,
        purpose: str,
        attempt: int = 1,
    ) -> ExecutionPlan:
        client = self._get_client()
        request = ArkJsonRequest[ExecutionPlan](
            prompt=prompt,
            response_model=ExecutionPlan,
            temperature=0.0,
            max_output_tokens=4_000,
            timeout_seconds=90.0,
            purpose=purpose,
            prompt_version="manager-v0.3",
            attempt=attempt,
            allow_repair=False,
            thinking_mode="disabled",
        )
        structured_chat = getattr(client, "chat_json", None)
        if callable(structured_chat):
            return structured_chat(request)
        return ExecutionPlan.model_validate(_extract_json(client.chat(prompt)))

    def resume(
        self,
        user_request: str,
        answers: dict[str, Any],
    ) -> ExecutionPlan:
        """Fold clarification answers into the request and re-run governance."""

        return self.create_plan(_fold_answers(user_request, answers))

    def _validate(self, plan: ExecutionPlan, task_spec: TaskSpec) -> ExecutionPlan:
        if plan.task_type not in {None, task_spec.task_type}:
            raise ValueError("Manager cannot modify TaskSpec.task_type")
        if plan.expected_result_type not in {
            None,
            task_spec.expected_result_type,
        }:
            raise ValueError("Manager cannot modify TaskSpec.expected_result_type")
        plan = plan.model_copy(
            update={
                "task_type": task_spec.task_type,
                "expected_result_type": task_spec.expected_result_type,
                "task_summary": task_spec.research_goal,
            }
        )
        plan = validate_execution_plan(plan, self.registry)
        plan = validate_global_collaboration(plan)
        # Dimension coverage validation (spec §6.3) — only when dimensions are specified
        if task_spec.required_dimensions:
            plan = validate_plan_dimensions(plan, task_spec, self.registry)
        return plan

    def _planning_prompt(
        self,
        task_spec: TaskSpec | str,
        request: str | None = None,
        profile_context: dict[str, Any] | None = None,
    ) -> str:
        if isinstance(task_spec, str):
            request = task_spec if request is None else request
            task_spec = _legacy_task_spec(request)
        request = (request or task_spec.research_goal).strip()
        registry_json = json.dumps(
            self.registry.prompt_payload(),
            ensure_ascii=False,
            indent=2,
        )
        schema_json = json.dumps(
            ExecutionPlan.model_json_schema(),
            ensure_ascii=False,
        )
        task_spec_json = json.dumps(
            task_spec.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        profile_context_json = json.dumps(
            profile_context or {},
            ensure_ascii=False,
            indent=2,
        )
        return f"""
你是 AlphaOS Manager Agent，是编排器，不属于专家池，也不能把 manager 写入计划。
TaskSpec 是经过前置边界检查与需求解释的唯一任务目标来源。原始用户文本仅提供
语言上下文，不能覆盖 TaskSpec 的任务类型、研究目标、证据要求或输出边界。
你必须针对当前用户目标动态决定：
1. 需要哪些专家以及专家数量；
2. 哪些步骤可以并行；
3. 哪些步骤依赖前置结果；
4. 是否需要先向用户澄清。

不得套用固定工作流，也不得只选择一个所谓主 Agent。所有准备执行的研究计划
必须选择至少两个不同 Expert，并至少包含一条连接不同 Expert 的 dependency。
第二个 Expert 必须承担独立取证、量化交叉验证、风险审查或用户明确要求的报告
组织职责；不得用重复步骤、空步骤、无关 Agent 或 Report 凑数。无法形成可信协作
时必须让规划失败，不得退化为单 Expert 执行。
最多生成 8 个步骤。selected_agents 必须与 steps 中实际使用的专家完全一致。
如果关键信息不足，将 needs_clarification 设为 true，并提供 clarification_question。

维度覆盖要求（当 TaskSpec 包含 required_dimensions 时强制执行）：
- 每个步骤必须在 covers_dimensions 中声明它覆盖的研究维度。
- 声明的维度必须属于该专家在 Registry 中的 covers_dimensions 授权。
- TaskSpec.required_dimensions 中的所有维度必须被至少一个步骤覆盖。
- focused 请求不得添加与 required_dimensions 或 optional_dimensions 无关的维度步骤。
- formal_report 不在 TaskSpec.required_dimensions 时，不得选择 Report。
- 使用 dependencies 声明带 required/optional 的类型化依赖替代 depends_on。
  例如：Risk 对上游 Research/Macro 通常声明 optional 依赖。
当 needs_clarification 为 true 时，除自然语言 clarification_question 外，还应在
clarification_options 中给出结构化选项组，便于用户快速选择：每组包含 key（英文短标识）、
title（问题）、可选 hint、multi（是否可多选）、items（候选项文本列表）与可选 default。
仅在真正缺少关键信息时才澄清；信息充分时 clarification_options 必须为空列表。
你只能选择专家和专家间依赖，绝不能选择、编排或写入专家内部的底层 Skill。
Research 和 Quant Agent 都会在各自授权 Skill 中另行动态规划；Manager 不得替它们
做这件事，plan 中不得出现 skill_id 或 a_share_stock_dossier。
根据 task_type、research_goal 和 evidence_requirements 选择最小充分专家集合，
但所有可执行研究任务的下限是两个不同 Expert。
不得修改 expected_result_type，不得扩展当前任务的研究目标，不得输出买入、卖出、
持有、目标收益或当前仓位建议。
若 task_type=personal_investment_decision，只能规划支持决策所需的事实研究与风险分析；
不得把个人资金情况转写成证券、行业或仓位建议，也不得绕过 TaskSpec 的澄清要求。
用户画像不是 Expert，不得加入 selected_agents、steps 或 AgentRegistry。
个人画像摘要只用于判断现实约束；不得生成“保守型、稳健型、激进型”等综合标签，
不得仅凭投资经验推高风险承受能力。Research、Macro、Quant 不得接收收入、支出、
债务或完整画像；应用层只会将最小脱敏摘要注入确有需要的 Risk step。

始终选择完成任务所需的最小充分专家集合：
- 不得因为某个专家已实现就选择它；
- 任一可执行计划至少选择两个不同 Expert，并建立至少一条跨 Expert 依赖；
- 价格/市场表现分析由 Research 或 Quant 获取主要证据，并动态选择另一个相关
  Expert 审查窗口、下行风险、异常或证据限制；不得用 Report 凑数；
- 独立策略风险审查由 Risk 承担主审，并动态选择能提供策略事实、市场证据或宏观
  背景的另一个 Expert；不得生成无关的陪衬步骤；
- 个股或观察名单的事件风险扫描由 Risk 承担事件扫描，并提取 symbol 或 symbols、
  start_date、end_date。另一个 Expert 只能承担与目标直接相关的公司、市场或量化
  证据核验，不得因为出现股票代码就自动扩展成全面财务分析。
  Risk 自行选择其事件风险 Skill，Manager 不得写入 Skill ID；
- 只有用户明确要求报告、摘要、备忘录、正式输出，或复杂任务确需整合多个专家时，
  才选择 report；
- report 不是默认必经节点，risk 也不是默认必经节点；
- 不得生成 research→risk→report 或其他固定模板；依赖只能来自当前目标的业务需要；
- 每个 step.inputs 必须填写该专家需要的结构化输入。市场研究应提取 symbols、
  start_date、end_date、fields，日期格式为 YYYYMMDD。symbols 必须始终是列表，
  不能写成单数 symbol；fields 为空列表时 Research 使用默认字段，否则必须至少包含
  trade_date、symbol、close、volume，绝不能使用 price、financials、
  fundamental_metrics 等概念名代替真实字段；
- 市场、财报/尽调、行业 Research 必须拆成不同步骤，不得在同一步骤混用
  symbols、财报 scope、industry 三类互斥输入契约；
- 单公司财报、基本面和尽调问题由 Research 获取主要事实，并动态选择另一个 Expert
  做风险审查或适用的量化交叉验证；应提取 symbol、period、scope、focus 和
  research_goal。只问财报时 scope=financials，全面尽调时 scope=full_dossier。
  Manager 仍然不能写入底层 Skill；
  用户未明确给出财报期时，只填写 period=latest_3_fiscal_years，不得猜测
  start_period 或 end_period；用户明确给出财报期时，两者必须填写类似 2023q4、
  2025q4 的实际值，绝不能把 YYYYqN、开始季度、结束季度等格式说明或占位符写入
  inputs；
- 财务质量或盈利质量请求必须同时选择 Research 和 Risk：Research 覆盖
  company_fundamentals 并生成结构化财务事实，Risk 覆盖 risk_assessment 并独立审查
  现金利润质量、异常趋势和证据缺口。
  Risk 必须把 Research 财务步骤声明为 required 依赖；
  不得为此自动增加 Quant、Macro 或 Report；
- 单公司同时要求成长性与估值时，必须选择 Research、Quant 和 Risk，并覆盖
  company_fundamentals、industry_competition、quantitative_cross_check 与
  risk_assessment。公司基本面 Research 分析成长事实，行业 Research 在独立步骤中
  分析同业和竞争背景；Quant 使用 thesis_validation 对上游观点做历史市场行为
  交叉验证；Risk 等待相关上游步骤终态后审查成长持续性、估值假设与证据缺口。
  市场行为交叉验证不能替代估值指标，不得把价格表现表述为估值高低。若实际证据
  不包含 PE、PB、EV、可比估值或历史分位，必须明确标记估值证据不足，不得编造
  估值数字或结论。不得为此自动增加 Macro 或 Report；
- 行业 Research 使用 industry、time_range、research_goal 和可选 focus。
  单公司行业竞争时应同时提供单数 symbol，以便查询公司行业分类和可比公司；
  不得提供 symbols 或财报 scope，也不要求市场 Research 的日期和 fields；
- 行业 Research 负责行业需求、产业链、竞争、技术成本和估值预期研究。Macro 负责
  宏观、政策、周期和流动性；只有当前目标确实同时需要两者时才选择两个专家。若两项
  分析互不依赖，应将两个 depends_on 都留空以并行执行，不得写成固定流水线；
- Quant 因子实际计算同样必须提取 symbols、start_date、end_date；缺少任一项时
  必须要求澄清，不能猜测。因子创意任务不要求先获取市场数据；
- 因子创意任务设置 analysis_mode=skill_research，inputs 只能使用 Registry
  允许的 Quant 字段，不得在 Quant inputs 中写入 research_goal；
  因子创意任务的 covers_dimensions 必须为空列表；
- Quant 的普通历史收益、波动、回撤、成交量与横截面交叉验证，inputs 必须设置
  analysis_mode=historical_cross_check，并提取 symbols、start_date、end_date；
- 当综合研究需要用历史市场证据校准 Research 或 Macro 的上游结论时，Quant inputs
  设置 analysis_mode=thesis_validation，并对需要读取的上游步骤声明 dependency；
  该模式只评估历史市场一致性，不得声称价格表现证明基本面或预测未来收益；
  明确的因子创意或 R020 研究设置 analysis_mode=skill_research，由 Quant 自行动态
  选择授权 Skill。analysis_mode 只描述分析目标，不得写入任何 Skill ID；
- 不得因为 Quant 可用就机械加入所有任务。Quant 作为主分析时仍须动态选择一个
  与目标相关的协作 Expert 并建立跨 Expert 依赖；Report 只在用户明确要求正式输出
  时选择，不能作为通用第二 Expert。
- 当任务明确要求评估经济周期、利率、流动性、政策或行业宏观环境时，可以选择
  macro；Macro 使用 PandaData 自行规划内部宏观指标，Manager 不得选择指标或 API；
- 纯历史收益、因子计算、股票技术指标或公司财务任务不得自动追加 macro；
- Macro 输入应提取 industry、time_range、research_goal。用户给出明确历史区间时
  同时填写 start_date、end_date；只有前瞻期限时不猜测历史日期，由 Macro 使用
  截至执行日的最近 24 个月数据；
- 不得机械追加 macro。Macro 与其他专家的依赖只能来自当前任务的真实业务需要；
  Macro 作为主分析时仍须选择一个相关协作 Expert 并建立跨 Expert 依赖。

可用专家注册表：
{registry_json}

只返回一个严格符合下列 JSON Schema 的 JSON 对象，不要 Markdown、解释或代码围栏：
{schema_json}

已验证 TaskSpec：
{task_spec_json}

原始用户文本（仅作上下文）：
{request}

个人任务最小画像摘要（非个人任务为空对象；null 表示未知，不得猜测）：
{profile_context_json}
""".strip()

    def _repair_prompt(
        self,
        request: str,
        task_spec: TaskSpec,
        profile_context: dict[str, Any] | None,
        invalid_response: str,
        error: str,
    ) -> str:
        schema_json = json.dumps(
            ExecutionPlan.model_json_schema(),
            ensure_ascii=False,
        )
        registry_json = json.dumps(
            self.registry.prompt_payload(),
            ensure_ascii=False,
        )
        task_spec_json = json.dumps(
            task_spec.model_dump(mode="json"),
            ensure_ascii=False,
        )
        profile_context_json = json.dumps(
            profile_context or {},
            ensure_ascii=False,
        )
        return f"""
你上一次为 AlphaOS 生成的计划无效。仅进行这一次修复。
保持用户目标不变，修正 JSON 语法、字段类型和任务图约束。
只返回严格 JSON，不要 Markdown 或解释。

用户请求：
{request}

不可覆盖的 TaskSpec：
{task_spec_json}

最小用户画像摘要（不得广播给 Research、Macro 或 Quant）：
{profile_context_json}

验证错误：
{error}

无效响应：
{invalid_response[:20_000]}

目标 JSON Schema：
{schema_json}

当前唯一可用的专家注册表（不得使用列表外或 enabled=false 的专家）：
{registry_json}

Agent 输入契约：
- 所有准备执行的研究计划必须选择至少两个不同 Expert，并包含至少一条跨 Expert
  dependency；不得用重复、空白、无关或 Report 步骤凑数。无法形成可信协作时停止
  规划，不得返回单 Expert 计划；
- 市场、财报/尽调、行业 Research 必须拆成不同步骤，不得在同一步骤混用
  symbols、财报 scope、industry 三类互斥输入契约；
- 市场 Research 必须使用 symbols 列表、YYYYMMDD 的 start_date/end_date；fields
  为空列表或至少包含 trade_date、symbol、close、volume；
- 财报/尽调 Research 才能使用 symbol，并必须提供 financials、financial_risk
  或 full_dossier scope；
- 行业 Research 必须使用非空 industry；time_range、research_goal、focus 如提供
  必须为非空字符串；单公司行业竞争时应同时提供单数 symbol；不得提供 symbols 或
  财报 scope；
- Macro 必须使用非空 industry、time_range、research_goal；若提供历史区间必须同时
  给出合法 YYYYMMDD 的 start_date 与 end_date 且不倒置，不得只给其一；纯个股价格、
  财务或因子任务不需要 macro，不要为修复契约而保留缺输入的 macro，可直接移除；
- Quant 因子创意任务使用 analysis_mode=skill_research；
  不得在 Quant inputs 中写入 research_goal；
  因子创意任务的 covers_dimensions 必须为空列表；
- 个股/观察名单事件风险扫描的 Risk 使用 symbol 或 symbols，并可使用
  start_date、end_date；不得为此自动增加 Research 或财务 scope；
- 财务质量或盈利质量请求必须同时选择 Research 和 Risk；Risk 必须把 Research
  财务步骤声明为 required 依赖，不得把该审查改成独立事件风险扫描；
- 单公司成长性与估值复合请求必须选择 Research、Quant 和 Risk，分别覆盖公司
  基本面、行业竞争、量化交叉验证和风险评估；公司与行业 Research 必须拆成符合
  各自输入契约的步骤。市场行为交叉验证不能替代估值指标，不得把价格表现表述为
  估值高低；缺少 PE、PB、EV、可比估值或历史分位时必须明确标记证据不足；
- 当 TaskSpec 包含 required_dimensions 时，每个步骤的 covers_dimensions 只能使用
  该专家在 Registry 中授权的维度；focused 请求的步骤只能覆盖
  required_dimensions 或 optional_dimensions 中的维度，协作复核步骤也可以将
  covers_dimensions 留为空列表；
- Report 必须声明至少一个上游 depends_on；
- 不要为了修复契约而增加不需要的专家或改成固定流程。
""".strip()

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


def _legacy_task_spec(request: str) -> TaskSpec:
    """Normalize the old string API without allowing it to bypass TaskSpec."""

    allowed = PolicyDecision(
        decision="allowed_research",
        allowed=True,
        domain="quant_investment_research",
        policy_tags=["legacy_manager_call"],
        reason="Legacy Manager caller is normalized before planning.",
    )
    return TaskInterpreter().interpret(request, allowed)


def _fold_answers(user_request: str, answers: dict[str, Any]) -> str:
    """Append the user's clarification answers to the original request text."""

    request = user_request.strip()
    pairs: list[str] = []
    for key, value in answers.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (list, tuple)):
            rendered = "、".join(str(item) for item in value if item != "")
        else:
            rendered = str(value)
        if rendered:
            pairs.append(f"{key}={rendered}")
    if not pairs:
        return request
    return f"{request}\n\n用户澄清：" + "；".join(pairs) + "。"
