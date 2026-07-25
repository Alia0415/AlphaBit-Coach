from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.core.contracts import ExecutionPlan
from backend.services.research_query_refiner import (
    ResearchQueryRefinement,
    ResearchQueryRefiner,
    ResearchQueryRefinerError,
)


def _plan() -> ExecutionPlan:
    return ExecutionPlan.model_validate(
        {
            "goal": "分析 000001.SZ 在 2024 年的价格表现",
            "intent": "按最终问题执行",
            "complexity": "low",
            "selected_agents": [
                {"agent": "research", "reason": "需要核对市场表现"}
            ],
            "steps": [
                {
                    "id": "research_1",
                    "agent": "research",
                    "objective": "分析价格表现",
                    "inputs": {
                        "symbols": ["000001.SZ"],
                        "start_date": "20240101",
                        "end_date": "20241231",
                        "fields": [],
                    },
                    "depends_on": [],
                    "expected_output": "价格表现证据",
                }
            ],
            "needs_clarification": False,
            "clarification_question": None,
        }
    )


class FakeArkClient:
    def __init__(self, payload: dict | Exception) -> None:
        self.payload = payload

    def chat_json(self, request):
        if isinstance(self.payload, Exception):
            raise self.payload
        return request.response_model.model_validate(self.payload)


def test_colloquial_query_is_rewritten_with_one_light_clarification() -> None:
    refiner = ResearchQueryRefiner(
        FakeArkClient(
            {
                "rewritten_query": (
                    "分析宁德时代的经营表现、成长能力、估值水平与主要风险"
                ),
                "requires_confirmation": True,
                "need_clarification": True,
                "clarification_type": "time_range",
            }
        )
    )

    result = refiner.refine(" 宁德时代最近怎么样 ")

    assert result.original_query == "宁德时代最近怎么样"
    assert "经营表现" in result.rewritten_query
    assert result.requires_confirmation is True
    assert result.need_clarification is True
    assert result.options == ["近3个月", "近1年", "近3年"]


def test_professional_query_proceeds_unchanged_without_confirmation() -> None:
    original = "分析贵州茅台（600519.SH）近三个财年的盈利能力与财务质量"
    refiner = ResearchQueryRefiner(
        FakeArkClient(
            {
                "rewritten_query": "模型不应静默替换这个专业问题",
                "requires_confirmation": False,
                "need_clarification": False,
                "clarification_type": None,
            }
        )
    )

    result = refiner.refine(original)

    assert result.rewritten_query == original
    assert result.requires_confirmation is False
    assert result.options == []


def test_refiner_failure_is_explicit_and_safe() -> None:
    refiner = ResearchQueryRefiner(FakeArkClient(RuntimeError("transport")))

    with pytest.raises(ResearchQueryRefinerError, match="直接使用原问题"):
        refiner.refine("宁德时代最近怎么样")


def test_rewrite_endpoint_returns_only_user_facing_fields() -> None:
    class StubRefiner:
        def refine(self, original_query: str) -> ResearchQueryRefinement:
            return ResearchQueryRefinement(
                original_query=original_query,
                rewritten_query="分析宁德时代近一年的经营表现与主要风险",
                requires_confirmation=True,
                need_clarification=True,
                clarification_type="time_range",
                options=["近3个月", "近1年", "近3年"],
            )

    with patch.object(main_module, "query_refiner", StubRefiner()):
        response = TestClient(main_module.app).post(
            "/api/research-query/rewrite",
            json={"original_query": "宁德时代最近怎么样"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "original_query": "宁德时代最近怎么样",
        "rewritten_query": "分析宁德时代近一年的经营表现与主要风险",
        "requires_confirmation": True,
        "need_clarification": True,
        "clarification_type": "time_range",
        "options": ["近3个月", "近1年", "近3年"],
    }


def test_final_query_has_priority_for_manager_and_persistence() -> None:
    calls: list[tuple[object, ...]] = []

    class CapturingManager:
        def create_plan(self, *args: object) -> ExecutionPlan:
            calls.append(args)
            return _plan()

    original = "平安银行最近咋样"
    rewritten = "分析平安银行近期的价格表现"
    final = "分析 000001.SZ 在 2024 年的价格表现"
    with patch.object(main_module, "manager", CapturingManager()):
        response = TestClient(main_module.app).post(
            "/api/tasks/sessions",
            json={
                "prompt": rewritten,
                "original_query": original,
                "rewritten_query": rewritten,
                "final_query": final,
            },
        )

    assert response.status_code == 200
    assert calls and calls[0][1] == final
    task_id = response.json()["task_id"]
    detail = TestClient(main_module.app).get(f"/api/tasks/{task_id}").json()
    assert detail["prompt"] == final
    assert detail["original_query"] == original
    assert detail["rewritten_query"] == rewritten
    assert detail["final_query"] == final
