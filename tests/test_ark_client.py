from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError

from backend.services import ark_client
from backend.services.ark_client import ArkClient, ArkClientError


def test_ark_client_ignores_environment_proxy_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setenv("ARK_MODEL", "test-model")
    http_client = object()
    http_factory = Mock(return_value=http_client)
    openai_client = SimpleNamespace(responses=SimpleNamespace(create=Mock()))
    openai_factory = Mock(return_value=openai_client)
    monkeypatch.setattr(ark_client, "DefaultHttpxClient", http_factory)
    monkeypatch.setattr(ark_client, "OpenAI", openai_factory)

    client = ArkClient()

    http_factory.assert_called_once_with(trust_env=False)
    openai_factory.assert_called_once_with(
        base_url=ark_client.ARK_BASE_URL,
        api_key="test-key",
        http_client=http_client,
    )
    assert client._model == "test-model"


def test_chat_reports_connection_error_type_without_sensitive_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    request = httpx.Request("POST", ark_client.ARK_BASE_URL)
    connection_error = APIConnectionError(request=request)
    connection_error.__cause__ = OSError("secret transport detail")
    responses = SimpleNamespace(create=Mock(side_effect=connection_error))
    monkeypatch.setattr(
        ark_client,
        "DefaultHttpxClient",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        ark_client,
        "OpenAI",
        Mock(return_value=SimpleNamespace(responses=responses)),
    )

    with pytest.raises(ArkClientError, match=r"连接失败（OSError）") as exc_info:
        ArkClient().chat("hello")

    assert "secret transport detail" not in str(exc_info.value)


def test_chat_reports_http_status_without_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    request = httpx.Request("POST", ark_client.ARK_BASE_URL)
    response = httpx.Response(
        429,
        request=request,
        json={"message": "sensitive upstream detail"},
    )
    status_error = APIStatusError(
        "rate limited",
        response=response,
        body=response.json(),
    )
    responses = SimpleNamespace(create=Mock(side_effect=status_error))
    monkeypatch.setattr(
        ark_client,
        "DefaultHttpxClient",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        ark_client,
        "OpenAI",
        Mock(return_value=SimpleNamespace(responses=responses)),
    )

    with pytest.raises(ArkClientError, match=r"HTTP 429") as exc_info:
        ArkClient().chat("hello")

    assert "sensitive upstream detail" not in str(exc_info.value)
