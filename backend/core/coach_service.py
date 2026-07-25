"""AI 金融陪练层（Coach layer）。

The coach is NOT an expert: it never appears in a plan, never joins the task
DAG, and never triggers new research. It only reads completed reports,
persisted execution events, and the local user profile, then uses the model to
teach — anchored strictly to real evidence. Ark failures are surfaced honestly
and never replaced by fabricated answers (对齐 AlphaOS 可靠性规范).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.core.contracts import (
    CoachGuide,
    CoachGuideDraft,
    CoachNarrationDraft,
    CoachReply,
    CoachReview,
)
from backend.core.user_profile import UserInvestmentProfile
from backend.services.ark_client import ArkClient, ArkClientError, ArkJsonRequest

logger = logging.getLogger(__name__)

# Milestones that may trigger one process narration each (never per-event).
NARRATION_MILESTONES = frozenset(
    {"plan_created", "step_completed", "step_failed", "task_completed"}
)
# Hard cap of model narration calls for a single task.
MAX_NARRATIONS_PER_TASK = 10

_MAX_QUOTED_TEXT_CHARS = 500
_MAX_FRAGMENT_CHARS = 400
_MAX_CONTEXT_CHARS = 6_000
_MAX_EVENT_LINES = 20

_EXPERIENCE_GUIDANCE: dict[str, str] = {
    "none": (
        "用户没有投资经验：用最通俗的语言先解释每个概念是什么、为什么重要，"
        "避免术语堆砌，多给背景铺垫，可用生活化类比。"
    ),
    "basic": (
        "用户有基础投资经验：拆解关键指标与分析框架，解释指标如何计算、"
        "如何解读，以及本报告中的判断逻辑。"
    ),
    "experienced": (
        "用户投资经验丰富：聚焦数据范围、研究方法与证据细节，"
        "讨论方法论局限与证据强度，不必解释入门概念。"
    ),
}


class CoachServiceError(RuntimeError):
    """Raised when a coach model call cannot produce a trustworthy result."""


class CoachService:
    """Model-driven coaching over completed reports and execution milestones."""

    def __init__(self, ark_client: ArkClient | None = None) -> None:
        self._ark_client = ark_client

    @property
    def available(self) -> bool:
        return self._ark_client is not None

    # -- report coaching ------------------------------------------------------

    def answer(
        self,
        report: dict[str, Any],
        question: str,
        quoted_text: str | None = None,
        profile: UserInvestmentProfile | None = None,
    ) -> CoachReply:
        """Answer a report question with evidence-anchored, layered teaching.

        ``quoted_text`` must already be validated by the caller via
        :func:`validate_quoted_text`; it is re-checked here defensively.
        """

        client = self._require_client()
        aggregation = report.get("aggregation")
        if quoted_text is not None and not validate_quoted_text(
            aggregation, quoted_text
        ):
            raise CoachServiceError("引用片段不在报告文本中，已拒绝该请求。")

        context = _build_report_context(aggregation)
        if not context:
            raise CoachServiceError("报告缺少可讲解的聚合内容。")

        prompt = _ANSWER_PROMPT_TEMPLATE.format(
            experience_guidance=_experience_guidance(profile),
            report_context=context,
            quoted_section=(
                f"用户在报告中选中并引用了这段文字，回答必须优先围绕它展开：\n"
                f"「{quoted_text}」"
                if quoted_text
                else "用户没有引用具体片段。"
            ),
            question=question,
        )
        try:
            reply = client.chat_json(
                ArkJsonRequest(
                    prompt=prompt,
                    response_model=CoachReply,
                    temperature=0.2,
                    purpose="coach_answer",
                    prompt_version="1.0",
                )
            )
        except ArkClientError as exc:
            raise CoachServiceError(f"陪练模型调用失败：{exc}") from exc

        rejected = [
            snippet
            for snippet in reply.cited_evidence
            if not _contains_normalized(context, snippet)
        ]
        if rejected:
            raise CoachServiceError(
                "陪练回答引用了报告中不存在的内容，已拒绝该回答。"
            )
        return reply

    def build_guide(
        self,
        report: dict[str, Any],
        profile: UserInvestmentProfile | None = None,
    ) -> CoachGuide:
        """Produce guided questions plus a structured research review.

        Experts, evidence basis, and open questions are extracted
        deterministically from execution evidence; the model only writes the
        framework narrative, the questions, and next learning steps.
        """

        client = self._require_client()
        aggregation = report.get("aggregation")
        context = _build_report_context(aggregation)
        if not context:
            raise CoachServiceError("报告缺少可讲解的聚合内容。")

        experts_involved = _extract_experts(aggregation)
        evidence_basis = _extract_evidence_basis(aggregation)
        open_questions = _extract_open_questions(aggregation)

        prompt = _GUIDE_PROMPT_TEMPLATE.format(
            experience_guidance=_experience_guidance(profile),
            report_context=context,
            experts_involved="、".join(experts_involved) or "（无）",
            evidence_basis="\n".join(f"- {item}" for item in evidence_basis)
            or "- （无）",
            open_questions="\n".join(f"- {item}" for item in open_questions)
            or "- （无）",
        )
        try:
            draft = client.chat_json(
                ArkJsonRequest(
                    prompt=prompt,
                    response_model=CoachGuideDraft,
                    temperature=0.3,
                    purpose="coach_guide",
                    prompt_version="1.0",
                )
            )
        except ArkClientError as exc:
            raise CoachServiceError(f"陪练模型调用失败：{exc}") from exc

        return CoachGuide(
            report_id=str(report.get("id", "")),
            guided_questions=draft.guided_questions,
            review=CoachReview(
                framework=draft.framework,
                experts_involved=experts_involved,
                evidence_basis=evidence_basis,
                open_questions=open_questions,
                next_learning_steps=draft.next_learning_steps,
            ),
            created_at=_now(),
        )

    # -- process coaching -----------------------------------------------------

    def narrate_milestone(
        self,
        goal: str,
        recent_events: list[dict[str, Any]],
        milestone: str,
    ) -> CoachNarrationDraft:
        """Narrate one execution milestone for teaching purposes.

        The caller batches events since the previous milestone, enforces the
        per-task call cap, and treats any failure as "skip this narration".
        """

        client = self._require_client()
        if milestone not in NARRATION_MILESTONES:
            raise CoachServiceError(f"非法的解说里程碑：{milestone}")

        prompt = _NARRATION_PROMPT_TEMPLATE.format(
            goal=goal,
            milestone=milestone,
            event_lines=_format_event_lines(recent_events),
        )
        try:
            return client.chat_json(
                ArkJsonRequest(
                    prompt=prompt,
                    response_model=CoachNarrationDraft,
                    temperature=0.3,
                    timeout_seconds=60.0,
                    purpose="coach_narration",
                    prompt_version="1.0",
                )
            )
        except ArkClientError as exc:
            raise CoachServiceError(f"过程解说生成失败：{exc}") from exc

    # -- internals -------------------------------------------------------------

    def _require_client(self) -> ArkClient:
        if self._ark_client is None:
            raise CoachServiceError(
                "陪练模型服务当前不可用（未配置 ARK_API_KEY）。"
            )
        return self._ark_client


# ---------------------------------------------------------------------------
# Quoted-text validation (IDE-style selection quoting)
# ---------------------------------------------------------------------------


def validate_quoted_text(
    aggregation: dict[str, Any] | None,
    quoted_text: str,
) -> bool:
    """True iff the quote is a whitespace-normalized substring of report text.

    Only renderable report text (direct answer + content block fragments) is a
    valid quote source; raw technical evidence is deliberately excluded.
    """

    if not quoted_text or len(quoted_text) > _MAX_QUOTED_TEXT_CHARS:
        return False
    needle = _normalize(quoted_text)
    if not needle:
        return False
    for fragment in report_text_fragments(aggregation):
        if needle in _normalize(fragment):
            return True
    return False


def report_text_fragments(aggregation: dict[str, Any] | None) -> list[str]:
    """Renderable report text fragments (mirrors the followup fragment scope)."""

    if not isinstance(aggregation, dict):
        return []
    fragments: list[str] = []
    direct = aggregation.get("direct_answer")
    if isinstance(direct, dict):
        for key in ("headline", "explanation"):
            text = direct.get(key)
            if isinstance(text, str) and text.strip():
                fragments.append(text.strip())
    for key in (
        "key_findings",
        "evidence_summary",
        "risks",
        "limitations",
        "next_research_steps",
    ):
        for item in aggregation.get(key, []) or []:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    fragments.append(text.strip())
    for block in aggregation.get("content_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        for key in ("title", "description"):
            text = block.get(key)
            if isinstance(text, str) and text.strip():
                fragments.append(text.strip())
        rendered = _stringify_data(block.get("data"))
        if rendered:
            fragments.append(rendered)
    return fragments


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _stringify_data(data: Any) -> str:
    """Flatten block data strings the same way the report renders them."""

    texts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if value.strip():
                texts.append(value.strip())
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return " ".join(texts)[:2_000]


def _contains_normalized(haystack: str, needle: str) -> bool:
    normalized_needle = _normalize(needle)
    return bool(normalized_needle) and normalized_needle in _normalize(haystack)


# ---------------------------------------------------------------------------
# Deterministic context / extraction helpers
# ---------------------------------------------------------------------------


def _build_report_context(aggregation: dict[str, Any] | None) -> str:
    """Bounded textual context from the aggregation (no raw technical dump)."""

    if not isinstance(aggregation, dict):
        return ""
    sections: list[str] = []
    direct = aggregation.get("direct_answer")
    if isinstance(direct, dict):
        headline = str(direct.get("headline") or "").strip()
        explanation = str(direct.get("explanation") or "").strip()
        if headline:
            sections.append(f"【结论】{_clip(headline)}")
        if explanation:
            sections.append(f"【说明】{_clip(explanation)}")
    validation = aggregation.get("validation")
    if isinstance(validation, dict):
        label = str(validation.get("label") or "").strip()
        explanation = str(validation.get("explanation") or "").strip()
        if label or explanation:
            sections.append(f"【证据成熟度】{_clip(f'{label} {explanation}'.strip())}")
    for key, title in (
        ("key_findings", "关键发现"),
        ("risks", "风险"),
        ("limitations", "局限"),
        ("next_research_steps", "下一步研究"),
    ):
        lines = [
            _clip(str(item.get("text")))
            for item in aggregation.get(key, []) or []
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
        if lines:
            sections.append(f"【{title}】\n" + "\n".join(f"- {line}" for line in lines))
    scopes = aggregation.get("data_scope")
    if isinstance(scopes, list) and scopes:
        sections.append(
            "【数据范围】"
            + _clip(json.dumps(scopes, ensure_ascii=False), 600)
        )
    for block in aggregation.get("content_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        title = str(block.get("title") or "").strip()
        description = str(block.get("description") or "").strip()
        if title or description:
            sections.append(f"【{title or '内容块'}】{_clip(description)}")
    return "\n".join(sections)[:_MAX_CONTEXT_CHARS]


def _extract_experts(aggregation: dict[str, Any] | None) -> list[str]:
    if not isinstance(aggregation, dict):
        return []
    summary = aggregation.get("execution_summary")
    if not isinstance(summary, dict):
        return []
    return [
        str(agent)
        for agent in summary.get("selected_agents", []) or []
        if str(agent).strip()
    ]


def _extract_evidence_basis(aggregation: dict[str, Any] | None) -> list[str]:
    if not isinstance(aggregation, dict):
        return []
    basis = [
        str(item.get("text")).strip()
        for item in aggregation.get("key_findings", []) or []
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    if not basis:
        basis = [
            str(item.get("text")).strip()
            for item in aggregation.get("evidence_summary", []) or []
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
    return basis[:8]


def _extract_open_questions(aggregation: dict[str, Any] | None) -> list[str]:
    if not isinstance(aggregation, dict):
        return []
    questions: list[str] = []
    technical = aggregation.get("technical_evidence")
    if isinstance(technical, dict):
        questions.extend(
            str(item).strip()
            for item in technical.get("missing_evidence", []) or []
            if str(item).strip()
        )
    for key in ("limitations", "next_research_steps"):
        questions.extend(
            str(item.get("text")).strip()
            for item in aggregation.get(key, []) or []
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        )
    deduplicated = list(dict.fromkeys(questions))
    return deduplicated[:8]


def _experience_guidance(profile: UserInvestmentProfile | None) -> str:
    experience = "none"
    if profile is not None and profile.investment_experience:
        experience = profile.investment_experience
    return _EXPERIENCE_GUIDANCE[experience]


def _format_event_lines(events: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for event in events[-_MAX_EVENT_LINES:]:
        if not isinstance(event, dict):
            continue
        parts = [str(event.get("type") or "event")]
        agent = event.get("agent")
        if agent:
            parts.append(f"agent={agent}")
        step_id = event.get("step_id")
        if step_id:
            parts.append(f"step={step_id}")
        message = str(event.get("message") or "").strip()
        if message:
            parts.append(_clip(message, 200))
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines) or "- （无事件）"


def _clip(text: str, limit: int = _MAX_FRAGMENT_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_ANSWER_PROMPT_TEMPLATE = """\
你是 AlphaBit Coach 的金融陪练教练。用户刚读完一份 AI 投研团队生成的研究报告，
现在就报告内容向你提问。你的目标是让用户学到金融知识，而不是替用户做决定。

