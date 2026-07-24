"""Validated user investment profile facts and deterministic derived metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


MAX_CNY_AMOUNT = 1_000_000_000_000
PROFILE_FACT_FIELDS = (
    "investment_goal",
    "investment_horizon_months",
    "liquidity_need",
    "monthly_after_tax_income_cny",
    "monthly_essential_expenses_cny",
    "monthly_debt_payment_cny",
    "emergency_fund_cny",
    "planned_large_expenses_cny",
    "planned_large_expenses_within_months",
    "available_investment_funds_cny",
    "max_acceptable_loss_ratio",
    "investment_experience",
    "existing_positions",
)


class ExistingPosition(BaseModel):
    """One user-reported holding without any inferred valuation."""

    model_config = ConfigDict(extra="forbid")

    asset_name: str = Field(min_length=1, max_length=100)
    asset_type: str = Field(min_length=1, max_length=50)
    amount_cny: int | None = Field(default=None, ge=0, le=MAX_CNY_AMOUNT)
    portfolio_ratio: float | None = Field(default=None, ge=0, le=1)

    @field_validator("asset_name", "asset_type")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("持仓名称和类型不能为空")
        return normalized

    @model_validator(mode="after")
    def amount_or_ratio_is_required(self) -> "ExistingPosition":
        if self.amount_cny is None and self.portfolio_ratio is None:
            raise ValueError("每项持仓至少填写大致金额或占比")
        return self


class UserInvestmentProfile(BaseModel):
    """User-confirmed facts. Missing values remain ``None`` and are never guessed."""

    model_config = ConfigDict(extra="forbid")

    investment_goal: str | None = Field(default=None, max_length=500)
    investment_horizon_months: int | None = Field(default=None, ge=1, le=1_200)
    liquidity_need: Literal["high", "medium", "low"] | None = None

    monthly_after_tax_income_cny: int | None = Field(
        default=None, ge=0, le=MAX_CNY_AMOUNT
    )
    monthly_essential_expenses_cny: int | None = Field(
        default=None, ge=0, le=MAX_CNY_AMOUNT
    )
    monthly_debt_payment_cny: int | None = Field(
        default=None, ge=0, le=MAX_CNY_AMOUNT
    )

    emergency_fund_cny: int | None = Field(default=None, ge=0, le=MAX_CNY_AMOUNT)
    planned_large_expenses_cny: int | None = Field(
        default=None, ge=0, le=MAX_CNY_AMOUNT
    )
    planned_large_expenses_within_months: int | None = Field(
        default=None, ge=0, le=1_200
    )

    available_investment_funds_cny: int | None = Field(
        default=None, ge=0, le=MAX_CNY_AMOUNT
    )
    max_acceptable_loss_ratio: float | None = Field(default=None, ge=0, le=1)

    investment_experience: Literal["none", "basic", "experienced"] | None = None
    existing_positions: list[ExistingPosition] | None = Field(
        default=None, max_length=100
    )

    onboarding_completed: bool = False
    profile_version: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("investment_goal")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_must_include_timezone(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("画像时间必须包含时区")
        return value

    @model_validator(mode="after")
    def completed_profile_has_timestamps(self) -> "UserInvestmentProfile":
        if self.onboarding_completed and (
            self.created_at is None or self.updated_at is None
        ):
            raise ValueError("已完成建档的画像必须包含创建和更新时间")
        if (
            self.created_at is not None
            and self.updated_at is not None
            and self.updated_at < self.created_at
        ):
            raise ValueError("画像更新时间不能早于创建时间")
        return self

    @computed_field(return_type=int | None)
    @property
    def monthly_surplus_cny(self) -> int | None:
        values = (
            self.monthly_after_tax_income_cny,
            self.monthly_essential_expenses_cny,
            self.monthly_debt_payment_cny,
        )
        if any(value is None for value in values):
            return None
        income, expenses, debt = values
        assert income is not None and expenses is not None and debt is not None
        return income - expenses - debt

    @computed_field(return_type=float | None)
    @property
    def emergency_fund_months(self) -> float | None:
        if (
            self.emergency_fund_cny is None
            or self.monthly_essential_expenses_cny is None
            or self.monthly_essential_expenses_cny == 0
        ):
            return None
        return self.emergency_fund_cny / self.monthly_essential_expenses_cny

    @computed_field(return_type=float | None)
    @property
    def debt_payment_ratio(self) -> float | None:
        if (
            self.monthly_debt_payment_cny is None
            or self.monthly_after_tax_income_cny is None
            or self.monthly_after_tax_income_cny == 0
        ):
            return None
        return self.monthly_debt_payment_cny / self.monthly_after_tax_income_cny

    @computed_field(return_type=float | None)
    @property
    def known_asset_concentration(self) -> float | None:
        positions = self.existing_positions
        if positions is None:
            return None
        if not positions:
            return 0.0
        known_ratios = [
            position.portfolio_ratio
            for position in positions
            if position.portfolio_ratio is not None
        ]
        if known_ratios:
            return max(known_ratios)
        if any(position.amount_cny is None for position in positions):
            return None
        total = sum(position.amount_cny or 0 for position in positions)
        if total == 0:
            return None
        return max((position.amount_cny or 0) / total for position in positions)

    @computed_field(return_type=float)
    @property
    def profile_completeness(self) -> float:
        answered = sum(
            getattr(self, field_name) is not None
            for field_name in PROFILE_FACT_FIELDS
        )
        return answered / len(PROFILE_FACT_FIELDS)

    def missing_fields(self) -> list[str]:
        """Return unanswered fact fields without treating explicit zero as missing."""

        return [
            field_name
            for field_name in PROFILE_FACT_FIELDS
            if getattr(self, field_name) is None
        ]
