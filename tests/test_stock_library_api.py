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
    assert len(stocks) == 10
    assert stocks[0] == {
        "symbol": "000001.SZ",
        "name": "平安银行",
        "market": "SZ",
    }


def test_search_by_stock_code_succeeds() -> None:
    response = client.get("/api/stocks/search", params={"q": "600519"})

    assert response.status_code == 200
    assert response.json()["stocks"][0]["symbol"] == "600519.SH"


def test_search_by_default_stock_name_succeeds() -> None:
    response = client.get("/api/stocks/search", params={"q": "贵州茅台"})

    assert response.status_code == 200
    assert response.json()["stocks"] == [
        {"symbol": "600519.SH", "name": "贵州茅台", "market": "SH"}
    ]


def test_search_unknown_stock_returns_empty_list() -> None:
    response = client.get("/api/stocks/search", params={"q": "不存在的股票"})

    assert response.status_code == 200
    assert response.json()["stocks"] == []


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
