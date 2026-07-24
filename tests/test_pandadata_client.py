from __future__ import annotations

import os

import pytest

from backend.services.pandadata_client import (
    PANDADATA_SERVICE_HOST,
    _configure_pandadata_proxy_bypass,
)


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
