"""Pinned executable adapter for deterministic portfolio liquidity stress."""

from __future__ import annotations

import importlib.util
import math
from collections.abc import Mapping
from types import ModuleType
from typing import Any

from backend.skills.contracts import (
    SkillInvocation,
    SkillResult,
    SkillSpec,
    SkillStatus,
)
from backend.skills.loaders.instruction_skill_loader import (
    RuntimeSkillLocator,
    SkillUnavailableError,
)


class PortfolioLiquidityStressAdapter:
    """Call only the locked ``analyze`` function; never the upstream demo CLI."""

    def __init__(self, *, locator: RuntimeSkillLocator) -> None:
        self._locator = locator

    def __call__(
        self,
        invocation: SkillInvocation,
        spec: SkillSpec,
    ) -> SkillResult:
        try:
            entrypoint, provenance = self._locator.resolve_entrypoint(spec)
        except SkillUnavailableError as exc:
            return _unavailable(invocation, str(exc))
        except ValueError:
            return _failed(invocation, "流动性压力测试路径未通过安全校验。")

        holdings = invocation.inputs.get("holdings")
        if not isinstance(holdings, list) or not holdings:
            return _failed(
                invocation,
                "流动性压力测试需要非空 holdings，且不得使用上游 DEMO。",
                provenance=provenance,
            )
        rows: list[dict[str, str]] = []
        for item in holdings:
            if not isinstance(item, Mapping):
                return _failed(
                    invocation,
                    "holdings 每一项都必须是对象。",
                    provenance=provenance,
                )
            rows.append(
                {
                    key: str(item.get(key, ""))
                    for key in (
                        "symbol",
                        "position_value",
                        "adv",
                        "spread_bps",
                        "volatility",
                    )
                }
            )
        try:
            participation = _finite(
                invocation.inputs.get("participation", 0.1),
                "participation",
            )
            volume_shock = _finite(
                invocation.inputs.get("volume_shock", 0.5),
                "volume_shock",
            )
            horizon_days = int(invocation.inputs.get("horizon_days", 5))
            eta = _finite(invocation.inputs.get("eta", 0.5), "eta")
            raw_redemption = invocation.inputs.get("redemption_value")
            redemption = (
                None
                if raw_redemption in (None, "")
                else _finite(raw_redemption, "redemption_value")
            )
            module = _load_module(entrypoint)
            raw_result = module.analyze(
                rows,
                participation,
                volume_shock,
                horizon_days,
                eta,
                redemption,
            )
            report = module.build_report(raw_result)
        except (TypeError, ValueError, OverflowError):
            return _failed(
                invocation,
                "流动性压力测试输入或计算参数无效。",
                provenance=provenance,
            )
        except Exception:
            return _failed(
                invocation,
                "锁定的流动性压力测试执行失败。",
                provenance=provenance,
            )
        if not isinstance(report, dict):
            return _failed(
                invocation,
                "流动性压力测试未返回预期报告。",
                provenance=provenance,
            )
        if report.get("status") == "insufficient-evidence":
            return _failed(
                invocation,
                "持仓或市场输入不足，未执行流动性压力计算。",
                provenance=provenance,
            )

        domain = report.get("domain_result", {})
        evidence = (
            list(domain.get("details", []))
            if isinstance(domain, Mapping)
            and isinstance(domain.get("details"), list)
            else []
        )
        return SkillResult(
            invocation_id=invocation.invocation_id,
            skill_id=invocation.skill_id,
            status=SkillStatus.COMPLETED,
            summary=(
                f"已对 {len(rows)} 个调用方提供的持仓执行流动性压力情景。"
            ),
            data={
                "report": report,
                "validation_status": "scenario_estimate_not_validated",
            },
            evidence=[
                {"type": "liquidity_stress_position", **item}
                for item in evidence
                if isinstance(item, Mapping)
            ],
            assumptions=[
                "持仓市值、ADV、价差和波动率由调用方提供且口径一致。",
                "参与率、成交量冲击和冲击系数仅是情景参数。",
            ],
            limitations=[
                "结果是确定性情景估计，不是实际成交保证或交易建议。",
                "未接入账户或券商持仓；不会读取或使用上游 DEMO 数据。",
            ],
            provenance=provenance,
        )


def _finite(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _load_module(entrypoint: Any) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "alphaos_runtime_portfolio_liquidity_stress",
        entrypoint,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to construct module loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "analyze", None)) or not callable(
        getattr(module, "build_report", None)
    ):
        raise RuntimeError("Approved module is missing required callables")
    return module


def _failed(
    invocation: SkillInvocation,
    error: str,
    *,
    provenance: dict[str, Any] | None = None,
) -> SkillResult:
    return SkillResult(
        invocation_id=invocation.invocation_id,
        skill_id=invocation.skill_id,
        status=SkillStatus.FAILED,
        summary="组合流动性压力测试未成功完成。",
        limitations=[error],
        provenance=provenance or {},
        error=error,
    )


def _unavailable(invocation: SkillInvocation, error: str) -> SkillResult:
    return SkillResult(
        invocation_id=invocation.invocation_id,
        skill_id=invocation.skill_id,
        status=SkillStatus.UNAVAILABLE,
        summary="组合流动性 Runtime Skill 未安装或不可用。",
        limitations=[error],
        error=error,
    )
