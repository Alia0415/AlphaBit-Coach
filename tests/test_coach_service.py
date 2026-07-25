"""CoachService: evidence anchoring, quote validation, layering, honest failure."""

from __future__ import annotations

import pytest

from backend.core.coach_service import (
    CoachService,
    CoachServiceError,
    report_text_fragments,
    validate_quoted_text,
)
from backend.core.contracts import (
    CoachGuideDraft,
    CoachNarrationDraft,
    CoachReply,
    ConceptNote,
    GuidedQuestion,
)
from backend.core.user_profile import UserInvestmentProfile
from backend.services.ark_client import ArkClientError, ArkErrorKind


class FakeArkClient:
    """Returns queued Pydantic objects or raises queued exceptions."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[object] = []

    def chat_json(self, request, budget_remaining_seconds=None):  # noqa: ANN001
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _aggregation() -> dict:
    return {
        "user_goal": "分析 000001.SZ",
        "completion_status": "completed",
        "output_mode": "data_analysis",
        "direct_answer": {
            "headline": "平安银行 2024 年全年上涨",
            "explanation": "区间累计收益为正，成交量整体放大。",
            "confidence": "medium",
            "stance": "neutral",
        },
        "key_findings": [
            {"text": "全年收益率约 15%。", "evidence_type": "fact"},
        ],
        "risks": [{"text": "银行板块波动风险。", "evidence_type": "risk"}],
        "limitations": [
            {"text": "未覆盖基本面维度。", "evidence_type": "limitation"},
        ],
        "next_research_steps": [
            {"text": "补充财务报表分析。", "evidence_type": "research_action"},
        ],
        "content_blocks": [
            {
                "id": "b1",
                "type": "metric_cards",
                "title": "区间收益",
                "importance": "primary",
                "description": "period_return 指标显示全年收益率约 15%。",
                "data": {"period_return": "15%", "max_drawdown": "8%"},
            }
        ],
        "execution_summary": {
            "selected_agents": ["research", "quant"],
            "completed_steps": ["research_1", "quant_1"],
            "failed_steps": [],
            "blocked_steps": [],
            "analysis_path": [],
        },
        "technical_evidence": {
            "validation_statuses": {},
            "conflicts": [],
            "missing_evidence": ["缺少行业对比数据"],
            "source_results": {},
        },
    }


def _report() -> dict:
    return {"id": "r1", "task_id": "t1", "aggregation": _aggregation()}


def _reply(**overrides) -> CoachReply:
    payload = {
        "answer": "报告显示全年收益率约 15%，属于正收益区间。",
        "concept_notes": [ConceptNote(term="收益率", explanation="投资回报比例。")],
        "cited_evidence": ["全年收益率约 15%。"],
        "uncertainty_note": "",
        "is_general_knowledge_included": True,
    }
    payload.update(overrides)
    return CoachReply(**payload)


# -- quoted text validation ---------------------------------------------------


def test_validate_quoted_text_accepts_report_substring() -> None:
    assert validate_quoted_text(_aggregation(), "全年收益率约 15%")


def test_validate_quoted_text_normalizes_whitespace() -> None:
    assert validate_quoted_text(_aggregation(), "全年 收益率约\n15%")


def test_validate_quoted_text_rejects_foreign_text() -> None:
    assert not validate_quoted_text(_aggregation(), "报告里根本没有这句话")


def test_validate_quoted_text_rejects_oversized_quote() -> None:
    assert not validate_quoted_text(_aggregation(), "长" * 501)


def test_report_fragments_exclude_raw_technical_evidence() -> None:
    fragments = " ".join(report_text_fragments(_aggregation()))
    assert "缺少行业对比数据" not in fragments


# -- answer ---------------------------------------------------------------


def test_answer_returns_anchored_reply() -> None:
    ark = FakeArkClient(_reply())
    service = CoachService(ark_client=ark)

    reply = service.answer(_report(), "收益率是多少？")

    assert "15%" in reply.answer
    assert reply.cited_evidence == ["全年收益率约 15%。"]
    request = ark.requests[0]
    assert request.allow_repair is True
    assert request.purpose == "coach_answer"


def test_answer_rejects_fabricated_citation() -> None:
    ark = FakeArkClient(_reply(cited_evidence=["编造的收益率 99%"]))
    service = CoachService(ark_client=ark)

    with pytest.raises(CoachServiceError, match="不存在的内容"):
        service.answer(_report(), "收益率是多少？")


def test_answer_rejects_invalid_quoted_text() -> None:
    service = CoachService(ark_client=FakeArkClient(_reply()))

    with pytest.raises(CoachServiceError, match="引用片段"):
        service.answer(_report(), "解释一下", quoted_text="不在报告里的话")


def test_answer_anchors_valid_quoted_text_in_prompt() -> None:
    ark = FakeArkClient(_reply())
    service = CoachService(ark_client=ark)

    service.answer(_report(), "这句话什么意思？", quoted_text="全年收益率约 15%")

    assert "全年收益率约 15%" in ark.requests[0].prompt


@pytest.mark.parametrize(
    ("experience", "marker"),
    [
        (None, "没有投资经验"),
        ("none", "没有投资经验"),
        ("basic", "基础投资经验"),
        ("experienced", "投资经验丰富"),
    ],
)
def test_answer_layers_prompt_by_experience(experience, marker) -> None:
    ark = FakeArkClient(_reply())
    service = CoachService(ark_client=ark)
    profile = (
        UserInvestmentProfile(investment_experience=experience)
        if experience is not None
        else None
    )

    service.answer(_report(), "收益率是多少？", profile=profile)

    assert marker in ark.requests[0].prompt


def test_answer_surfaces_ark_failure_without_fallback() -> None:
    ark = FakeArkClient(
        ArkClientError("模型超时", kind=ArkErrorKind.TIMEOUT)
    )
    service = CoachService(ark_client=ark)

    with pytest.raises(CoachServiceError, match="调用失败"):
        service.answer(_report(), "收益率是多少？")


def test_answer_without_client_reports_unavailable() -> None:
    with pytest.raises(CoachServiceError, match="不可用"):
        CoachService().answer(_report(), "收益率是多少？")


# -- guide ---------------------------------------------------------------


def test_build_guide_keeps_deterministic_entries() -> None:
    draft = CoachGuideDraft(
        guided_questions=[
            GuidedQuestion(question=f"问题{i}", why_it_matters=f"原因{i}")
            for i in range(3)
        ],
        framework="先做行情研究，再做量化验证。",
        next_learning_steps=["学习收益率计算"],
    )
    ark = FakeArkClient(draft)
    service = CoachService(ark_client=ark)

    guide = service.build_guide(_report())

    assert guide.report_id == "r1"
    assert len(guide.guided_questions) == 3
    # Experts/evidence/open questions come from code, not from the model.
    assert guide.review.experts_involved == ["research", "quant"]
    assert guide.review.evidence_basis == ["全年收益率约 15%。"]
    assert "缺少行业对比数据" in guide.review.open_questions
    assert "未覆盖基本面维度。" in guide.review.open_questions
    assert guide.review.framework == "先做行情研究，再做量化验证。"
    assert guide.generated_by == "model"


def test_build_guide_surfaces_ark_failure() -> None:
    ark = FakeArkClient(ArkClientError("挂了", kind=ArkErrorKind.SERVER))
    service = CoachService(ark_client=ark)

    with pytest.raises(CoachServiceError, match="调用失败"):
        service.build_guide(_report())


# -- narration ---------------------------------------------------------------


def test_narrate_milestone_returns_draft_with_event_context() -> None:
    draft = CoachNarrationDraft(
        narration="研究专家刚完成了行情分析。",
        teaching_point="真实投研中先确认数据再下结论。",
    )
    ark = FakeArkClient(draft)
    service = CoachService(ark_client=ark)
    events = [
        {"type": "step_completed", "agent": "research", "step_id": "research_1",
         "message": "研究步骤完成"},
    ]

    result = service.narrate_milestone("分析 000001.SZ", events, "step_completed")

    assert result.narration
    prompt = ark.requests[0].prompt
    assert "step_completed" in prompt
    assert "研究步骤完成" in prompt


def test_narrate_milestone_rejects_unknown_milestone() -> None:
    service = CoachService(ark_client=FakeArkClient())

    with pytest.raises(CoachServiceError, match="里程碑"):
        service.narrate_milestone("目标", [], "tool_called")


def test_narrate_milestone_surfaces_ark_failure() -> None:
    ark = FakeArkClient(ArkClientError("连接失败", kind=ArkErrorKind.CONNECTION))
    service = CoachService(ark_client=ark)

    with pytest.raises(CoachServiceError, match="解说生成失败"):
        service.narrate_milestone("目标", [], "task_completed")
