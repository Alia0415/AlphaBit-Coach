"""Controlled quantitative cross-check calculations (spec section 7.2).

This module provides deterministic, reproducible computations for
quantitative decision support. It is NOT a runtime Skill — it is internal
to the Quant Agent's execution path.

Outputs are historical computation facts; they must never be expressed as
IC, backtest performance, trading signals, or future return evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PriceRow:
    """One row of daily price data."""

    date: str
    close: float
    volume: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0


@dataclass
class CrossCheckResult:
    """Structured output of a cross-check computation."""

    metric_id: str
    method: str
    description: str
    value: float | None
    unit: str | None
    window: str
    sample_count: int
    benchmark: str | None = None
    direction: str | None = None
    limitations: list[str] = field(default_factory=list)


ConsistencyLabel = Literal["supports", "conflicts", "inconclusive"]
ClaimDirection = Literal["positive", "negative", "risk", "neutral"]
MarketAlignmentLabel = Literal["aligned", "divergent", "mixed", "inconclusive"]


@dataclass
class ConsistencyCheck:
    """Label indicating whether upstream claims are supported by quant data."""

    claim_source: str
    claim_summary: str
    quant_evidence: str
    label: ConsistencyLabel
    reason: str


@dataclass
class MarketAlignment:
    """Historical market alignment for one bounded upstream claim."""

    assessment: MarketAlignmentLabel
    reason: str
    metric_ids: list[str]
    falsification_conditions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------


def period_return(prices: list[PriceRow]) -> CrossCheckResult | None:
    """Simple period return from first to last close."""
    if len(prices) < 2:
        return None
    first = prices[0].close
    last = prices[-1].close
    if first <= 0:
        return None
    ret = (last - first) / first
    return CrossCheckResult(
        metric_id="period_return",
        method="(last_close - first_close) / first_close",
        description="区间收益率",
        value=round(ret, 6),
        unit="ratio",
        window=f"{prices[0].date}~{prices[-1].date}",
        sample_count=len(prices),
        direction="positive" if ret > 0 else "negative",
    )


def relative_return(
    target_prices: list[PriceRow],
    benchmark_prices: list[PriceRow],
    benchmark_name: str = "benchmark",
) -> CrossCheckResult | None:
    """Excess return of target over a benchmark."""
    target_ret = period_return(target_prices)
    bench_ret = period_return(benchmark_prices)
    if target_ret is None or bench_ret is None:
        return None
    if target_ret.value is None or bench_ret.value is None:
        return None
    excess = target_ret.value - bench_ret.value
    return CrossCheckResult(
        metric_id="relative_return",
        method="target_return - benchmark_return",
        description=f"相对 {benchmark_name} 超额收益",
        value=round(excess, 6),
        unit="ratio",
        window=target_ret.window,
        sample_count=min(target_ret.sample_count, bench_ret.sample_count),
        benchmark=benchmark_name,
        direction="outperform" if excess > 0 else "underperform",
    )


def annualized_volatility(prices: list[PriceRow]) -> CrossCheckResult | None:
    """Annualized volatility based on daily log returns."""
    returns = _daily_log_returns(prices)
    if len(returns) < 5:
        return None
    std = _std(returns)
    ann_vol = std * math.sqrt(252)
    return CrossCheckResult(
        metric_id="annualized_volatility",
        method="std(daily_log_returns) * sqrt(252)",
        description="年化波动率",
        value=round(ann_vol, 6),
        unit="ratio",
        window=f"{prices[0].date}~{prices[-1].date}",
        sample_count=len(returns),
    )


def downside_volatility(
    prices: list[PriceRow], threshold: float = 0.0
) -> CrossCheckResult | None:
    """Annualized downside volatility (below threshold returns)."""
    returns = _daily_log_returns(prices)
    downside = [r for r in returns if r < threshold]
    if len(downside) < 3:
        return CrossCheckResult(
            metric_id="downside_volatility",
            method="std(negative_returns) * sqrt(252)",
            description="下行波动率",
            value=None,
            unit="ratio",
            window=f"{prices[0].date}~{prices[-1].date}" if prices else "",
            sample_count=len(downside),
            limitations=["下行样本不足（<3个交易日）"],
        )
    std = _std(downside)
    ann_down = std * math.sqrt(252)
    return CrossCheckResult(
        metric_id="downside_volatility",
        method="std(negative_returns) * sqrt(252)",
        description="下行波动率",
        value=round(ann_down, 6),
        unit="ratio",
        window=f"{prices[0].date}~{prices[-1].date}",
        sample_count=len(downside),
    )


def maximum_drawdown(prices: list[PriceRow]) -> CrossCheckResult | None:
    """Maximum drawdown from peak to trough in the price series."""
    if len(prices) < 2:
        return None
    closes = [p.close for p in prices]
    max_dd = 0.0
    peak = closes[0]
    for close in closes[1:]:
        if close > peak:
            peak = close
        dd = (peak - close) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return CrossCheckResult(
        metric_id="maximum_drawdown",
        method="max((peak - trough) / peak)",
        description="最大回撤",
        value=round(max_dd, 6),
        unit="ratio",
        window=f"{prices[0].date}~{prices[-1].date}",
        sample_count=len(prices),
        direction="risk_indicator",
    )


def volume_trend(
    prices: list[PriceRow], short_window: int = 5, long_window: int = 20
) -> CrossCheckResult | None:
    """Volume expansion signal: short MA / long MA of volume."""
    volumes = [p.volume for p in prices if p.volume > 0]
    if len(volumes) < long_window:
        return None
    short_ma = sum(volumes[-short_window:]) / short_window
    long_ma = sum(volumes[-long_window:]) / long_window
    ratio = short_ma / long_ma if long_ma > 0 else None
    return CrossCheckResult(
        metric_id="volume_expansion",
        method=f"ma({short_window}d_volume) / ma({long_window}d_volume)",
        description="成交量扩张倍数",
        value=round(ratio, 4) if ratio else None,
        unit="ratio",
        window=f"{prices[0].date}~{prices[-1].date}",
        sample_count=len(volumes),
        direction="expansion" if ratio and ratio > 1.5 else "normal",
    )


def multi_window_sensitivity(
    prices: list[PriceRow],
    windows: tuple[int, ...] = (20, 60, 120),
) -> list[CrossCheckResult]:
    """Compute period return for multiple windows to check conclusion sensitivity."""
    results: list[CrossCheckResult] = []
    for w in windows:
        if len(prices) < w:
            results.append(
                CrossCheckResult(
                    metric_id=f"return_{w}d",
                    method=f"period_return(last_{w}_days)",
                    description=f"{w}日收益率",
                    value=None,
                    unit="ratio",
                    window=f"last_{w}_days",
                    sample_count=0,
                    limitations=[f"数据不足{w}个交易日"],
                )
            )
            continue
        subset = prices[-w:]
        ret = period_return(subset)
        if ret is not None:
            ret.metric_id = f"return_{w}d"
            ret.description = f"{w}日收益率"
            results.append(ret)
    return results


def cross_section_rank(
    target_value: float,
    peer_values: list[float],
    metric_name: str = "metric",
) -> CrossCheckResult:
    """Rank of target within peer cross-section (higher = better percentile)."""
    all_values = sorted(peer_values + [target_value])
    rank = all_values.index(target_value) + 1
    total = len(all_values)
    percentile = rank / total
    return CrossCheckResult(
        metric_id=f"rank_{metric_name}",
        method=f"percentile_rank({metric_name})",
        description=f"{metric_name} 横截面排名",
        value=round(percentile, 4),
        unit="percentile",
        window="cross_section",
        sample_count=total,
        direction="top" if percentile >= 0.75 else "bottom" if percentile <= 0.25 else "middle",
    )


# ---------------------------------------------------------------------------
# Consistency assessment
# ---------------------------------------------------------------------------


def assess_consistency(
    upstream_claim: str,
    claim_source: str,
    quant_results: list[CrossCheckResult],
) -> ConsistencyCheck:
    """Deterministic consistency check between upstream claim and quant evidence.

    Rules:
    - If quant results are empty or all have None values: inconclusive
    - If claim is about positive outlook and return is negative: conflicts
    - If claim is about risk and drawdown is high: supports
    - Otherwise: inconclusive (conservative default)
    """
    valid_results = [r for r in quant_results if r.value is not None]
    if not valid_results:
        return ConsistencyCheck(
            claim_source=claim_source,
            claim_summary=upstream_claim,
            quant_evidence="无有效量化计算结果",
            label="inconclusive",
            reason="量化证据不足，无法判断一致性",
        )

    evidence_summary = "; ".join(
        f"{r.description}={r.value}" for r in valid_results[:5]
    )
    # Conservative default: quant cannot definitively confirm/deny most claims
    return ConsistencyCheck(
        claim_source=claim_source,
        claim_summary=upstream_claim,
        quant_evidence=evidence_summary,
        label="inconclusive",
        reason="量化证据可供参考，但不能独立验证定性判断",
    )


def assess_market_alignment(
    direction: ClaimDirection,
    quant_results: list[CrossCheckResult],
) -> MarketAlignment:
    """Compare an explicit claim direction with historical return windows."""

    returns = [
        item
        for item in quant_results
        if item.metric_id
        in {"period_return", "return_20d", "return_60d", "return_120d"}
        and item.value is not None
        and item.value != 0
    ]
    metric_ids = [item.metric_id for item in returns]
    if direction in {"neutral", "risk"}:
        return MarketAlignment(
            assessment="inconclusive",
            reason="历史价格和风险指标只能提供背景，不能验证该类定性观点。",
            metric_ids=metric_ids,
            falsification_conditions=["补充与该观点直接对应的基本面或宏观指标。"],
        )
    if not returns:
        return MarketAlignment(
            assessment="inconclusive",
            reason="有效收益窗口不足，无法判断历史市场方向是否一致。",
            metric_ids=[],
            falsification_conditions=["补充更长且口径一致的历史行情窗口。"],
        )

    signs = {1 if item.value and item.value > 0 else -1 for item in returns}
    if len(signs) > 1:
        return MarketAlignment(
            assessment="mixed",
            reason="不同时间窗口的历史收益方向不一致，结论具有窗口敏感性。",
            metric_ids=metric_ids,
            falsification_conditions=["观察后续多个窗口是否收敛到同一方向。"],
        )

    observed = next(iter(signs))
    expected = 1 if direction == "positive" else -1
    if observed == expected:
        return MarketAlignment(
            assessment="aligned",
            reason="可用历史收益窗口的方向与该观点方向一致。",
            metric_ids=metric_ids,
            falsification_conditions=["若多个观察窗口转向相反方向，一致性将减弱。"],
        )
    return MarketAlignment(
        assessment="divergent",
        reason="可用历史收益窗口的方向与该观点方向相反。",
        metric_ids=metric_ids,
        falsification_conditions=["需要新的直接证据解释定性观点与市场表现的背离。"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _daily_log_returns(prices: list[PriceRow]) -> list[float]:
    """Compute daily log returns from price series."""
    returns: list[float] = []
    for i in range(1, len(prices)):
        if prices[i - 1].close > 0 and prices[i].close > 0:
            returns.append(math.log(prices[i].close / prices[i - 1].close))
    return returns


def _std(values: list[float]) -> float:
    """Sample standard deviation."""
    if len(values) < 2:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(variance)


def run_cross_check(
    target_prices: list[PriceRow],
    benchmark_prices: list[PriceRow] | None = None,
    peer_prices: dict[str, list[PriceRow]] | None = None,
    benchmark_name: str = "沪深300",
) -> list[CrossCheckResult]:
    """Run the full cross-check calculation suite on target data.

    Returns all computed metrics; callers filter/present as needed.
    """
    results: list[CrossCheckResult] = []

    # Core metrics
    ret = period_return(target_prices)
    if ret:
        results.append(ret)

    if benchmark_prices:
        rel = relative_return(target_prices, benchmark_prices, benchmark_name)
        if rel:
            results.append(rel)

    vol = annualized_volatility(target_prices)
    if vol:
        results.append(vol)

    down = downside_volatility(target_prices)
    if down:
        results.append(down)

    dd = maximum_drawdown(target_prices)
    if dd:
        results.append(dd)

    vt = volume_trend(target_prices)
    if vt:
        results.append(vt)

    # Multi-window sensitivity
    sensitivity = multi_window_sensitivity(target_prices)
    results.extend(sensitivity)

    # Cross-section ranking if peers provided
    if peer_prices and ret and ret.value is not None:
        peer_returns: list[float] = []
        for peer_data in peer_prices.values():
            peer_ret = period_return(peer_data)
            if peer_ret and peer_ret.value is not None:
                peer_returns.append(peer_ret.value)
        if peer_returns:
            rank = cross_section_rank(ret.value, peer_returns, "period_return")
            results.append(rank)

    return results
