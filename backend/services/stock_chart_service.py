"""Stock library and deterministic chart-data preparation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import stdev
from typing import Any, Iterable

from backend.demo_stock_data import (
    DEMO_DATA_SOURCE,
    demo_daily_rows,
    demo_intraday_rows,
)
from backend.services.pandadata_client import PandaDataClient


STOCK_SYMBOL_PATTERN = re.compile(r"^\d{6}\.(?:SH|SZ)$")
SUPPORTED_PERIODS = frozenset({"1m", "1d", "1w", "1mo"})
PERIOD_LIMITS = {"1d": 500, "1w": 260, "1mo": 120}

DEFAULT_STOCKS: tuple[dict[str, str], ...] = (
    {"symbol": "000001.SZ", "name": "平安银行", "market": "SZ"},
    {"symbol": "600519.SH", "name": "贵州茅台", "market": "SH"},
    {"symbol": "300750.SZ", "name": "宁德时代", "market": "SZ"},
    {"symbol": "002594.SZ", "name": "比亚迪", "market": "SZ"},
    {"symbol": "601318.SH", "name": "中国平安", "market": "SH"},
    {"symbol": "600036.SH", "name": "招商银行", "market": "SH"},
    {"symbol": "000858.SZ", "name": "五粮液", "market": "SZ"},
    {"symbol": "688981.SH", "name": "中芯国际", "market": "SH"},
    {"symbol": "000300.SH", "name": "沪深300", "market": "SH"},
    {"symbol": "000001.SH", "name": "上证指数", "market": "SH"},
)


class StockChartError(RuntimeError):
    """A controlled stock-chart error safe for API translation."""


class StockNotFoundError(StockChartError):
    """Raised when a symbol is invalid or unavailable."""


class StockDataUnavailableError(StockChartError):
    """Raised when a configured provider cannot return usable chart data."""


@dataclass(frozen=True)
class ChartRequest:
    symbol: str
    period: str
    range_name: str
    force_demo: bool = False


class StockChartService:
    """Prepare stable chart payloads from PandaData or the local demo dataset."""

    def __init__(self, client: PandaDataClient) -> None:
        self.client = client

    def list_stocks(self) -> list[dict[str, str]]:
        return [dict(stock) for stock in DEFAULT_STOCKS]

    def search(self, query: str) -> list[dict[str, str]]:
        normalized = str(query or "").strip()
        if not normalized:
            return self.list_stocks()
        upper = normalized.upper()
        digits = re.sub(r"\D", "", upper)
        matches = [
            dict(stock)
            for stock in DEFAULT_STOCKS
            if upper in stock["symbol"]
            or normalized in stock["name"]
            or (digits and digits == stock["symbol"][:6])
        ]
        if matches:
            return matches
        if STOCK_SYMBOL_PATTERN.fullmatch(upper):
            return [
                {
                    "symbol": upper,
                    "name": upper,
                    "market": upper.rsplit(".", 1)[1],
                }
            ]
        return []

    def chart(self, request: ChartRequest) -> dict[str, Any]:
        symbol = normalize_symbol(request.symbol)
        if request.period not in SUPPORTED_PERIODS:
            raise StockNotFoundError("暂不支持该行情周期。")
        range_name = normalize_range(request.range_name, request.period)
        stock = stock_metadata(symbol)
        use_demo = request.force_demo or not self.client.configured

        if request.period == "1m":
            rows = (
                demo_intraday_rows(symbol)
                if use_demo
                else self._load_real_intraday(symbol)
            )
            if not rows:
                raise StockNotFoundError(
                    "当前股票暂无可用的分时演示数据。"
                    if use_demo
                    else "暂时无法获取这只股票的分时行情。"
                )
            return build_intraday_payload(
                stock,
                rows,
                range_name=range_name,
                is_demo=use_demo,
            )

        rows = demo_daily_rows(symbol) if use_demo else self._load_real_daily(symbol, range_name)
        candles = sanitize_candles(rows)
        if not candles:
            raise StockNotFoundError(
                "当前股票暂无可用的演示行情。"
                if use_demo
                else "暂时无法获取这只股票的行情。"
            )
        candles = filter_range(candles, range_name)
        if request.period != "1d":
            candles = aggregate_candles(candles, request.period)
        candles = candles[-PERIOD_LIMITS[request.period] :]
        if not candles:
            raise StockDataUnavailableError("该周期暂无有效行情数据。")
        return build_candle_payload(
            stock,
            candles,
            period=request.period,
            range_name=range_name,
            is_demo=use_demo,
        )

    def _load_real_daily(self, symbol: str, range_name: str) -> Any:
        end = date.today()
        start = end - timedelta(days=range_to_days(range_name))
        try:
            return self.client.get_stock_chart_daily(
                symbol=symbol,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        except Exception as exc:
            raise StockDataUnavailableError(
                "PandaData 暂时无法返回这只股票的行情，请稍后重试。"
            ) from exc

    def _load_real_intraday(self, symbol: str) -> Any:
        end = date.today()
        start = end - timedelta(days=7)
        try:
            return self.client.get_stock_chart_intraday(
                symbol=symbol,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        except Exception as exc:
            raise StockDataUnavailableError(
                "PandaData 暂时无法返回这只股票的分时行情，请稍后重试。"
            ) from exc


def normalize_symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if not STOCK_SYMBOL_PATTERN.fullmatch(symbol):
        raise StockNotFoundError("股票代码格式应为 XXXXXX.SH 或 XXXXXX.SZ。")
    return symbol


def normalize_range(value: str, period: str) -> str:
    normalized = str(value or "").strip().lower()
    allowed = {"1d", "3m", "6m", "1y", "3y", "5y"}
    if not normalized:
        return "1d" if period == "1m" else "1y"
    if normalized not in allowed:
        raise StockNotFoundError("暂不支持该时间范围。")
    return normalized


def stock_metadata(symbol: str) -> dict[str, str]:
    for stock in DEFAULT_STOCKS:
        if stock["symbol"] == symbol:
            return dict(stock)
    return {
        "symbol": symbol,
        "name": symbol,
        "market": symbol.rsplit(".", 1)[1],
    }


def sanitize_candles(rows: Any) -> list[dict[str, float | str]]:
    """Filter invalid OHLCV records, de-duplicate, and return ascending rows."""

    by_time: dict[str, dict[str, float | str]] = {}
    for row in iter_rows(rows):
        timestamp = normalize_day(
            pick(row, "trade_date", "date", "time", "datetime", "timestamp")
        )
        open_price = finite_number(pick(row, "open", "open_price"))
        high = finite_number(pick(row, "high", "high_price"))
        low = finite_number(pick(row, "low", "low_price"))
        close = finite_number(pick(row, "close", "close_price", "price"))
        volume = finite_number(pick(row, "volume", "vol", "trade_volume"), default=0)
        values = (open_price, high, low, close, volume)
        if timestamp is None or any(value is None for value in values):
            continue
        assert open_price is not None
        assert high is not None
        assert low is not None
        assert close is not None
        assert volume is not None
        if (
            high < max(open_price, close, low)
            or low > min(open_price, close, high)
            or volume < 0
            or min(open_price, high, low, close) <= 0
        ):
            continue
        by_time[timestamp] = {
            "time": timestamp,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    return [by_time[key] for key in sorted(by_time)]


def aggregate_candles(
    candles: list[dict[str, float | str]],
    period: str,
) -> list[dict[str, float | str]]:
    if period not in {"1w", "1mo"}:
        return list(candles)
    groups: dict[str, list[dict[str, float | str]]] = {}
    for candle in candles:
        parsed = date.fromisoformat(str(candle["time"]))
        if period == "1w":
            iso_year, iso_week, _ = parsed.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
        else:
            key = f"{parsed.year:04d}-{parsed.month:02d}"
        groups.setdefault(key, []).append(candle)
    result: list[dict[str, float | str]] = []
    for rows in groups.values():
        result.append(
            {
                "time": rows[0]["time"],
                "open": rows[0]["open"],
                "high": max(float(row["high"]) for row in rows),
                "low": min(float(row["low"]) for row in rows),
                "close": rows[-1]["close"],
                "volume": sum(float(row["volume"]) for row in rows),
            }
        )
    return result


def calculate_ma(
    candles: list[dict[str, float | str]],
    window: int,
) -> list[dict[str, float | str]]:
    if len(candles) < window:
        return []
    values: list[dict[str, float | str]] = []
    closes = [float(candle["close"]) for candle in candles]
    rolling_sum = sum(closes[:window])
    values.append({"time": candles[window - 1]["time"], "value": rolling_sum / window})
    for index in range(window, len(candles)):
        rolling_sum += closes[index] - closes[index - window]
        values.append({"time": candles[index]["time"], "value": rolling_sum / window})
    return values


def build_candle_payload(
    stock: dict[str, str],
    candles: list[dict[str, float | str]],
    *,
    period: str,
    range_name: str,
    is_demo: bool,
) -> dict[str, Any]:
    return {
        **stock,
        "period": period,
        "range": range_name,
        "start_date": str(candles[0]["time"]).replace("-", ""),
        "end_date": str(candles[-1]["time"]).replace("-", ""),
        "data_source": DEMO_DATA_SOURCE if is_demo else "PandaData",
        "is_demo": is_demo,
        "candles": candles,
        "line": [],
        "volume": [],
        "indicators": {
            "ma5": calculate_ma(candles, 5),
            "ma10": calculate_ma(candles, 10),
            "ma20": calculate_ma(candles, 20),
        },
        "metrics": calculate_metrics(
            [float(candle["close"]) for candle in candles],
            period=period,
        ),
    }


def build_intraday_payload(
    stock: dict[str, str],
    rows: Any,
    *,
    range_name: str,
    is_demo: bool,
) -> dict[str, Any]:
    points = sanitize_intraday(rows)
    if not points:
        raise StockDataUnavailableError("该周期暂无有效行情数据。")
    latest_day = datetime.fromtimestamp(int(points[-1]["time"])).date()
    points = [
        point
        for point in points
        if datetime.fromtimestamp(int(point["time"])).date() == latest_day
    ][-480:]
    line = [{"time": point["time"], "value": point["value"]} for point in points]
    volume = [
        {
            "time": point["time"],
            "value": point["volume"],
            "direction": point["direction"],
        }
        for point in points
    ]
    return {
        **stock,
        "period": "1m",
        "range": range_name,
        "start_date": latest_day.strftime("%Y%m%d"),
        "end_date": latest_day.strftime("%Y%m%d"),
        "data_source": DEMO_DATA_SOURCE if is_demo else "PandaData",
        "is_demo": is_demo,
        "candles": [],
        "line": line,
        "volume": volume,
        "indicators": {"ma5": [], "ma10": [], "ma20": []},
        "metrics": calculate_metrics(
            [float(point["value"]) for point in points],
            period="1m",
        ),
    }


def sanitize_intraday(rows: Any) -> list[dict[str, float | int | str]]:
    by_time: dict[int, dict[str, float | int | str]] = {}
    previous: float | None = None
    ordered: list[tuple[int, float, float]] = []
    for row in iter_rows(rows):
        timestamp = normalize_timestamp(
            pick(row, "time", "trade_time", "datetime", "timestamp", "trade_date")
        )
        value = finite_number(pick(row, "close", "price", "value", "last"))
        volume = finite_number(pick(row, "volume", "vol", "trade_volume"), default=0)
        if timestamp is None or value is None or volume is None:
            continue
        if value <= 0 or volume < 0:
            continue
        ordered.append((timestamp, value, volume))
    for timestamp, value, volume in sorted(ordered):
        direction = "up" if previous is None or value >= previous else "down"
        by_time[timestamp] = {
            "time": timestamp,
            "value": value,
            "volume": volume,
            "direction": direction,
        }
        previous = value
    return [by_time[key] for key in sorted(by_time)]


def calculate_metrics(values: list[float], *, period: str) -> dict[str, float | None]:
    if not values:
        return {
            "latest_close": None,
            "period_return": None,
            "maximum_drawdown": None,
            "volatility": None,
        }
    period_return = values[-1] / values[0] - 1 if values[0] else None
    peak = values[0]
    max_drawdown = 0.0
    returns: list[float] = []
    for index, value in enumerate(values):
        peak = max(peak, value)
        if peak:
            max_drawdown = min(max_drawdown, value / peak - 1)
        if index and values[index - 1] > 0 and value > 0:
            returns.append(math.log(value / values[index - 1]))
    annualization = {"1m": 240 * 252, "1d": 252, "1w": 52, "1mo": 12}[period]
    volatility = (
        stdev(returns) * math.sqrt(annualization)
        if len(returns) >= 2
        else None
    )
    return {
        "latest_close": values[-1],
        "period_return": period_return,
        "maximum_drawdown": max_drawdown,
        "volatility": volatility,
    }


def filter_range(
    candles: list[dict[str, float | str]],
    range_name: str,
) -> list[dict[str, float | str]]:
    if range_name == "5y":
        return candles
    end = date.fromisoformat(str(candles[-1]["time"]))
    cutoff = end - timedelta(days=range_to_days(range_name))
    return [
        candle
        for candle in candles
        if date.fromisoformat(str(candle["time"])) >= cutoff
    ]


def range_to_days(range_name: str) -> int:
    return {
        "1d": 7,
        "3m": 100,
        "6m": 200,
        "1y": 370,
        "3y": 1100,
        "5y": 1830,
    }[range_name]


def iter_rows(value: Any) -> Iterable[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            value = value.to_dict(orient="records")
        except TypeError:
            value = value.to_dict()
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("data", "records", "rows", "items"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
        if value and all(isinstance(item, dict) for item in value.values()):
            rows: list[dict[str, Any]] = []
            for key, item in value.items():
                row = dict(item)
                row.setdefault("trade_date", key)
                rows.append(row)
            return rows
    return []


def pick(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def finite_number(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_day(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    text = text[:10].replace("/", "-")
    candidates = ("%Y-%m-%d", "%Y%m%d")
    for fmt in candidates:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_timestamp(value: Any) -> int | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    if isinstance(value, datetime):
        return int(value.timestamp())
    text = str(value or "").strip()
    if text.isdigit():
        number = int(text)
        if len(text) == 8:
            try:
                return int(datetime.strptime(text, "%Y%m%d").timestamp())
            except ValueError:
                return None
        return number // 1000 if number > 10_000_000_000 else number
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None
