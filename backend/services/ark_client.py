"""Reusable Volcano Ark model client with structured requests and retry."""

from __future__ import annotations

import json
import logging
import os
import random
import time
from enum import Enum
from pathlib import Path
from typing import Any, Generic, TypeVar

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, DefaultHttpxClient, OpenAI
from pydantic import BaseModel, Field, ValidationError

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_ARK_MODEL = "ep-20260708162855-pcf9x"
DEFAULT_ARK_TIMEOUT_SECONDS = 90.0
DEFAULT_ARK_MAX_RETRIES = 1
ALPHAOS_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Error taxonomy (spec §11)
# ---------------------------------------------------------------------------


class ArkErrorKind(str, Enum):
    """Stable internal error classification — never exposed to users."""

    CONFIGURATION = "configuration"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    INVALID_RESPONSE = "invalid_response"
    SCHEMA_VALIDATION = "schema_validation"
    CONTENT_EMPTY = "content_empty"


class ArkClientError(RuntimeError):
    """Raised when an Ark model request cannot be completed."""

    def __init__(self, message: str, kind: ArkErrorKind | None = None) -> None:
        super().__init__(message)
        self.kind = kind or ArkErrorKind.INVALID_RESPONSE


# ---------------------------------------------------------------------------
# Request contracts (spec §11)
# ---------------------------------------------------------------------------


class ArkTextRequest(BaseModel):
    """Structured text prompt request."""

    prompt: str = Field(min_length=1)
    model: str | None = None
    temperature: float = 0.0
    max_output_tokens: int | None = None
    timeout_seconds: float = 120.0
    purpose: str = "general"
    prompt_version: str = "1.0"
    execution_id: str | None = None
    step_id: str | None = None
    attempt: int = 1


class ArkJsonRequest(BaseModel, Generic[T]):
    """Structured JSON prompt request with schema validation."""

    prompt: str = Field(min_length=1)
    response_model: Any  # The Pydantic model class for validation
    model: str | None = None
    temperature: float = 0.0
    max_output_tokens: int | None = None
    timeout_seconds: float = 120.0
    purpose: str = "structured_output"
    prompt_version: str = "1.0"
    execution_id: str | None = None
    step_id: str | None = None
    attempt: int = 1

    class Config:
        arbitrary_types_allowed = True


class ArkResponse(BaseModel):
    """Structured response wrapper."""

    text: str
    model: str
    attempt: int = 1
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_RETRYABLE_KINDS = {
    ArkErrorKind.TIMEOUT,
    ArkErrorKind.CONNECTION,
    ArkErrorKind.RATE_LIMIT,
    ArkErrorKind.SERVER,
}
_MAX_TRANSPORT_RETRIES = 2
_BASE_BACKOFF_SECONDS = 1.0
_MAX_JITTER_SECONDS = 0.5


def _should_transport_retry(kind: ArkErrorKind) -> bool:
    return kind in _RETRYABLE_KINDS