讲解分层要求：{experience_guidance}

报告内容（这是你唯一可引用的事实来源）：
{report_context}

{quoted_section}

用户问题：{question}

硬性约束：
1. 只能引用上述报告内容中的事实，cited_evidence 里的每一条必须是报告内容的原文片段，禁止编造数字或结论。
2. 允许补充金融常识帮助理解，但必须与报告事实明确区分，且将 is_general_knowledge_included 置为 true。
3. 报告证据不足以回答时必须如实说明，写入 uncertainty_note，不得猜测。
4. 禁止给出任何买入/卖出/持仓等投资建议。
5. 出现的金融术语放入 concept_notes（term + explanation），按上面的分层要求解释。

只输出一个 JSON 对象，不要输出其他文字，字段如下：
{{"answer": "面向用户的讲解正文", "concept_notes": [{{"term": "术语", "explanation": "解释"}}], "cited_evidence": ["报告原文片段"], "uncertainty_note": "不确定性说明，可为空字符串", "is_general_knowledge_included": false}}
"""

_GUIDE_PROMPT_TEMPLATE = """\
你是 AlphaBit Coach 的金融陪练教练。请基于下面这份已完成的研究报告，
为用户生成引导式思考题和研究复盘，帮助用户学会"像分析师一样思考"。

