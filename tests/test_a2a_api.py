from __future__ import annotations

import asyncio
import time
import uuid

from fastapi.testclient import TestClient

from backend import main as main_module


def test_a2a_agent_card_is_public_and_complete() -> None:
    response = TestClient(main_module.app).get("/.well-known/agent-card.json")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "AlphaOS Quant Research Organization"
    assert body["url"].endswith("/a2a")
    assert body["capabilities"]["pushNotifications"] is False
    assert any(skill["id"] == "multi_agent_quant_research" for skill in body["skills"])


def test_a2a_message_send_returns_before_execution_finishes(monkeypatch) -> None:
    task_id = f"a2a-async-{uuid.uuid4().hex}"

    async def scenario() -> None:
        execution_started = asyncio.Event()
        release_execution = asyncio.Event()

        async def slow_execution(_task_id: str, _prompt: str):
            execution_started.set()
            await release_execution.wait()
            raise RuntimeError("test execution stopped")

        monkeypatch.setattr(main_module, "_execute_a2a_prompt", slow_execution)

        task = await asyncio.wait_for(
            main_module._a2a_send_message(
                {"taskId": task_id, "text": "分析 600519.SH 的主要风险。"}
            ),
            timeout=0.1,
        )

        assert task["id"] == task_id
        assert task["status"]["state"] == "working"
        await asyncio.wait_for(execution_started.wait(), timeout=0.1)

        release_execution.set()
        await asyncio.gather(*list(main_module._a2a_tasks))
        assert main_module.store.get_task(task_id)["status"] == "failed"

    asyncio.run(scenario())


def test_a2a_message_send_accepts_text_parts_and_persists_task() -> None:
    task_id = f"a2a-test-weather-{uuid.uuid4().hex}"
    with TestClient(main_module.app) as client:
        response = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "message/send",
                "params": {
                    "taskId": task_id,
                    "message": {
                        "role": "user",
                        "messageId": "diagnostic-message",
                        "parts": [{"kind": "text", "text": "今天天气怎么样？"}],
                    },
                    "configuration": {
                        "acceptedOutputModes": ["text/plain", "application/json"]
                    },
                },
            },
        )

        assert response.status_code == 200
        envelope = response.json()
        assert envelope["id"] == "rpc-1"
        task = envelope["result"]
        assert task["kind"] == "task"
        assert task["id"] == task_id
        assert task["status"]["state"] == "working"
        assert task["status"]["message"]["kind"] == "message"
        assert task["status"]["message"]["messageId"] == f"{task_id}-status"
        assert task["history"][0]["kind"] == "message"
        assert task["artifacts"][0]["parts"][0]["kind"] == "text"

        for _ in range(100):
            fetched = client.post(
                "/a2a",
                json={
                    "jsonrpc": "2.0",
                    "id": "rpc-2",
                    "method": "tasks/get",
                    "params": {"id": task_id},
                },
            )
            fetched_task = fetched.json()["result"]
            if fetched_task["status"]["state"] != "working":
                break
            time.sleep(0.01)

        assert fetched.status_code == 200
        assert fetched_task["kind"] == "task"
        assert fetched_task["id"] == task_id
        assert fetched_task["status"]["state"] == "completed"
        assert fetched_task["status"]["message"]["kind"] == "message"


def test_a2a_bearer_auth_is_enforced_when_configured(monkeypatch) -> None:
    monkeypatch.setenv(main_module.A2A_TOKEN_ENV, "secret-token")
    client = TestClient(main_module.app)

    rejected = client.post(
        "/a2a/message:send",
        json={"text": "今天天气怎么样？"},
    )
    accepted = client.post(
        "/a2a/message:send",
        headers={"Authorization": "Bearer secret-token"},
        json={"taskId": "a2a-auth-ok", "text": "今天天气怎么样？"},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["id"] == "a2a-auth-ok"
