from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError

from backend.services import ark_client
from backend.services.ark_client import ArkClient, ArkClientError, ArkTextRequest


def test_ark_client_ignores_environment_proxy_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setenv("ARK_MODEL", "test-model")
    monkeypatch.delenv("ARK_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ARK_MAX_RETRIES", raising=False)
    http_client = object()
    http_factory = Mock(return_value=http_client)
    openai_client = SimpleNamespace(responses=SimpleNamespace(create=Mock()))
    openai_factory = Mock(return_value=openai_client)
    monkeypatch.setattr(ark_client, "DefaultHttpxClient", http_factory)
    monkeypatch.setattr(ark_client, "OpenAI", openai_factory)

    client = ArkClient()

    http_factory.assert_called_once_with(
        trust_env=False,
        timeout=ark_client.DEFAULT_ARK_TIMEOUT_SECONDS,
    )
    openai_factory.assert_called_once_with(
        base_url=ark_client.ARK_BASE_URL,
        api_key="test-key",
        http_client=http_client,
        max_retries=ark_client.DEFAULT_ARK_MAX_RETRIES,
    )
    assert client._model == "test-model"


def test_ark_client_accepts_only_bounded_timeout_and_retry_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setenv("ARK_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("ARK_MAX_RETRIES", "2")
    http_factory = Mock(return_value=object())
    openai_factory = Mock(
        return_value=SimpleNamespace(responses=SimpleNamespace(create=Mock()))
    )
    monkeypatch.setattr(ark_client, "DefaultHttpxClient", http_factory)
    monkeypatch.setattr(ark_client, "OpenAI", openai_factory)

    ArkClient()

    http_factory.assert_called_once_with(trust_env=False, timeout=45.0)
    assert openai_factory.call_args.kwargs["max_retries"] == 2

    monkeypatch.setenv("ARK_TIMEOUT_SECONDS", "3600")
    monkeypatch.setenv("ARK_MAX_RETRIES", "99")
    http_factory.reset_mock()
    openai_factory.reset_mock()

    ArkClient()

    http_factory.assert_called_once_with(
        trust_env=False,
        timeout=ark_client.DEFAULT_ARK_TIMEOUT_SECONDS,
    )
    assert (
        openai_factory.call_args.kwargs["max_retries"]
        == ark_client.DEFAULT_ARK_MAX_RETRIES
    )


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


def test_chat_text_applies_request_timeout_and_output_token_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    create = Mock(return_value=SimpleNamespace(output_text="ok"))
    monkeypatch.setattr(
        ark_client,
        "DefaultHttpxClient",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        ark_client,
        "OpenAI",
        Mock(
            return_value=SimpleNamespace(
                responses=SimpleNamespace(create=create)
            )
        ),
    )

    response = ArkClient().chat_text(
        ArkTextRequest(
            prompt="bounded request",
            timeout_seconds=37.0,
            max_output_tokens=1234,
        )
    )

    assert response.text == "ok"
    create.assert_called_once_with(
        model=ark_client.DEFAULT_ARK_MODEL,
        input="bounded request",
        temperature=0.0,
        timeout=37.0,
        max_output_tokens=1234,
    )
