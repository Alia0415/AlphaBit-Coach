from __future__ import annotations

import math

import pytest

from backend.services.stock_chart_service import (
    ChartRequest,
    StockChartService,
    calculate_ma,
    sanitize_candles,
)


class _DemoClient:
    configured = False


def test_valid_demo_chart_returns_expected_payload() -> None:
    service = StockChartService(_DemoClient())  # type: ignore[arg-type]

    payload = service.chart(
        ChartRequest(
            symbol="300750.SZ",
            period="1d",
            range_name="1y",
            force_demo=True,
        )
    )

    assert payload["symbol"] == "300750.SZ"
    assert payload["name"] == "宁德时代"
    assert 200 <= len(payload["candles"]) <= 500
    assert payload["is_demo"] is True


def test_candles_are_sorted_and_duplicate_times_keep_last_valid_row() -> None:
    rows = [
        {"trade_date": "20260103", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100},
        {"trade_date": "20260102", "open": 8, "high": 10, "low": 7, "close": 9, "volume": 90},
        {"trade_date": "20260103", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 120},
    ]

    candles = sanitize_candles(rows)

    assert [row["time"] for row in candles] == ["2026-01-02", "2026-01-03"]
    assert candles[-1]["close"] == 12
    assert candles[-1]["volume"] == 120


def test_invalid_ohlc_and_non_finite_values_are_filtered() -> None:
    rows = [
        {"trade_date": "20260101", "open": 10, "high": 9, "low": 8, "close": 10, "volume": 100},
        {"trade_date": "20260102", "open": 10, "high": 12, "low": 11, "close": 10, "volume": 100},
        {"trade_date": "20260103", "open": 10, "high": 12, "low": 9, "close": math.nan, "volume": 100},
        {"trade_date": "20260104", "open": 10, "high": 12, "low": 9, "close": 11, "volume": -1},
        {"trade_date": "20260105", "open": "10", "high": "12", "low": "9", "close": "11", "volume": "100"},
    ]

    candles = sanitize_candles(rows)

    assert len(candles) == 1
    assert candles[0]["time"] == "2026-01-05"


def test_ma5_ma10_ma20_are_calculated_deterministically() -> None:
    candles = [
        {
            "time": f"2026-01-{index:02d}",
            "open": index,
            "high": index,
            "low": index,
            "close": float(index),
            "volume": 1,
        }
        for index in range(1, 21)
    ]

    ma5 = calculate_ma(candles, 5)
    ma10 = calculate_ma(candles, 10)
    ma20 = calculate_ma(candles, 20)

    assert ma5[0] == {"time": "2026-01-05", "value": pytest.approx(3)}
    assert ma5[-1] == {"time": "2026-01-20", "value": pytest.approx(18)}
    assert ma10[-1] == {"time": "2026-01-20", "value": pytest.approx(15.5)}
    assert ma20 == [{"time": "2026-01-20", "value": pytest.approx(10.5)}]


def test_ma_returns_empty_array_when_data_is_insufficient() -> None:
    candles = [
        {"time": "2026-01-01", "close": 10.0},
        {"time": "2026-01-02", "close": 11.0},
    ]

    assert calculate_ma(candles, 5) == []
    assert calculate_ma(candles, 10) == []
    assert calculate_ma(candles, 20) == []


def test_demo_stock_switch_returns_distinct_price_series() -> None:
    service = StockChartService(_DemoClient())  # type: ignore[arg-type]

    first = service.chart(ChartRequest("000001.SZ", "1d", "3m", True))
    second = service.chart(ChartRequest("600519.SH", "1d", "3m", True))

    assert first["candles"] != second["candles"]
    assert first["metrics"]["latest_close"] != second["metrics"]["latest_close"]
