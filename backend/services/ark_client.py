"""Reusable Volcano Ark model client."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, DefaultHttpxClient, OpenAI

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_ARK_MODEL = "ep-20260708162855-pcf9x"
DEFAULT_ARK_TIMEOUT_SECONDS = 90.0
DEFAULT_ARK_MAX_RETRIES = 1
ALPHAOS_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class ArkClientError(RuntimeError):
    """Raised when an Ark model request cannot be completed."""


class ArkClient:
    """Small adapter around the Volcano Ark OpenAI-compatible API."""

    def __init__(self) -> None:
        load_dotenv(dotenv_path=ALPHAOS_ENV_FILE)
        api_key = os.getenv("ARK_API_KEY", "").strip()
        if not api_key:
            raise ArkClientError(
                "未找到 ARK_API_KEY，请先配置环境变量或本地 .env 文件。"
            )

        self._model = os.getenv("ARK_MODEL", "").strip() or DEFAULT_ARK_MODEL
        timeout = _bounded_float_env(
            "ARK_TIMEOUT_SECONDS",
            DEFAULT_ARK_TIMEOUT_SECONDS,
            minimum=5.0,
            maximum=180.0,
        )
        max_retries = _bounded_int_env(
            "ARK_MAX_RETRIES",
            DEFAULT_ARK_MAX_RETRIES,
            minimum=0,
            maximum=2,
        )
        self._client = OpenAI(
            base_url=ARK_BASE_URL,
            api_key=api_key,
            http_client=DefaultHttpxClient(
                trust_env=False,
                timeout=timeout,
            ),
            max_retries=max_retries,
        )

    def chat(self, prompt: str, model: str | None = None) -> str:
        """Send a text prompt and return the model's text response."""
        selected_model = model or self._model
        try:
            response = self._client.responses.create(
                model=selected_model,
                input=prompt,
            )
        except APIConnectionError as exc:
            cause = exc.__cause__ or exc.__context__
            cause_name = (
                type(cause).__name__
                if cause is not None
                else type(exc).__name__
            )
            raise ArkClientError(
                f"Volcano Ark API 连接失败（{cause_name}）。"
            ) from None
        except APIStatusError as exc:
            raise ArkClientError(
                f"Volcano Ark API 返回 HTTP {exc.status_code}。"
            ) from None
        except Exception:
            raise ArkClientError("Volcano Ark API 请求失败。") from None

        output_text = response.output_text
        if not output_text or not output_text.strip():
            raise ArkClientError("Volcano Ark API 返回了空响应。")
        return output_text


def _bounded_float_env(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(os.getenv(name, ""))
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


def _bounded_int_env(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default
