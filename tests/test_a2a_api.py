from __future__ import annotations

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


def test_a2a_message_send_accepts_text_parts_and_persists_task() -> None:
    client = TestClient(main_module.app)

    response = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "method": "message/send",
            "params": {
                "taskId": "a2a-test-weather",
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
    assert task["id"] == "a2a-test-weather"
    assert task["status"]["state"] == "completed"
    assert task["status"]["message"]["kind"] == "message"
    assert task["status"]["message"]["messageId"] == "a2a-test-weather-status"
    assert task["history"][0]["kind"] == "message"
    assert task["artifacts"][0]["parts"][0]["kind"] == "text"

    fetched = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "rpc-2",
            "method": "tasks/get",
            "params": {"id": "a2a-test-weather"},
        },
    )
    assert fetched.status_code == 200
    fetched_task = fetched.json()["result"]
    assert fetched_task["kind"] == "task"
    assert fetched_task["id"] == "a2a-test-weather"
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
