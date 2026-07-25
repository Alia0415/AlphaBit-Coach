"""Planning session creation and SSE streaming execution with persistence."""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.agents.manager_agent import ManagerAgent
from backend.core.contracts import AgentId, ExpertResult, ExpertTask
from backend.core.policy_contracts import PolicyDecision
from backend.core.task_interpreter import TaskInterpreter
from backend.core.workflow_executor import WorkflowExecutor


class MockArkClient:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def chat(self, prompt: str, model: str | None = None) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def _research_plan_payload() -> dict:
    return {
        "goal": "分析 000001.SZ 在 2024 年的价格表现",
        "intent": "按用户目标执行",
        "complexity": "medium",
        "selected_agents": [
            {"agent": "research", "reason": "获取市场证据"},
            {"agent": "risk", "reason": "审查风险和证据限制"},
        ],
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
            },
            {
                "id": "risk_1",
                "agent": "risk",
                "objective": "审查窗口、下行风险和证据限制",
                "inputs": {"symbols": ["000001.SZ"]},
                "depends_on": ["research_1"],
                "expected_output": "risk review",
            },
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

    return WorkflowExecutor(
        handlers={
            AgentId.RESEARCH: handler,
            AgentId.RISK: handler,
        }
    )


def test_session_creates_plan_and_persists_without_executing() -> None:
    manager = ManagerAgent(
        client=MockArkClient(json.dumps(_research_plan_payload(), ensure_ascii=False))
    )
    client = TestClient(main_module.app)
    with patch.object(main_module, "manager", manager):
        response = client.post(
            "/api/tasks/sessions",
            json={"prompt": "分析 000001.SZ 在 2024 年的价格表现。"},
        )

    assert response.status_code == 200
    body = response.json()
    task_id = body["task_id"]
    assert body["plan"]["steps"][0]["agent"] == "research"

    detail = client.get(f"/api/tasks/{task_id}").json()
    assert detail["status"] == "planned"
    assert [e["type"] for e in detail["events"]] == ["plan_created"]
    assert detail["aggregation"] is None


def test_session_passes_interpreted_task_spec_to_manager() -> None:
    prompt = "分析 000001.SZ 在 2024 年的价格表现。"
    policy = PolicyDecision(
        decision="allowed_research",
        allowed=True,
        domain="quant_investment_research",
        policy_tags=[],
        reason="test",
    )
    task_spec = TaskInterpreter().interpret(prompt, policy)
    calls: list[tuple[object, ...]] = []

    class StubInterpreter:
        def interpret(self, raw_prompt: str, raw_policy: object) -> object:
            return task_spec

    class RecordingManager:
        def create_plan(self, *args: object) -> object:
            calls.append(args)
            return ManagerAgent(
                client=MockArkClient(
                    json.dumps(_research_plan_payload(), ensure_ascii=False)
                )
            ).create_plan(task_spec, prompt)

    with (
        patch.object(main_module, "task_interpreter", StubInterpreter()),
        patch.object(main_module, "manager", RecordingManager()),
    ):
        response = TestClient(main_module.app).post(
            "/api/tasks/sessions", json={"prompt": prompt}
        )

    assert response.status_code == 200
    assert calls == [(task_spec, prompt)]


def test_stream_executes_plan_and_persists_events_and_report() -> None:
    manager = ManagerAgent(
        client=MockArkClient(json.dumps(_research_plan_payload(), ensure_ascii=False))
    )
    client = TestClient(main_module.app)
    with (
        patch.object(main_module, "manager", manager),
        patch.object(main_module, "workflow_executor", _mock_executor()),
    ):
        created = client.post(
            "/api/tasks/sessions",
            json={"prompt": "分析 000001.SZ 在 2024 年的价格表现。"},
        )
        task_id = created.json()["task_id"]
        stream = client.get(f"/api/tasks/{task_id}/stream")
        assert stream.status_code == 200
        messages = _parse_sse(stream.text)

    execution_types = [data["type"] for name, data in messages if name is None]
    assert execution_types == [
        "plan_created",
        "step_started",
        "step_completed",
        "step_started",
        "step_completed",
        "synthesis_started",
        "task_completed",
    ]
    named = {name: data for name, data in messages if name is not None}
    assert "aggregation" in named
    assert named["aggregation"]["completeness"]["completion_ratio"] == 1.0
    assert "report_id" in named["aggregation"]
    aggregation = named["aggregation"]["aggregation"]
    assert aggregation["direct_answer"]["headline"] != "已完成所需的数据计算"
    assert aggregation["key_findings"] or aggregation["evidence_summary"]
    assert named["done"]["status"] == "completed"

    detail = client.get(f"/api/tasks/{task_id}").json()
    assert detail["status"] == "completed"
    assert [e["type"] for e in detail["events"]] == execution_types
    assert detail["aggregation"] is not None
    stored = main_module.store.get_task(task_id)
    assert stored is not None
    assert stored["task_spec"]
    assert aggregation["result_type"] == stored["task_spec"]["task_type"]

    reports = client.get("/api/reports").json()
    assert len(reports) == 1
    assert reports[0]["task_id"] == task_id


def test_stream_on_missing_task_returns_404() -> None:
    response = TestClient(main_module.app).get("/api/tasks/nope/stream")
    assert response.status_code == 404
