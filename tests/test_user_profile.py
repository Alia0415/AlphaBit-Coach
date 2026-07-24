from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import main as main_module
from backend.agents.manager_agent import ManagerAgent
from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import ExecutionPlan
from backend.core.user_profile import ExistingPosition, UserInvestmentProfile


NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def _completed_profile(**overrides: object) -> UserInvestmentProfile:
    payload: dict[str, object] = {
        "investment_goal": "为五年后的购房首付做准备",
        "investment_horizon_months": 60,
        "liquidity_need": "medium",
        "monthly_after_tax_income_cny": 20_000,
        "monthly_essential_expenses_cny": 8_000,
        "monthly_debt_payment_cny": 2_000,
        "emergency_fund_cny": 48_000,
        "planned_large_expenses_cny": 30_000,
        "planned_large_expenses_within_months": 10,
        "available_investment_funds_cny": 100_000,
        "max_acceptable_loss_ratio": 0.1,
        "investment_experience": "basic",
        "existing_positions": [
            {
                "asset_name": "沪深300指数基金",
                "asset_type": "基金",
                "amount_cny": 60_000,
                "portfolio_ratio": 0.6,
            },
            {
                "asset_name": "银行存款",
                "asset_type": "存款",
                "amount_cny": 40_000,
                "portfolio_ratio": 0.4,
            },
        ],
        "onboarding_completed": True,
        "profile_version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(overrides)
    return UserInvestmentProfile.model_validate(payload)


def test_missing_values_remain_none_and_are_not_coerced_to_zero() -> None:
    profile = UserInvestmentProfile()

    assert profile.monthly_after_tax_income_cny is None
    assert profile.monthly_surplus_cny is None
    assert profile.emergency_fund_months is None
    assert profile.existing_positions is None
    assert profile.profile_completeness == 0


def test_cashflow_and_financial_buffer_metrics_are_deterministic() -> None:
    profile = _completed_profile()

    assert profile.monthly_surplus_cny == 10_000
    assert profile.emergency_fund_months == 6
    assert profile.debt_payment_ratio == pytest.approx(0.1)
    assert profile.known_asset_concentration == pytest.approx(0.6)
    assert profile.profile_completeness == 1


def test_future_large_expense_and_zero_values_are_preserved() -> None:
    profile = _completed_profile(
        planned_large_expenses_cny=0,
        planned_large_expenses_within_months=0,
        monthly_debt_payment_cny=0,
    )

    dumped = profile.model_dump(mode="json")
    assert dumped["planned_large_expenses_cny"] == 0
    assert dumped["planned_large_expenses_within_months"] == 0
    assert dumped["monthly_debt_payment_cny"] == 0
    assert profile.monthly_surplus_cny == 12_000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("monthly_after_tax_income_cny", -1),
        ("monthly_essential_expenses_cny", 1.5),
        ("max_acceptable_loss_ratio", -0.01),
        ("max_acceptable_loss_ratio", 1.01),
        ("investment_horizon_months", 0),
    ],
)
def test_amount_month_and_percentage_validation(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        UserInvestmentProfile.model_validate({field: value})


def test_no_positions_and_unanswered_positions_remain_distinct() -> None:
    unanswered = UserInvestmentProfile(existing_positions=None)
    explicitly_none = UserInvestmentProfile(existing_positions=[])

    assert unanswered.existing_positions is None
    assert unanswered.known_asset_concentration is None
    assert explicitly_none.existing_positions == []
    assert explicitly_none.known_asset_concentration == 0


def test_position_requires_amount_or_ratio_and_can_derive_from_amounts() -> None:
    with pytest.raises(ValidationError, match="大致金额或占比"):
        ExistingPosition(
            asset_name="示例基金",
            asset_type="基金",
            amount_cny=None,
            portfolio_ratio=None,
        )

    profile = UserInvestmentProfile(
        existing_positions=[
            {
                "asset_name": "基金 A",
                "asset_type": "基金",
                "amount_cny": 75_000,
                "portfolio_ratio": None,
            },
            {
                "asset_name": "基金 B",
                "asset_type": "基金",
                "amount_cny": 25_000,
                "portfolio_ratio": None,
            },
        ]
    )
    assert profile.known_asset_concentration == pytest.approx(0.75)


@pytest.mark.parametrize(
    "sensitive_field",
    ["name", "id_card_number", "bank_card_number", "account_number", "address"],
)
def test_profile_rejects_sensitive_identity_fields(sensitive_field: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        UserInvestmentProfile.model_validate({sensitive_field: "should-not-be-stored"})


def test_completed_onboarding_requires_timestamps() -> None:
    with pytest.raises(ValidationError, match="创建和更新时间"):
        UserInvestmentProfile(onboarding_completed=True)


def test_profile_timestamps_require_timezone() -> None:
    with pytest.raises(ValidationError, match="必须包含时区"):
        UserInvestmentProfile(
            onboarding_completed=True,
            created_at=datetime(2026, 7, 24, 8, 0),
            updated_at=datetime(2026, 7, 24, 8, 0),
        )


class RecordingManager:
    def __init__(self) -> None:
        self.profile: UserInvestmentProfile | None = None

    def create_plan(
        self,
        prompt: str,
        user_profile: UserInvestmentProfile | None = None,
    ) -> ExecutionPlan:
        self.profile = user_profile
        return ExecutionPlan(
            goal=prompt,
            intent="画像合同验证",
            complexity="low",
            selected_agents=[],
            steps=[],
            needs_clarification=True,
            clarification_question="请补充当前任务直接需要的一项信息。",
        )


def test_tasks_api_accepts_and_revalidates_profile_snapshot() -> None:
    manager = RecordingManager()
    with patch.object(main_module, "manager", manager):
        response = TestClient(main_module.app).post(
            "/api/tasks",
            json={
                "prompt": "分析新能源行业是否适合我的研究目标",
                "user_profile": _completed_profile().model_dump(
                    mode="json", exclude_computed_fields=True
                ),
            },
        )

    assert response.status_code == 200
    assert isinstance(manager.profile, UserInvestmentProfile)
    assert manager.profile.monthly_surplus_cny == 10_000
    assert response.json()["aggregation"]["completion_status"] == "needs_clarification"


def test_tasks_api_rejects_invalid_profile_before_manager_or_external_calls() -> None:
    manager = RecordingManager()
    payload = _completed_profile().model_dump(
        mode="json", exclude_computed_fields=True
    )
    payload["max_acceptable_loss_ratio"] = 1.5
    with patch.object(main_module, "manager", manager):
        response = TestClient(main_module.app).post(
            "/api/tasks",
            json={"prompt": "测试", "user_profile": payload},
        )

    assert response.status_code == 422
    assert manager.profile is None


class PromptRecordingClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def chat(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_manager_receives_profile_facts_without_creating_profile_agent() -> None:
    response = json.dumps(
        {
            "goal": "研究行业",
            "intent": "行业研究",
            "complexity": "low",
            "selected_agents": [
                {"agent": "research", "reason": "需要行业事实研究"}
            ],
            "steps": [
                {
                    "id": "research_1",
                    "agent": "research",
                    "objective": "研究新能源行业",
                    "inputs": {
                        "industry": "新能源",
                        "time_range": "未来五年",
                        "research_goal": "了解行业事实",
                    },
                    "depends_on": [],
                    "expected_output": "行业事实与证据边界",
                }
            ],
            "needs_clarification": False,
            "clarification_question": None,
        },
        ensure_ascii=False,
    )
    client = PromptRecordingClient(response)

    plan = ManagerAgent(client=client).create_plan(
        "研究新能源行业",
        _completed_profile(),
    )

    assert [selection.agent.value for selection in plan.selected_agents] == ["research"]
    assert '"monthly_surplus_cny": 10000' in client.prompts[0]
    assert "不得创建 profile" in client.prompts[0]
    assert "画像信息不足：" in client.prompts[0]
    assert "不得规划或生成个性化买入、卖出或资产配置建议" in client.prompts[0]
    assert "profile" not in {agent_id.value for agent_id in AgentRegistry().ids()}
