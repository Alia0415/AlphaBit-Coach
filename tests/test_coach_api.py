"""Coach endpoints: validation, persistence, guide caching, compat fields."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.core.coach_service import CoachService, CoachServiceError
from backend.core.contracts import (
    CoachGuide,
    CoachReply,
    CoachReview,
    ConceptNote,
    GuidedQuestion,
)


class FakeCoachService(CoachService):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(ark_client=None)
        self.fail = fail
        self.guide_calls = 0

    def answer(self, report, question, quoted_text=None, profile=None):  # noqa: ANN001
        if self.fail:
            raise CoachServiceError("陪练模型调用失败：模拟故障")
        return CoachReply(
            answer="报告显示全年收益率约 15%。",
            concept_notes=[ConceptNote(term="收益率", explanation="投资回报比例。")],
            cited_evidence=["全年收益率约 15%。"],
            uncertainty_note="",
            is_general_knowledge_included=False,
        )

    def build_guide(self, report, profile=None):  # noqa: ANN001
        if self.fail:
            raise CoachServiceError("陪练模型调用失败：模拟故障")
        self.guide_calls += 1
        return CoachGuide(
            report_id=str(report.get("id", "")),
            guided_questions=[
                GuidedQuestion(
                    question=f"思考题 v{self.guide_calls}",
                    why_it_matters="检验结论稳健性。",
                )
            ],
            review=CoachReview(
                framework="行情研究框架",
                experts_involved=["research"],
                evidence_basis=["全年收益率约 15%。"],
                open_questions=["未覆盖基本面维度。"],
                next_learning_steps=["学习收益率计算"],
            ),
            created_at="2026-07-25T00:00:00+00:00",
        )


def _seed_report() -> str:
    report_id = uuid.uuid4().hex
    task_id = uuid.uuid4().hex
    main_module.store.create_task(
        task_id=task_id,
        prompt="分析 000001.SZ 在 2024 年的价格表现。",
        status="completed",
        plan={"goal": "分析 000001.SZ", "steps": []},
    )
    main_module.store.create_report(
        report_id=report_id,
        task_id=task_id,
        title="分析 000001.SZ",
        aggregation={
            "user_goal": "分析 000001.SZ",
            "completion_status": "completed",
            "output_mode": "data_analysis",
            "direct_answer": {
                "headline": "平安银行 2024 年全年上涨",
                "explanation": "区间累计收益为正，全年收益率约 15%。",
                "confidence": "medium",
                "stance": "neutral",
            },
            "content_blocks": [],
        },
    )
    return report_id


def test_coach_ask_persists_both_turns_and_returns_model_message() -> None:
    report_id = _seed_report()
    client = TestClient(main_module.app)

    with patch.object(main_module, "coach_service", FakeCoachService()):
        response = client.post(
            f"/api/reports/{report_id}/coach",
            json={"question": "收益率是多少？", "quoted_text": "全年收益率约 15%"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "coach"
    assert body["generated_by"] == "model"
    assert body["quoted_text"] == "全年收益率约 15%"
    assert body["concept_notes"][0]["term"] == "收益率"
    assert body["cited_evidence"] == ["全年收益率约 15%。"]

    detail = client.get(f"/api/reports/{report_id}").json()
    roles = [m["role"] for m in detail["coach_messages"]]
    assert roles == ["user", "coach"]
    assert detail["coach_messages"][0]["quoted_text"] == "全年收益率约 15%"
    assert detail["coach_messages"][0]["generated_by"] == "user"


def test_coach_ask_rejects_quote_not_in_report() -> None:
    report_id = _seed_report()
    client = TestClient(main_module.app)

    with patch.object(main_module, "coach_service", FakeCoachService()):
        response = client.post(
            f"/api/reports/{report_id}/coach",
            json={"question": "解释一下", "quoted_text": "报告里没有这句话"},
        )

    assert response.status_code == 422
    # Nothing is persisted for a rejected request.
    assert main_module.store.list_coach_messages(report_id) == []


def test_coach_ask_surfaces_model_failure_as_502() -> None:
    report_id = _seed_report()
    client = TestClient(main_module.app)

    with patch.object(main_module, "coach_service", FakeCoachService(fail=True)):
        response = client.post(
            f"/api/reports/{report_id}/coach",
            json={"question": "收益率是多少？"},
        )

    assert response.status_code == 502
    assert "陪练模型调用失败" in response.json()["detail"]
    assert main_module.store.list_coach_messages(report_id) == []


def test_coach_ask_on_missing_report_returns_404() -> None:
    response = TestClient(main_module.app).post(
        "/api/reports/nope/coach",
        json={"question": "任意问题"},
    )
    assert response.status_code == 404


def test_coach_guide_is_cached_until_refresh() -> None:
    report_id = _seed_report()
    client = TestClient(main_module.app)
    fake = FakeCoachService()

    with patch.object(main_module, "coach_service", fake):
        first = client.get(f"/api/reports/{report_id}/coach/guide")
        second = client.get(f"/api/reports/{report_id}/coach/guide")
        # Second call hits the cache: the model is not called again.
        assert fake.guide_calls == 1
        refreshed = client.get(
            f"/api/reports/{report_id}/coach/guide?refresh=true"
        )

    assert first.status_code == 200
    assert first.json()["guided_questions"][0]["question"] == "思考题 v1"
    assert second.json()["guided_questions"][0]["question"] == "思考题 v1"
    # refresh=true regenerates.
    assert refreshed.json()["guided_questions"][0]["question"] == "思考题 v2"
    assert fake.guide_calls == 2


def test_coach_guide_on_missing_report_returns_404() -> None:
    response = TestClient(main_module.app).get("/api/reports/nope/coach/guide")
    assert response.status_code == 404


def test_report_detail_exposes_compat_coach_fields() -> None:
    report_id = _seed_report()
    client = TestClient(main_module.app)

    detail = client.get(f"/api/reports/{report_id}").json()

    assert detail["coach_messages"] == []
    assert detail["coach_guide"] is None