def _backoff_seconds(attempt: int) -> float:
    base = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
    jitter = random.uniform(0, _MAX_JITTER_SECONDS)
    return base + jitter


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ArkClient:
    """Volcano Ark adapter with structured requests, error taxonomy, and retry."""

    def __init__(self) -> None:
        load_dotenv(dotenv_path=ALPHAOS_ENV_FILE)
        api_key = os.getenv("ARK_API_KEY", "").strip()
        if not api_key:
            raise ArkClientError(
                "未找到 ARK_API_KEY，请先配置环境变量或本地 .env 文件。",
                kind=ArkErrorKind.CONFIGURATION,
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

    # --- Legacy interface (backward compatible) ---

    def chat(self, prompt: str, model: str | None = None) -> str:
        """Send a text prompt and return the model's text response (legacy)."""
        request = ArkTextRequest(prompt=prompt, model=model)
        response = self.chat_text(request)
        return response.text

    # --- New structured interfaces (spec §11) ---

    def chat_text(
        self,
        request: ArkTextRequest,
        budget_remaining_seconds: float | None = None,
    ) -> ArkResponse:
        """Send a text prompt with retry and return structured response."""
        selected_model = request.model or self._model
        last_error: ArkClientError | None = None

        for attempt in range(1, _MAX_TRANSPORT_RETRIES + 2):
            if budget_remaining_seconds is not None and budget_remaining_seconds <= 0:
                raise ArkClientError(
                    "时间预算耗尽，无法重试。",
                    kind=ArkErrorKind.TIMEOUT,
                )

            start_time = time.monotonic()
            try:
                response = self._client.responses.create(
                    model=selected_model,
                    input=request.prompt,
                    temperature=request.temperature,
                )
                duration_ms = int((time.monotonic() - start_time) * 1000)
                output_text = response.output_text
                if not output_text or not output_text.strip():
                    raise ArkClientError(
                        "Volcano Ark API 返回了空响应。",
                        kind=ArkErrorKind.CONTENT_EMPTY,
                    )
                return ArkResponse(
                    text=output_text,
                    model=selected_model,
                    attempt=attempt,
                    duration_ms=duration_ms,
                )
            except ArkClientError as exc:
                last_error = exc
                if not _should_transport_retry(exc.kind):
                    raise
                if attempt > _MAX_TRANSPORT_RETRIES:
                    raise
                logger.warning(
                    "Ark transport retry %d/%d: %s",
                    attempt,
                    _MAX_TRANSPORT_RETRIES,
                    exc.kind.value,
                )
                time.sleep(_backoff_seconds(attempt))
            except APIConnectionError as exc:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                cause = exc.__cause__ or exc.__context__
                cause_name = (
                    type(cause).__name__ if cause is not None else type(exc).__name__
                )
                last_error = ArkClientError(
                    f"Volcano Ark API 连接失败（{cause_name}）。",
                    kind=ArkErrorKind.CONNECTION,
                )
                if attempt > _MAX_TRANSPORT_RETRIES:
                    raise last_error from None
                logger.warning(
                    "Ark connection retry %d/%d", attempt, _MAX_TRANSPORT_RETRIES
                )
                time.sleep(_backoff_seconds(attempt))
            except APIStatusError as exc:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                kind = _classify_status_error(exc.status_code)
                last_error = ArkClientError(
                    f"Volcano Ark API 返回 HTTP {exc.status_code}。",
                    kind=kind,
                )
                if not _should_transport_retry(kind):
                    raise last_error from None
                if attempt > _MAX_TRANSPORT_RETRIES:
                    raise last_error from None
                logger.warning(
                    "Ark status retry %d/%d: HTTP %d",
                    attempt,
                    _MAX_TRANSPORT_RETRIES,
                    exc.status_code,
                )
                time.sleep(_backoff_seconds(attempt))
            except Exception:
                raise ArkClientError(
                    "Volcano Ark API 请求失败。",
                    kind=ArkErrorKind.INVALID_RESPONSE,
                ) from None

        # Should not reach here, but satisfy type checker
        raise last_error or ArkClientError(
            "Ark 请求失败。", kind=ArkErrorKind.INVALID_RESPONSE
        )

    def chat_json(
        self,
        request: ArkJsonRequest[T],
        budget_remaining_seconds: float | None = None,
    ) -> T:
        """Send a prompt expecting JSON, validate with Pydantic, one repair allowed."""
        text_request = ArkTextRequest(
            prompt=request.prompt,
            model=request.model,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            timeout_seconds=request.timeout_seconds,
            purpose=request.purpose,
            prompt_version=request.prompt_version,
            execution_id=request.execution_id,
            step_id=request.step_id,
            attempt=request.attempt,
        )
        response = self.chat_text(text_request, budget_remaining_seconds)
        raw_text = response.text.strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_text = "\n".join(lines)

        # First attempt to parse
        model_class = request.response_model
        try:
            data = json.loads(raw_text)
            return model_class.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as first_error:
            # One repair attempt allowed (spec §11)
            logger.warning("Ark JSON first parse failed: %s", str(first_error)[:200])
            repair_prompt = (
                f"{request.prompt}\n\n"
                f"你上次的 JSON 输出有错误:\n{str(first_error)[:500]}\n\n"
                f"请修复并重新输出有效 JSON。"
            )
            repair_request = ArkTextRequest(
                prompt=repair_prompt,
                model=request.model,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
                timeout_seconds=request.timeout_seconds,
                purpose=f"{request.purpose}_repair",
                prompt_version=request.prompt_version,
                execution_id=request.execution_id,
                step_id=request.step_id,
                attempt=request.attempt + 1,
            )
            try:
                repair_response = self.chat_text(
                    repair_request, budget_remaining_seconds
                )
                repair_text = repair_response.text.strip()
                if repair_text.startswith("```"):
                    lines = repair_text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    repair_text = "\n".join(lines)
                data = json.loads(repair_text)
                return model_class.model_validate(data)
            except (json.JSONDecodeError, ValidationError, ArkClientError) as exc:
                raise ArkClientError(
                    f"JSON 修复失败: {str(exc)[:200]}",
                    kind=ArkErrorKind.SCHEMA_VALIDATION,
                ) from None


def _classify_status_error(status_code: int) -> ArkErrorKind:
    """Map HTTP status codes to internal error taxonomy."""
    if status_code == 429:
        return ArkErrorKind.RATE_LIMIT
    if status_code == 408:
        return ArkErrorKind.TIMEOUT
    if 500 <= status_code < 600:
        return ArkErrorKind.SERVER
    return ArkErrorKind.INVALID_RESPONSE


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
