"""Bounded model-assisted extraction of financial terms from report text."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.services.ark_client import ArkClient, ArkClientError

MAX_SOURCE_CHARS = 30_000
MAX_TERMS = 20
MAX_CACHE_ENTRIES = 128


class GlossaryExtractionError(RuntimeError):
    """Raised when dynamic glossary extraction is unavailable or invalid."""


class GlossaryTerm(BaseModel):
    """One validated term that appears verbatim in the source report."""

    term: str = Field(min_length=2, max_length=32)
    explanation: str = Field(min_length=12, max_length=300)
    category: str = Field(min_length=2, max_length=20)

    @field_validator("term")
    @classmethod
    def validate_term(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(
            r"[\u3400-\u9fffA-Za-z0-9α-ωΑ-Ω%+./()（）·\-\s]+",
            normalized,
        ):
            raise ValueError("术语名称包含不允许的字符")
        return normalized

    @field_validator("explanation", "category")
    @classmethod
    def validate_plain_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(mark in normalized for mark in ("<", ">", "\x00")):
            raise ValueError("术语字段必须是纯文本")
        return normalized


class GlossaryPayload(BaseModel):
    """Strict model-output envelope."""

    terms: list[GlossaryTerm] = Field(default_factory=list, max_length=MAX_TERMS)


class GlossaryExtractionResult(BaseModel):
    """API response that degrades safely when model extraction is unavailable."""

    status: Literal["extracted", "unavailable"]
    terms: list[GlossaryTerm] = Field(default_factory=list, max_length=MAX_TERMS)


class GlossaryExtractor:
    """Extract financial terms without allowing model-invented source text."""

    def __init__(self, client: ArkClient | None = None) -> None:
        self._client = client
        self._cache: dict[str, tuple[GlossaryTerm, ...]] = {}

    def extract(self, source_text: str) -> list[GlossaryTerm]:
        source = str(source_text or "").strip()[:MAX_SOURCE_CHARS]
        if len(source) < 2:
            return []

        cache_key = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return [item.model_copy() for item in self._cache[cache_key]]

        prompt = _extraction_prompt(source)
        try:
            raw = self._get_client().chat(prompt)
        except ArkClientError:
            raise GlossaryExtractionError("动态术语提取暂不可用") from None
        try:
            payload = _parse_payload(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            try:
                repaired = self._get_client().chat(_repair_prompt(prompt, str(exc)))
                payload = _parse_payload(repaired)
            except (
                ArkClientError,
                json.JSONDecodeError,
                ValidationError,
                ValueError,
            ):
                raise GlossaryExtractionError("动态术语提取暂不可用") from None

        terms = _filter_source_terms(payload.terms, source)
        self._cache[cache_key] = tuple(terms)
        if len(self._cache) > MAX_CACHE_ENTRIES:
            self._cache.pop(next(iter(self._cache)))
        return [item.model_copy() for item in terms]

    def _get_client(self) -> ArkClient:
        if self._client is None:
            self._client = ArkClient()
        return self._client


def _parse_payload(raw: str) -> GlossaryPayload:
    text = str(raw or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    payload: Any = json.loads(text)
    return GlossaryPayload.model_validate(payload)


def _filter_source_terms(
    candidates: list[GlossaryTerm],
    source: str,
) -> list[GlossaryTerm]:
    accepted: list[GlossaryTerm] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.term.casefold()
        if key in seen or item.term not in source:
            continue
        seen.add(key)
        accepted.append(item)
    accepted.sort(key=lambda item: (-len(item.term), item.term.casefold()))
    return accepted[:MAX_TERMS]


def _extraction_prompt(source: str) -> str:
    schema = json.dumps(GlossaryPayload.model_json_schema(), ensure_ascii=False)
    return f"""
你是 AlphaOS 的金融术语提取器。只识别下方报告正文中原样出现的专业金融术语。

规则：
- 最多返回 {MAX_TERMS} 个对普通读者有解释价值的术语。
- term 必须逐字出现在正文中，不得改写、扩写或补充正文没有的词。
- explanation 只解释通用定义和常见计算口径，不评价本报告、不提供投资建议。
- 优先选择财务报表、估值、宏观、风险、组合管理、行业经营和量化统计术语。
- 忽略公司名、证券代码、普通形容词、完整句子和已能直接理解的日常词。
- 只输出符合 schema 的 JSON，不要 Markdown。

JSON Schema：
{schema}

报告正文：
{source}
""".strip()


def _repair_prompt(original_prompt: str, error: str) -> str:
    return f"""
上一次金融术语提取输出无法通过结构校验。请只修复 JSON 格式和字段约束，
仍必须遵守原任务中“term 逐字存在于报告正文”的要求。只输出 JSON。

校验错误：
{error[:800]}

原任务：
{original_prompt}
""".strip()
