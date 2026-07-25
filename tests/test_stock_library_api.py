from __future__ import annotations

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.main import app
from backend.services.stock_chart_service import StockChartService


client = TestClient(app)


def test_default_stock_list_endpoint_succeeds() -> None:
    response = client.get("/api/stocks")

    assert response.status_code == 200
    stocks = response.json()["stocks"]
    assert len(stocks) == 38
    assert stocks[0] == {
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "market": "SH",
        "board": "沪市主板",
    }
    assert {stock["board"] for stock in stocks} == {
        "沪市主板",
        "深市主板",
        "创业板",
        "科创板",
        "宽基指数",
    }


def test_search_by_stock_code_succeeds() -> None:
    response = client.get("/api/stocks/search", params={"q": "600519"})

    assert response.status_code == 200
    assert response.json()["stocks"][0]["symbol"] == "600519.SH"


def test_search_by_default_stock_name_succeeds() -> None:
    response = client.get("/api/stocks/search", params={"q": "贵州茅台"})

    assert response.status_code == 200
    assert response.json()["stocks"] == [
        {
            "symbol": "600519.SH",
            "name": "贵州茅台",
            "market": "SH",
            "board": "沪市主板",
        }
    ]


def test_search_by_board_returns_board_members() -> None:
    response = client.get("/api/stocks/search", params={"q": "科创板"})

    assert response.status_code == 200
    stocks = response.json()["stocks"]
    assert len(stocks) == 8
    assert {stock["board"] for stock in stocks} == {"科创板"}


class _OfflinePandaData:
    configured = False


class _SearchPandaData:
    configured = True

    def __init__(self) -> None:
        self.catalog_calls = 0
        self.detail_calls: list[str] = []

    def get_stock_catalog(self) -> list[dict[str, object]]:
        self.catalog_calls += 1
        return [
            {"symbol": "601633.SH", "name": "长城汽车", "status": 1},
            {"symbol": "603986.SH", "name": "兆易创新", "status": 1},
        ]

    def get_stock_detail(self, *, symbol: str) -> list[dict[str, object]]:
        self.detail_calls.append(symbol)
        return [
            row
            for row in self.get_stock_catalog()
            if row["symbol"] == symbol
        ]


def test_search_unknown_stock_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "stock_charts",
        StockChartService(_OfflinePandaData()),  # type: ignore[arg-type]
    )

    response = client.get("/api/stocks/search", params={"q": "不存在的股票"})

    assert response.status_code == 200
    assert response.json()["stocks"] == []


def test_search_nondefault_stock_name_uses_provider_catalog_and_cache() -> None:
    provider = _SearchPandaData()
    service = StockChartService(provider)  # type: ignore[arg-type]

    assert service.search("长城汽车") == [
        {
            "symbol": "601633.SH",
            "name": "长城汽车",
            "market": "SH",
            "board": "沪市主板",
        }
    ]
    assert service.search("兆易") == [
        {
            "symbol": "603986.SH",
            "name": "兆易创新",
            "market": "SH",
            "board": "沪市主板",
        }
    ]
    assert provider.catalog_calls == 1


def test_search_nondefault_six_digit_code_resolves_provider_metadata() -> None:
    provider = _SearchPandaData()
    service = StockChartService(provider)  # type: ignore[arg-type]

    assert service.search("601633") == [
        {
            "symbol": "601633.SH",
            "name": "长城汽车",
            "market": "SH",
            "board": "沪市主板",
        }
    ]
    assert provider.detail_calls == ["601633.SH"]


def test_provider_metadata_is_reused_for_nondefault_chart_title() -> None:
    provider = _SearchPandaData()
    service = StockChartService(provider)  # type: ignore[arg-type]

    service.search("长城汽车")

    assert service._stock_metadata("601633.SH")["name"] == "长城汽车"
    assert provider.catalog_calls == 1
    assert provider.detail_calls == []


def test_search_normalizes_exchange_prefix_and_suffix() -> None:
    service = StockChartService(_OfflinePandaData())  # type: ignore[arg-type]

    assert service.search("sh601633")[0]["symbol"] == "601633.SH"
    assert service.search("300999sz")[0]["symbol"] == "300999.SZ"


def test_demo_chart_is_available_without_provider_credentials() -> None:
    response = client.get(
        "/api/stocks/000001.SZ/chart",
        params={"period": "1d", "range": "1y", "demo": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_demo"] is True
    assert payload["data_source"] == "AlphaBit Coach Demo Dataset"
    assert payload["candles"]
    assert payload["indicators"]["ma20"]


def test_demo_intraday_and_aggregate_periods_share_stable_contract() -> None:
    for period, data_key in (("1m", "line"), ("1w", "candles"), ("1mo", "candles")):
        response = client.get(
            "/api/stocks/600519.SH/chart",
            params={"period": period, "range": "1y", "demo": "true"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["period"] == period
        assert payload[data_key]
        assert payload["metrics"]["latest_close"] is not None


def test_invalid_stock_symbol_returns_controlled_error() -> None:
    response = client.get("/api/stocks/not-a-symbol/chart", params={"demo": "true"})

    assert response.status_code == 404
    assert "XXXXXX.SH" in response.json()["detail"]
    assert "Traceback" not in response.text


class _FailingPandaData:
    configured = True

    def get_stock_chart_daily(self, **_: object) -> object:
        raise RuntimeError("SECRET_TOKEN=do-not-leak internal.provider.local")


def test_pandadata_failure_does_not_leak_internal_error(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "stock_charts",
        StockChartService(_FailingPandaData()),  # type: ignore[arg-type]
    )

    response = client.get(
        "/api/stocks/600519.SH/chart",
        params={"period": "1d", "range": "1y"},
    )

    assert response.status_code == 502
    assert "PandaData 暂时无法返回" in response.json()["detail"]
    assert "SECRET_TOKEN" not in response.text
    assert "provider.local" not in response.text
