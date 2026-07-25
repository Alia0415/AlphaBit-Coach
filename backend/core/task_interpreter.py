"""Natural-language normalization into a research TaskSpec.

Uses LLM semantic analysis for scope and dimension extraction (spec §5.2),
with deterministic fallback for robustness.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.core.policy_contracts import PolicyDecision
from backend.core.task_spec import (
    ResearchDimension,
    RequestScope,
    SubjectType,
    TaskSpec,
    TaskType,
    _COMPREHENSIVE_DEFAULTS,
)

logger = logging.getLogger(__name__)


_SYMBOL = re.compile(r"(?<!\d)(\d{6}\.(?:SH|SZ))(?![A-Z])", re.IGNORECASE)
_YEAR = re.compile(r"(?<!\d)(20\d{2})\s*年?")
_RELATIVE_TIME = re.compile(r"(最近|过去|未来)\s*([一二三四五六七八九十\d]+)\s*(年|个月|月|季度)")
_COMPANY_AFTER_ANALYZE = re.compile(
    r"(?:分析|研究|评估|对比|比较)\s*([^，。；,.]{2,20}?)(?=最近|过去|未来|在|的财|财务|财报|公司|与|和|、|，|。|$)"
)

_EVIDENCE_REQUIREMENTS = {
    "personal_investment_decision": [
        "资金期限与流动性约束",
        "应急资金与收入支出情况",
        "亏损承受边界",
        "当前持仓与债务约束",
    ],
    "market_research": ["历史市场指标", "数据范围", "风险与限制"],
    "company_research": ["财务事实", "盈利质量与异常信号", "数据缺失项"],
    "factor_research": ["因子定义与参数", "覆盖率与缺失值", "验证状态"],
    "historical_analysis": ["历史样本范围", "计算规则", "成本假设"],
    "risk_review": ["主要风险源", "被挑战的假设", "缺失证据"],
    "comparison": ["统一比较口径", "各对象证据", "差异与限制"],
    "formal_report": ["可追溯事实", "验证状态", "来源与限制"],
}


# ---------------------------------------------------------------------------
# LLM dimension analysis model (spec §5.2)
# ---------------------------------------------------------------------------


class _DimensionAnalysis(BaseModel):
    """LLM output for semantic dimension classification."""

    request_scope: RequestScope
    required_dimensions: list[ResearchDimension] = Field(min_length=1)
    optional_dimensions: list[ResearchDimension] = Field(default_factory=list)
    reasoning: str = ""


_DIMENSION_PROMPT_TEMPLATE = """你是 AlphaOS TaskInterpreter 的维度分析器。
根据用户输入判断研究范围和所需研究维度。

可用维度（受控枚举）：
- company_fundamentals: 公司基本面（财报、业绩、股东等）
- industry_competition: 行业竞争（行业格局、竞品比较）
- macro_environment: 宏观环境（经济周期、利率、政策）
- quantitative_cross_check: 量化交叉验证（收益、波动、回撤、相对排名）
- risk_assessment: 风险评估（事件风险、质押、异常交易）
- formal_report: 正式报告（仅用户明确要求研报时）

判定规则：
- "分析某公司""全面研究""从多角度评估"等宽泛单公司请求→ comprehensive，包含前五个维度
- "看波动回撤""技术分析""历史表现"→ focused，仅 quantitative_cross_check
- "财报分析""财务质量""基本面"→ focused，仅 company_fundamentals
- "行业研究""竞争格局"→ focused，仅 industry_competition
- "事件风险""风险扫描"→ focused，仅 risk_assessment
- "宏观分析""经济环境"→ focused，仅 macro_environment
- "生成研报""正式报告"→ 用户要求的维度加 formal_report
- 只输出维度，不输出专家名称

只返回严格 JSON：
{{"request_scope": "...", "required_dimensions": [...], "optional_dimensions": [...], "reasoning": "..."}}

