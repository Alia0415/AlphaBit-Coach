"""Backend-owned planning progress, recovery, and failure contracts."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.agents.manager_agent import ManagerAgentError
from backend.core.contracts import ExecutionPlan


def _plan() -> ExecutionPlan:
    return ExecutionPlan.model_validate(
        {
            "goal": "分析 000001.SZ 的历史价格表现",
            "intent": "按用户目标执行",
            "complexity": "low",
            "selected_agents": [
                {"agent": "research", "reason": "需要核验真实市场数据"}
            ],
            "steps": [
                {
                    "id": "research_1",
                    "agent": "research",
                    "objective": "核验历史价格表现",
                    "inputs": {
                        "symbols": ["000001.SZ"],
                        "start_date": "20240101",
                        "end_date": "20241231",
                        "fields": [],
                    },
                    "depends_on": [],
                    "expected_output": "可追溯的历史市场证据",
                }
            ],
            "needs_clarification": False,
            "clarification_question": None,
        }
    )


def _wait_for_terminal(client: TestClient, run_id: str) -> dict:
    for _ in range(200):
        state = client.get(f"/api/research/runs/{run_id}/status").json()
        if state["status"] in {"plan_ready", "failed"}:
            return state
        time.sleep(0.01)
    raise AssertionError("research run did not reach a terminal planning state")


def test_research_run_exposes_only_real_manager_outputs(isolated_store) -> None:
    class StubManager:
        def create_plan(self, *args: object) -> ExecutionPlan:
            time.sleep(0.03)
            return _plan()

    with (
        TestClient(main_module.app) as client,
        patch.object(main_module, "manager", StubManager()),
    ):
        created = client.post(
            "/api/research/runs",
            json={"prompt": "分析 000001.SZ 在 2024 年的价格表现。"},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        terminal = _wait_for_terminal(client, run_id)

        assert terminal["current_stage"] == "plan_ready"
        assert terminal["progress"] == 100
        assert terminal["selected_agents"] == [
            {"agent": "research", "reason": "需要核验真实市场数据"}
        ]
        assert terminal["dag"]["steps"][0]["agent"] == "research"

        events = isolated_store.list_research_run_events(run_id)
        stages = [event["payload"]["current_stage"] for event in events]
        assert stages == [
            "received",
            "interpreting",
            "interpreted",
            "selecting_agents",
            "agents_selected",
            "building_dag",
            "validating_dag",
            "plan_ready",
        ]
        assert all(
            event["payload"]["selected_agents"] == []
            for event in events
            if stages.index(event["payload"]["current_stage"])
            < stages.index("agents_selected")
        )
        assert all(
            event["payload"]["dag"] is None
            for event in events
            if event["payload"]["current_stage"] != "plan_ready"
        )
        assert terminal["estimated_remaining_ms"] is None

        stream = client.get(f"/api/research/runs/{run_id}/events")
        assert stream.status_code == 200
        assert "event: done" in stream.text
        assert '"stage": "plan_ready"' in stream.text
        assert '"current_stage": "plan_ready"' in stream.text


def test_research_run_failure_preserves_real_failed_stage() -> None:
    class FailingManager:
        def create_plan(self, *args: object) -> ExecutionPlan:
            raise ManagerAgentError("上游规划模型暂时不可用")

    with (
        TestClient(main_module.app) as client,
        patch.object(main_module, "manager", FailingManager()),
    ):
        created = client.post(
            "/api/research/runs",
            json={"prompt": "分析 000001.SZ 在 2024 年的价格表现。"},
        )
        terminal = _wait_for_terminal(client, created.json()["run_id"])

    assert terminal["status"] == "failed"
    assert terminal["current_stage"] == "failed"
    assert terminal["failed_stage"] == "selecting_agents"
    assert "上游规划模型暂时不可用" in terminal["error"]
    assert terminal["dag"] is None


def test_fixed_stock_run_skips_interpreter_and_manager(isolated_store) -> None:
    class ForbiddenInterpreter:
        def interpret(self, *args: object) -> None:
            raise AssertionError("fixed stock workflow must skip Task Interpreter")

    class ForbiddenManager:
        def create_plan(self, *args: object) -> None:
            raise AssertionError("fixed stock workflow must skip Manager")

    with (
        TestClient(main_module.app) as client,
        patch.object(main_module, "task_interpreter", ForbiddenInterpreter()),
        patch.object(main_module, "manager", ForbiddenManager()),
    ):
        created = client.post(
            "/api/research/runs",
            json={
                "prompt": "全面分析贵州茅台（600519.SH）。",
                "workflow_mode": "stock_analysis",
                "stock_symbol": "600519.SH",
                "stock_name": "贵州茅台",
                "stock_board": "沪市主板",
            },
        )
        assert created.status_code == 202
        terminal = _wait_for_terminal(client, created.json()["run_id"])

    assert terminal["status"] == "plan_ready"
    assert terminal["workflow_mode"] == "stock_analysis"
    assert terminal["dag"]["intent"].startswith("使用固定股票研究预设")
    assert [
        selection["agent"]
        for selection in terminal["dag"]["selected_agents"]
    ] == ["research", "quant", "macro", "risk"]
    assert "固定 Agent 工作流已就绪" in terminal["message"]


def test_remaining_estimate_requires_three_real_plan_samples(isolated_store) -> None:
    def add_sample(
        index: int,
        elapsed_ms: int,
        workflow_mode: str = "dynamic",
    ) -> None:
        run_id = f"history-{index}"
        state = {
            "run_id": run_id,
            "workflow_mode": workflow_mode,
            "status": "running",
            "current_stage": "received",
            "progress": 2,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "selected_agents": [],
            "dag": None,
            "elapsed_ms": 0,
            "estimated_remaining_ms": None,
            "error": None,
            "failed_stage": None,
            "message": "received",
        }
        isolated_store.create_research_run(state)
        state.update(
            {
                "status": "plan_ready",
                "current_stage": "plan_ready",
                "progress": 100,
                "elapsed_ms": elapsed_ms,
                "message": "ready",
            }
        )
        isolated_store.record_research_run_state(state)

    add_sample(1, 1000)
    add_sample(2, 2000)
    assert isolated_store.estimate_research_run_remaining(500) is None
    add_sample(3, 3000)
    assert isolated_store.estimate_research_run_remaining(500) == 1500

    add_sample(4, 100, "stock_analysis")
    add_sample(5, 200, "stock_analysis")
    add_sample(6, 300, "stock_analysis")
    assert isolated_store.estimate_research_run_remaining(500) == 1500
    assert (
        isolated_store.estimate_research_run_remaining(
            50,
            workflow_mode="stock_analysis",
        )
        == 150
    )
