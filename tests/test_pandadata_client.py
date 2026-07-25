from __future__ import annotations

import os
from typing import Any

import pytest

from backend.services.pandadata_client import (
    PANDADATA_SERVICE_HOST,
    PandaDataClient,
    _configure_pandadata_proxy_bypass,
)


class RecordingSdk:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_stock_competitor_information(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("get_stock_competitor_information", kwargs))
        return [
            {"competitor_stock_code": "000001", "competitor_name": "A"},
            {"competitor_stock_code": "000002", "competitor_name": "B"},
        ]

    def get_stock_detail(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("get_stock_detail", kwargs))
        return [{"symbol": "601633.SH", "name": "长城汽车", "status": 1}]

    def get_industry_constituents(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("get_industry_constituents", kwargs))
        return [
            {"stock_symbol": "000001.SZ"},
            {"stock_symbol": "000002.SZ"},
        ]

    def get_industry_detail(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("get_industry_detail", kwargs))
        return [
            {"industry_code": "801730", "industry_name": "电力设备"},
            {"industry_code": "801880", "industry_name": "汽车"},
        ]

    def get_concept_list(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("get_concept_list", kwargs))
        return [{"concept": "A"}, {"concept": "B"}]

    def get_concept_constituents(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("get_concept_constituents", kwargs))
        return [{"concept_stock": "000001.SZ"}, {"concept_stock": "000002.SZ"}]

    def get_factor(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("get_factor", kwargs))
        return [{"symbol": "000001.SZ", "close": 10.0}]


def _client_with_sdk(monkeypatch: pytest.MonkeyPatch) -> tuple[PandaDataClient, RecordingSdk]:
    client = PandaDataClient()
    sdk = RecordingSdk()
    monkeypatch.setattr(client, "_authenticate", lambda: sdk)
    return client, sdk


def test_pandadata_proxy_bypass_preserves_existing_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.delenv("PANDADATA_BYPASS_SYSTEM_PROXY", raising=False)

    _configure_pandadata_proxy_bypass()

    expected = (
        "localhost,127.0.0.1,"
        f"{PANDADATA_SERVICE_HOST}"
    )
    assert os.environ["NO_PROXY"] == expected
    assert os.environ["no_proxy"] == expected


def test_pandadata_proxy_bypass_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("no_proxy", "localhost")
    monkeypatch.setenv("PANDADATA_BYPASS_SYSTEM_PROXY", "false")

    _configure_pandadata_proxy_bypass()

    assert os.environ["NO_PROXY"] == "localhost"
    assert os.environ["no_proxy"] == "localhost"


def test_competitor_call_uses_documented_sdk_name_and_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sdk = _client_with_sdk(monkeypatch)

    result = client.get_stock_competitor(
        symbol="002594.SZ",
        start_date="20240101",
        end_date="20241231",
        max_results=1,
    )

    assert sdk.calls == [
        (
            "get_stock_competitor_information",
            {
                "symbol": "002594.SZ",
                "start_date": "20240101",
                "end_date": "20241231",
                "fields": None,
            },
        )
    ]
    assert result == [{"competitor_stock_code": "000001", "competitor_name": "A"}]


def test_stock_catalog_call_uses_active_symbol_and_name_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sdk = _client_with_sdk(monkeypatch)

    result = client.get_stock_catalog()

    assert sdk.calls == [
        (
            "get_stock_detail",
            {
                "symbol": "",
                "fields": ["symbol", "name", "status"],
                "status": 1,
            },
        )
    ]
    assert result == [{"symbol": "601633.SH", "name": "长城汽车", "status": 1}]


def test_industry_calls_use_documented_parameters_and_filter_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sdk = _client_with_sdk(monkeypatch)

    constituents = client.get_industry_constituents(
        industry_code="801880", level="L1", max_results=1
    )
    detail = client.get_industry_detail(industry="汽车", level="L1")

    assert sdk.calls == [
        (
            "get_industry_constituents",
            {
                "industry_code": "801880",
                "stock_symbol": None,
                "level": "L1",
                "fields": None,
            },
        ),
        ("get_industry_detail", {"level": "L1", "fields": None}),
    ]
    assert constituents == [{"stock_symbol": "000001.SZ"}]
    assert detail == [{"industry_code": "801880", "industry_name": "汽车"}]


def test_concept_limits_are_applied_locally_not_sent_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sdk = _client_with_sdk(monkeypatch)

    concepts = client.get_concept_list(max_results=1)
    constituents = client.get_concept_constituents(concept="英伟达概念", max_results=1)

    assert sdk.calls == [
        ("get_concept_list", {"concept": None, "start_date": None, "end_date": None}),
        (
            "get_concept_constituents",
            {
                "concept": "英伟达概念",
                "concept_stock": None,
                "date": None,
                "fields": None,
            },
        ),
    ]
    assert concepts == [{"concept": "A"}]
    assert constituents == [{"concept_stock": "000001.SZ"}]


def test_factor_id_is_mapped_to_documented_factors_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sdk = _client_with_sdk(monkeypatch)

    client.get_factor(
        symbols=["000001.SZ"],
        factor_id="close",
        start_date="20240101",
        end_date="20240131",
    )

    assert sdk.calls == [
        (
            "get_factor",
            {
                "symbol": ["000001.SZ"],
                "factors": ["close"],
                "start_date": "20240101",
                "end_date": "20240131",
                "type": "stock",
                "index_component": "",
            },
        )
    ]