用户输入：
{user_input}
"""


class TaskInterpreter:
    """Interpret intent without choosing experts, Skills, or conclusions.

    Uses LLM for semantic dimension extraction when available (spec §5.2),
    with deterministic fallback for robustness.
    """

    def __init__(self, ark_client: Any | None = None) -> None:
        self._ark_client = ark_client

    def interpret(self, prompt: str, policy: PolicyDecision) -> TaskSpec:
        if not policy.allowed:
            raise ValueError("Blocked policy decisions cannot be interpreted as research")
        text = " ".join(prompt.strip().split())
        lowered = text.lower()
        task_type = _task_type(lowered)
        subject_type = _subject_type(lowered, task_type)
        subjects = _subjects(text, subject_type)
        symbols = [match.upper() for match in _SYMBOL.findall(text)]
        start_date, end_date, time_description = _time_range(text)
        missing_fields: list[str] = []
        clarification: str | None = None

        if task_type == "personal_investment_decision":
            missing_fields.extend(_missing_personal_decision_fields(lowered))
        else:
            is_factor_computation = task_type == "factor_research" and any(
                marker in lowered for marker in ("计算", "r020", "因子值", "排名")
            )
            if is_factor_computation and not symbols:
                missing_fields.append("subjects")
            if is_factor_computation and not (start_date and end_date):
                missing_fields.append("date_range")
            if subject_type == "company" and not subjects:
                missing_fields.append("company_or_stock_code")
            if task_type == "comparison" and len(subjects) < 2:
                missing_fields.append("comparison_subjects")

        if missing_fields:
            if task_type == "personal_investment_decision":
                clarification = (
                    "这是个人投资决策。关键信息不足时不会直接给出配置方案，"
                    "请补充投资期限、应急资金、稳定收入与日常支出，以及可承受的"
                    "最大亏损或回撤范围。"
                )
            elif "company_or_stock_code" in missing_fields:
                clarification = "请提供需要研究的公司名称或股票代码。"
            elif "comparison_subjects" in missing_fields:
                clarification = "请明确至少两个需要比较的研究对象。"
            elif {"subjects", "date_range"} <= set(missing_fields):
                clarification = "请提供因子计算的股票代码列表和明确日期范围。"
            elif "subjects" in missing_fields:
                clarification = "请提供因子计算的股票代码列表。"
            else:
                clarification = "请提供因子计算的明确日期范围。"

        defaulted_fields: list[str] = []
        assumptions: list[str] = []
        if (
            task_type != "personal_investment_decision"
            and not time_description
            and not (start_date and end_date)
        ):
            defaulted_fields.append("time_range=latest_available_research_window")
            assumptions.append("未指定时间范围时，使用专家能力允许的最近可用研究窗口。")
        defaulted_fields.append("requested_validation_level=research_draft")

        execution_decision: Literal[
            "execute",
            "execute_with_defaults",
            "clarify",
        ] = (
            "clarify"
            if missing_fields
            else "execute_with_defaults"
            if defaulted_fields
            else "execute"
        )

        # --- Dimension extraction (spec §5.2) ---
        request_scope: RequestScope = "focused"
        required_dimensions: list[ResearchDimension] = []
        optional_dimensions: list[ResearchDimension] = []
        dimension_defaulted = False

        if execution_decision != "clarify":
            # Try LLM semantic analysis first
            llm_result = self._try_llm_dimensions(text)
            if llm_result is not None:
                request_scope = llm_result.request_scope
                required_dimensions = llm_result.required_dimensions
                optional_dimensions = llm_result.optional_dimensions
            else:
                # Deterministic fallback (spec §5.2 conservative defaults)
                request_scope, required_dimensions = _deterministic_dimensions(
                    task_type, subject_type, lowered
                )
                if required_dimensions:
                    dimension_defaulted = True

        if dimension_defaulted:
            defaulted_fields.append("dimensions=deterministic_fallback")

        return TaskSpec(
            task_type=task_type,
            subject_type=subject_type,
            subjects=subjects,
            market="A-share" if any(_SYMBOL.fullmatch(item) for item in subjects) else None,
            research_goal=text,
            expected_result_type=task_type,
            start_date=start_date,
            end_date=end_date,
            time_range_description=time_description,
            evidence_requirements=list(_EVIDENCE_REQUIREMENTS[task_type]),
            requested_validation_level="research_draft",
            assumptions=assumptions,
            defaulted_fields=defaulted_fields,
            missing_fields=missing_fields,
            execution_decision=execution_decision,
            clarification_question=clarification,
            request_scope=request_scope,
            required_dimensions=required_dimensions,
            optional_dimensions=optional_dimensions,
        )

    def _try_llm_dimensions(self, text: str) -> _DimensionAnalysis | None:
        """Attempt LLM-based semantic dimension extraction.

        Returns None if LLM is unavailable or fails (triggers deterministic fallback).
        """
        if self._ark_client is None:
            return None

        try:
            from backend.services.ark_client import ArkJsonRequest

            prompt = _DIMENSION_PROMPT_TEMPLATE.format(user_input=text)
            request = ArkJsonRequest(
                prompt=prompt,
                response_model=_DimensionAnalysis,
                temperature=0.0,
                purpose="dimension_analysis",
                prompt_version="1.0",
            )
            result = self._ark_client.chat_json(request)
            # Validate: required_dimensions must be non-empty and deduplicated
            if not result.required_dimensions:
                return None
            if len(result.required_dimensions) != len(set(result.required_dimensions)):
                # Deduplicate
                result.required_dimensions = list(dict.fromkeys(result.required_dimensions))
            return result
        except Exception as exc:
            logger.warning("LLM dimension extraction failed, using fallback: %s", str(exc)[:100])
            return None


def _task_type(text: str) -> TaskType:
    if _is_personal_investment_decision(text):
        return "personal_investment_decision"
    if any(marker in text for marker in ("正式报告", "研究报告", "备忘录")):
        return "formal_report"
    if any(marker in text for marker in ("对比", "比较", " vs ", " versus ")):
        return "comparison"
    if any(marker in text for marker in ("因子", "r020", "ic检验", "ic ", "factor")):
        return "factor_research"
    event_risk_markers = (
        "事件风险",
        "风险扫描",
        "风险预警",
        "公告风险",
        "观察名单风险",
    )
    if any(marker in text for marker in event_risk_markers):
        return "risk_review"
    company_markers = ("财务", "财报", "现金流", "盈利质量", "审计意见", "公司", "个股")
    if any(marker in text for marker in company_markers):
        return "company_research"
    if _SYMBOL.search(text) and not any(
        marker in text
        for marker in (
            "价格",
            "股价",
            "行情",
            "波动",
            "回撤",
            "成交量",
            "收益",
            "表现",
        )
    ):
        return "company_research"
    risk_markers = ("风险审查", "评估风险", "失效风险", "主要风险", "风险分析")
    if any(marker in text for marker in risk_markers) and not _SYMBOL.search(text):
        return "risk_review"
    if any(marker in text for marker in ("历史计算", "历史表现", "历史收益", "回测")):
        return "historical_analysis"
    return "market_research"


def _subject_type(text: str, task_type: TaskType) -> SubjectType:
    if task_type == "personal_investment_decision":
        return "personal_finance"
    if task_type == "factor_research":
        return "factor"
    if task_type == "company_research" or any(
        marker in text for marker in ("这家公司", "该公司")
    ):
        return "company"
    if "行业" in text:
        return "industry"
    if any(marker in text for marker in ("宏观", "利率", "流动性", "经济周期", "政策")):
        return "macro_theme"
    if task_type == "risk_review":
        return "research_thesis"
    return "market"


def _subjects(text: str, subject_type: SubjectType) -> list[str]:
    symbols = [match.upper() for match in _SYMBOL.findall(text)]
    if subject_type == "factor":
        factors = re.findall(r"\bR\d{3}\b", text, flags=re.IGNORECASE)
        return list(
            dict.fromkeys([*(item.upper() for item in factors), *symbols])
        )
    if symbols:
        return list(dict.fromkeys(symbols))
    if subject_type == "industry":
        match = re.search(r"([^，。；,\s]{2,16}行业)", text)
        if not match:
            return []
        candidate = re.sub(r"^(?:请|帮我)?(?:分析|研究|评估)", "", match.group(1))
        return [candidate]
    if subject_type == "macro_theme":
        themes = [
            marker
            for marker in ("经济周期", "利率", "流动性", "政策", "宏观环境")
            if marker in text
        ]
        return themes
    if subject_type == "company":
        match = _COMPANY_AFTER_ANALYZE.search(text)
        if match:
            candidate = match.group(1).strip()
            if candidate not in {"这只股票", "该公司", "一家公司", "某公司"}:
                return [candidate]
    if subject_type == "research_thesis":
        return [text]
    return []


def _time_range(text: str) -> tuple[str | None, str | None, str | None]:
    years = [int(year) for year in _YEAR.findall(text)]
    if years:
        start_year, end_year = min(years), max(years)
        return (
            f"{start_year}0101",
            f"{end_year}1231",
            f"{start_year} 年" if start_year == end_year else f"{start_year} 至 {end_year} 年",
        )
    relative = _RELATIVE_TIME.search(text)
    if relative:
        return None, None, "".join(relative.groups())
    if "今年" in text:
        year = datetime.now().year
        return f"{year}0101", f"{year}1231", f"{year} 年"
    return None, None, None


def _is_personal_investment_decision(text: str) -> bool:
    personal_context = any(
        marker in text
        for marker in (
            "我有",
            "我的资金",
            "我的收入",
            "我的存款",
            "本人",
            "家庭资金",
            "家庭资产",
        )
    )
    allocation_request = any(
        marker in text
        for marker in (
            "想投资",
            "怎么安排",
            "如何安排",
            "怎么配置",
            "如何配置",
            "资产配置",
            "投资计划",
            "应该怎么投",
        )
    )
    return personal_context and allocation_request


def _missing_personal_decision_fields(text: str) -> list[str]:
    missing: list[str] = []
    if not any(
        marker in text
        for marker in ("投资期限", "资金期限", "持有期限", "长期", "短期", "个月", "年")
    ):
        missing.append("investment_horizon")
    if not any(marker in text for marker in ("应急资金", "应急金", "备用金")):
        missing.append("emergency_fund")
    has_income = any(marker in text for marker in ("收入", "工资", "现金流入"))
    has_expenses = any(marker in text for marker in ("支出", "开销", "月供", "现金流出"))
    if not (has_income and has_expenses):
        missing.append("income_and_expenses")
    if not any(
        marker in text
        for marker in ("亏损", "回撤", "风险承受", "最大损失", "损失承受")
    ):
        missing.append("loss_tolerance")
    return missing


# ---------------------------------------------------------------------------
# Deterministic dimension fallback (spec §5.2)
# ---------------------------------------------------------------------------

# Focused markers → single dimension
_FOCUSED_QUANTITATIVE = (
    "波动", "回撤", "收益", "表现", "涨跌", "成交量", "技术分析", "历史",
    "价格", "股价", "行情",
)
_FOCUSED_FUNDAMENTALS = (
    "财务", "财报", "现金流", "盈利质量", "审计意见", "基本面", "利润", "营收",
)
_FOCUSED_INDUSTRY = ("行业", "竞争格局", "竞品", "产业链", "同业")
_FOCUSED_RISK = ("事件风险", "风险扫描", "风险预警", "质押", "解禁")
_FOCUSED_MACRO = ("宏观", "经济周期", "利率", "流动性", "政策")
_FOCUSED_REPORT = ("正式报告", "研究报告", "备忘录", "研报")

# Comprehensive triggers
_COMPREHENSIVE_TRIGGERS = (
    "全面", "综合", "深度分析", "全方位", "多角度", "整体评估",
)


def _deterministic_dimensions(
    task_type: TaskType,
    subject_type: SubjectType,
    lowered: str,
) -> tuple[RequestScope, list[ResearchDimension]]:
    """Conservative deterministic dimension assignment (spec §5.2 fallback).

    Single-company broad analysis → comprehensive.
    Specific indicator requests → focused with minimal dimensions.
    """
    # Personal investment decisions don't get research dimensions
    if task_type == "personal_investment_decision":
        return "focused", []

    # Formal report
    if task_type == "formal_report":
        dims: list[ResearchDimension] = list(_COMPREHENSIVE_DEFAULTS)
        dims.append("formal_report")
        return "comprehensive", dims

    # Check for explicit comprehensive triggers
    is_comprehensive_trigger = any(t in lowered for t in _COMPREHENSIVE_TRIGGERS)

    # Company research with broad/vague phrasing → comprehensive
    if subject_type == "company" and task_type == "company_research":
        # If it's a broad company request (just "分析X" without specific focus)
        has_specific_focus = any(
            any(m in lowered for m in markers)
            for markers in (
                _FOCUSED_QUANTITATIVE,
                _FOCUSED_FUNDAMENTALS,
                _FOCUSED_RISK,
                _FOCUSED_MACRO,
            )
        )
        if is_comprehensive_trigger or not has_specific_focus:
            return "comprehensive", list(_COMPREHENSIVE_DEFAULTS)

    # Factor research doesn't map well to research dimensions
    if task_type == "factor_research":
        return "focused", ["quantitative_cross_check"]

    # Historical analysis / market research with quantitative markers
    if task_type == "historical_analysis" or (
        task_type == "market_research"
        and any(m in lowered for m in _FOCUSED_QUANTITATIVE)
    ):
        return "focused", ["quantitative_cross_check"]

    # Risk review
    if task_type == "risk_review":
        return "focused", ["risk_assessment"]

    # Focused dimension detection by markers
    if any(m in lowered for m in _FOCUSED_FUNDAMENTALS):
        return "focused", ["company_fundamentals"]
    if any(m in lowered for m in _FOCUSED_INDUSTRY):
        return "focused", ["industry_competition"]
    if any(m in lowered for m in _FOCUSED_MACRO):
        return "focused", ["macro_environment"]
    if any(m in lowered for m in _FOCUSED_RISK):
        return "focused", ["risk_assessment"]
    if any(m in lowered for m in _FOCUSED_QUANTITATIVE):
        return "focused", ["quantitative_cross_check"]

    # Market research with company subject → comprehensive
    if subject_type == "company" and is_comprehensive_trigger:
        return "comprehensive", list(_COMPREHENSIVE_DEFAULTS)

    # Default: market_research without specific markers → no dimensions
    # (Manager will still route correctly via existing logic)
    return "focused", []
