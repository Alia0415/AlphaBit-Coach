"""Deterministic local market data used by the stock-chart demo mode.

The values are synthetic, generated from fixed parameters, and must never be
presented as live or historical exchange data.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


DEMO_DATA_SOURCE = "AlphaBit Coach Demo Dataset"
DEMO_END_DATE = date(2026, 7, 24)

DEMO_STOCK_CONFIG: dict[str, dict[str, float]] = {
    "000001.SZ": {"base": 11.2, "trend": 0.0014, "phase": 0.2, "volume": 72_000_000},
    "600519.SH": {"base": 1390.0, "trend": 0.0011, "phase": 1.4, "volume": 3_100_000},
    "300750.SZ": {"base": 235.0, "trend": -0.0002, "phase": 2.3, "volume": 18_000_000},
    "002594.SZ": {"base": 290.0, "trend": 0.0006, "phase": 0.8, "volume": 15_000_000},
    "601318.SH": {"base": 54.0, "trend": 0.0005, "phase": 1.9, "volume": 42_000_000},
    "600036.SH": {"base": 43.0, "trend": 0.0008, "phase": 2.8, "volume": 31_000_000},
    "000858.SZ": {"base": 134.0, "trend": -0.0001, "phase": 3.3, "volume": 8_500_000},
    "688981.SH": {"base": 92.0, "trend": 0.0017, "phase": 0.5, "volume": 49_000_000},
    "000300.SH": {"base": 4050.0, "trend": 0.0004, "phase": 1.1, "volume": 215_000_000},
    "000001.SH": {"base": 3520.0, "trend": 0.0003, "phase": 2.1, "volume": 390_000_000},
}


def _demo_config(symbol: str) -> dict[str, float] | None:
    configured = DEMO_STOCK_CONFIG.get(symbol)
    if configured is not None:
        return configured
    if len(symbol) != 9 or symbol[6:] not in {".SH", ".SZ"}:
        return None
    try:
        numeric = int(symbol[:6])
    except ValueError:
        return None
    return {
        "base": 8.0 + (numeric % 24_000) / 100,
        "trend": ((numeric % 19) - 9) / 12_000,
        "phase": (numeric % 31) / 5,
        "volume": float(8_000_000 + (numeric % 72_000_000)),
    }


def demo_daily_rows(symbol: str) -> list[dict[str, float | str]]:
    """Return a fixed set of weekday OHLCV rows for a supported symbol."""

    config = _demo_config(symbol)
    if config is None:
        return []
    days = _weekdays_ending(DEMO_END_DATE, 390)
    rows: list[dict[str, float | str]] = []
    previous_close = config["base"]
    for index, trading_day in enumerate(days):
        cycle = math.sin(index / 11 + config["phase"]) * 0.006
        slower_cycle = math.sin(index / 47 + config["phase"] / 2) * 0.003
        close = max(
            0.01,
            previous_close * (1 + config["trend"] + cycle + slower_cycle),
        )
        gap = math.sin(index / 7 + config["phase"]) * 0.0025
        open_price = max(0.01, previous_close * (1 + gap))
        spread = 0.004 + abs(math.cos(index / 9 + config["phase"])) * 0.006
        high = max(open_price, close) * (1 + spread)
        low = min(open_price, close) * (1 - spread * 0.82)
        volume_factor = 0.72 + abs(math.sin(index / 8 + config["phase"])) * 0.62
        rows.append(
            {
                "trade_date": trading_day.strftime("%Y%m%d"),
                "open": round(open_price, 3),
                "high": round(high, 3),
                "low": round(low, 3),
                "close": round(close, 3),
                "volume": int(config["volume"] * volume_factor),
            }
        )
        previous_close = close
    return rows


def demo_intraday_rows(symbol: str) -> list[dict[str, float | int]]:
    """Return one fixed trading day with 240 one-minute close/volume points."""

    config = _demo_config(symbol)
    if config is None:
        return []
    daily = demo_daily_rows(symbol)
    previous_close = float(daily[-2]["close"])
    latest_close = float(daily[-1]["close"])
    trading_minutes = [
        datetime.combine(DEMO_END_DATE, time(9, 30)) + timedelta(minutes=i)
        for i in range(120)
    ]
    trading_minutes.extend(
        datetime.combine(DEMO_END_DATE, time(13, 0)) + timedelta(minutes=i)
        for i in range(120)
    )
    zone = ZoneInfo("Asia/Shanghai")
    rows: list[dict[str, float | int]] = []
    for index, minute in enumerate(trading_minutes):
        progress = index / max(1, len(trading_minutes) - 1)
        bridge = previous_close + (latest_close - previous_close) * progress
        wave = math.sin(index / 13 + config["phase"]) * previous_close * 0.0017
        value = max(0.01, bridge + wave)
        volume_factor = 0.7 + abs(math.sin(index / 17 + config["phase"])) * 0.8
        rows.append(
            {
                "time": int(minute.replace(tzinfo=zone).timestamp()),
                "close": round(value, 3),
                "volume": int(config["volume"] / 240 * volume_factor),
            }
        )
    return rows


def _weekdays_ending(end: date, count: int) -> list[date]:
    values: list[date] = []
    cursor = end
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(values))
