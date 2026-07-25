"""Process coaching: milestone-triggered SSE narrations, cap, skip-on-failure."""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.agents.manager_agent import ManagerAgent
from backend.core.coach_service import CoachService, CoachServiceError
from backend.core.contracts import AgentId, CoachNarrationDraft, ExpertResult, ExpertTask
from backend.core.workflow_executor import WorkflowExecutor


class MockArkClient:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)

    def chat(self, prompt: str, model: str | None = None) -> str:
        return self.responses.pop(0)


class FakeCoachService(CoachService):
    """Deterministic narrations without any model call."""

    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(ark_client=None)
        self.fail = fail
        self.calls: list[tuple[str, int]] = []

    @property
    def available(self) -> bool:  # narration path checks availability
        return True

    def narrate_milestone(self, goal, recent_events, milestone):  # noqa: ANN001
        self.calls.append((milestone, len(recent_events)))
        if self.fail:
            raise CoachServiceError("模拟模型失败")
        return CoachNarrationDraft(
            narration=f"解说：{milestone}",
            teaching_point=f"教学：{milestone}",
        )


def _research_plan_payload() -> dict:
    return {
        "goal": "分析 000001.SZ 在 2024 年的价格表现",
        "intent": "按用户目标执行",
        "complexity": "low",
        "selected_agents": [{"agent": "research", "reason": "需要 research"}],
        "steps": [
            {
                "id": "research_1",
                "agent": "research",
                "objective": "research objective",
                "inputs": {
                    "symbols": ["000001.SZ"],
                    "start_date": "20240101",
                    "end_date": "20241231",
                    "fields": [],
                },
                "depends_on": [],
                "expected_output": "research output",
            }
        ],
        "needs_clarification": False,
        "clarification_question": None,
    }


def _parse_sse(text: str) -> list[tuple[str | None, dict]]:
    messages: list[tuple[str | None, dict]] = []
    for chunk in text.strip().split("\n\n"):
        if not chunk.strip():
            continue
        event_name: str | None = None
        data_line = ""
        for line in chunk.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data_line = line[len("data: ") :]
        messages.append((event_name, json.loads(data_line)))
    return messages


def _mock_executor() -> WorkflowExecutor:
    def handler(task: ExpertTask) -> ExpertResult:
        return ExpertResult(
            task_id=task.task_id,
            agent=task.agent,
            status="completed",
            summary="research completed",
            evidence=[{"metric": "period_return", "value": 1.0}],
        )

    return WorkflowExecutor(handlers={AgentId.RESEARCH: handler})


def _run_stream(coach: CoachService) -> tuple[str, list[tuple[str | None, dict]]]:
    manager = ManagerAgent(
        client=MockArkClient(json.dumps(_research_plan_payload(), ensure_ascii=False))
    )
    client = TestClient(main_module.app)
    with (
        patch.object(main_module, "manager", manager),
        patch.object(main_module, "workflow_executor", _mock_executor()),
        patch.object(main_module, "coach_service", coach),
    ):
        created = client.post(
            "/api/tasks/sessions",
            json={"prompt": "分析 000001.SZ 在 2024 年的价格表现。"},
        )
        task_id = created.json()["task_id"]
        stream = client.get(f"/api/tasks/{task_id}/stream")
        assert stream.status_code == 200
        return task_id, _parse_sse(stream.text)


def test_milestones_trigger_narrations_and_sse_coach_events() -> None:
    coach = FakeCoachService()
    task_id, messages = _run_stream(coach)

    milestones = [m for m, _count in coach.calls]
    assert milestones == ["plan_created", "step_completed", "task_completed"]
    # Batched context: the plan_created narration consumes the replayed events.
    assert coach.calls[0][1] >= 1

    coach_events = [data for name, data in messages if name == "coach"]
    assert {event["milestone"] for event in coach_events} == {
        "plan_created",
        "step_completed",
        "task_completed",
    }
    for event in coach_events:
        assert event["generated_by"] == "model"
        assert event["narration"]
        assert event["teaching_point"]

    # Narrations are persisted for replay.
    persisted = main_module.store.list_coach_narrations(task_id)
    assert len(persisted) == 3


def test_narration_failure_skips_but_task_completes() -> None:
    coach = FakeCoachService(fail=True)
    task_id, messages = _run_stream(coach)

    assert not [data for name, data in messages if name == "coach"]
    named = {name: data for name, data in messages if name is not None}
    assert named["done"]["status"] == "completed"
    assert main_module.store.list_coach_narrations(task_id) == []


def test_unavailable_coach_never_blocks_stream() -> None:
    task_id, messages = _run_stream(CoachService())  # no ark client

    assert not [data for name, data in messages if name == "coach"]
    named = {name: data for name, data in messages if name is not None}
    assert named["done"]["status"] == "completed"
    assert main_module.store.list_coach_narrations(task_id) == []


def test_narration_call_cap_is_enforced() -> None:
    coach = FakeCoachService()
    with patch.object(main_module, "MAX_NARRATIONS_PER_TASK", 1):
        _task_id, messages = _run_stream(coach)

    assert [m for m, _count in coach.calls] == ["plan_created"]
    coach_events = [data for name, data in messages if name == "coach"]
    assert len(coach_events) == 1


def test_replay_endpoint_returns_persisted_narrations() -> None:
    coach = FakeCoachService()
    task_id, _messages = _run_stream(coach)

    client = TestClient(main_module.app)
    response = client.get(f"/api/tasks/{task_id}/coach-narrations")
    assert response.status_code == 200
    narrations = response.json()
    assert [n["milestone"] for n in narrations] == [
        "plan_created",
        "step_completed",
        "task_completed",
    ]
    assert [n["seq"] for n in narrations] == [1, 2, 3]
    assert all(n["generated_by"] == "model" for n in narrations)


def test_replay_endpoint_on_missing_task_returns_404() -> None:
    response = TestClient(main_module.app).get(
        "/api/tasks/nope/coach-narrations"
    )
    assert response.status_code == 404