讲解分层要求：{experience_guidance}

报告内容：
{report_context}

以下三组条目由系统从真实执行证据中提取，你只负责组织语言，不得增删条目、
不得改写含义（它们会原样进入复盘，你无需重复输出）：
- 参与专家：{experts_involved}
- 证据基础：
{evidence_basis}
- 未解决问题：
{open_questions}

任务：
1. guided_questions：3-5 个引导思考题，每题附 why_it_matters（这道题为什么值得想）。
   问题必须源自报告的具体内容，能引导用户检验结论、理解方法或关注风险。
2. framework：用 2-4 句话概括本次研究采用的分析框架（研究了什么、按什么路径分析）。
3. next_learning_steps：最多 5 条用户接下来可以学习的方向。

禁止编造报告中不存在的事实，禁止投资建议。
只输出一个 JSON 对象，不要输出其他文字，字段如下：
{{"guided_questions": [{{"question": "思考题", "why_it_matters": "为什么值得想"}}], "framework": "分析框架概括", "next_learning_steps": ["学习方向"]}}
"""

_NARRATION_PROMPT_TEMPLATE = """\
你是 AlphaBit Coach 的投研课堂解说员。一个多 Agent AI 投研团队正在执行用户的研究任务，
你要在关键节点向旁观的用户解说"现在发生了什么"，以及"真实投研中这一步意味着什么"。

用户的研究目标：{goal}
当前里程碑：{milestone}
自上一里程碑以来的真实执行事件：
{event_lines}

硬性约束：
1. 只能基于上述事件事实解说，禁止新增任何研究结论、数字或预测。
2. narration：口语化描述刚才发生了什么（2-3 句，像现场解说）。
3. teaching_point：解释真实投研工作中这一步的意义（1-2 句，教学视角）。
4. 禁止投资建议。

只输出一个 JSON 对象，不要输出其他文字，字段如下：
{{"narration": "现场解说", "teaching_point": "教学要点"}}
"""
