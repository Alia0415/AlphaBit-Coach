"""Controlled PandaData adapter for the pinned event-risk methodology."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from backend.services.pandadata_client import PandaDataClient
from backend.skills.contracts import (
    SkillInvocation,
    SkillResult,
    SkillSpec,
    SkillStatus,
)
from backend.skills.loaders.instruction_skill_loader import (
    InstructionSkillLoader,
    SkillUnavailableError,
)


DATED_METHODS = (
    "get_stock_status_change",
    "get_restricted_list",
    "get_stock_pledge",
    "get_stock_shareholder_change",
    "get_holder_count",
)
MAX_SYMBOLS = 20
MAX_ROWS_PER_METHOD = 100


class EventRiskAlertAdapter:
    """Scan only explicitly reviewed PandaData event endpoints."""

    def __init__(
        self,
        *,
        loader: InstructionSkillLoader,
        data_client: PandaDataClient,
        today_provider: Any = date.today,
    ) -> None:
        self._loader = loader
        self._data_client = data_client
        self._today_provider = today_provider

    def __call__(
        self,
        invocation: SkillInvocation,
        spec: SkillSpec,
    ) -> SkillResult:
        try:
            loaded = self._loader.load(spec)
        except (OSError, ValueError, SkillUnavailableError) as exc:
            return _unavailable(invocation, str(exc))

        symbols = _symbols(invocation.inputs)
        if not symbols:
            return _failed(invocation, "事件风险扫描至少需要一个 A 股 symbol。")
        if len(symbols) > MAX_SYMBOLS:
            return _failed(
                invocation,
                f"单次事件风险扫描最多支持 {MAX_SYMBOLS} 个 symbol。",
            )
        start_date, end_date = _window(
            invocation.inputs,
            self._today_provider(),
        )

        events: list[dict[str, Any]] = []
        data_scope: list[dict[str, Any]] = []
        success_count = 0
        for symbol in symbols:
            for method_name in DATED_METHODS:
                try:
                    raw = getattr(self._data_client, method_name)(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    rows = _rows(raw)[:MAX_ROWS_PER_METHOD]
                except Exception as exc:
                    data_scope.append(
                        {
                            "method": method_name,
                            "symbol": symbol,
                            "query_range": [start_date, end_date],
                            "status": "failed",
                            "error_type": type(exc).__name__,
                        }
                    )
                    continue
                success_count += 1
                data_scope.append(
                    {
                        "method": method_name,
                        "symbol": symbol,
                        "query_range": [start_date, end_date],
                        "status": "completed",
                        "row_count": len(rows),
                    }
                )
                for row in rows:
                    events.append(
                        {
                            "symbol": symbol,
                            "method": method_name,
                            "record": row,
                            "severity": "review",
                            "interpretation": (
                                "PandaData 返回了披露记录；需核对公告原文、"
                                "生效日期和具体字段后再判断影响。"
                            ),
                        }
                    )

        if success_count == 0:
            return _unavailable(
                invocation,
                "PandaData 事件接口均不可用，未生成事件风险结论。",
                provenance=loaded.provenance,
            )

        failed_count = len(data_scope) - success_count
        limitations = [
            "返回记录是风险核查线索，不等于已确认负面事件或因果结论。",
            "必须结合公告原文、字段含义和生效日期复核，不构成交易建议。",
        ]
        if failed_count:
            limitations.append(
                f"{failed_count} 个 PandaData 查询失败；结果仅覆盖成功接口。"
            )
        return SkillResult(
            invocation_id=invocation.invocation_id,
            skill_id=invocation.skill_id,
            status=SkillStatus.COMPLETED,
            summary=(
                f"已扫描 {len(symbols)} 个标的、{success_count} 个成功接口，"
                f"返回 {len(events)} 条待核查记录。"
            ),
            data={
                "symbols": symbols,
                "query_range": {
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "events": events,
                "data_scope": data_scope,
                "validation_status": "observed_event_records_not_causal",
            },
            evidence=events,
            assumptions=[
                "PandaData 返回字段及公告日期口径适用于当前扫描窗口。",
            ],
            limitations=limitations,
            provenance={
                **loaded.provenance,
                "pandadata_dependency": (
                    "Mapped to AlphaOS controlled PandaDataClient."
                ),
            },
        )


def _symbols(inputs: Mapping[str, Any]) -> list[str]:
    raw = inputs.get("symbols")
    values = raw if isinstance(raw, list) else [raw] if raw else []
    single = inputs.get("symbol")
    if single:
        values = [single, *values]
    return list(
        dict.fromkeys(
            str(value).strip().upper()
            for value in values
            if str(value).strip()
        )
    )


def _window(inputs: Mapping[str, Any], today: date) -> tuple[str, str]:
    end = str(inputs.get("end_date", "")).strip() or today.strftime("%Y%m%d")
    start = str(inputs.get("start_date", "")).strip()
    if not start:
        start = (today - timedelta(days=90)).strftime("%Y%m%d")
    return start, end


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    if not isinstance(value, Mapping):
        return []
    for key in ("data", "records", "rows", "result"):
        rows = _rows(value.get(key))
        if rows:
            return rows
    if value and all(
        isinstance(item, Sequence) and not isinstance(item, (str, bytes))
        for item in value.values()
    ):
        lengths = {len(item) for item in value.values()}
        if len(lengths) == 1:
            return [
                {str(key): values[index] for key, values in value.items()}
                for index in range(next(iter(lengths)))
            ]
    return []


def _failed(invocation: SkillInvocation, error: str) -> SkillResult:
    return SkillResult(
        invocation_id=invocation.invocation_id,
        skill_id=invocation.skill_id,
        status=SkillStatus.FAILED,
        summary="事件风险扫描未成功完成。",
        limitations=[error],
        error=error,
    )


def _unavailable(
    invocation: SkillInvocation,
    error: str,
    *,
    provenance: dict[str, Any] | None = None,
) -> SkillResult:
    return SkillResult(
        invocation_id=invocation.invocation_id,
        skill_id=invocation.skill_id,
        status=SkillStatus.UNAVAILABLE,
        summary="事件风险 Runtime Skill 或数据服务不可用。",
        limitations=[error],
        provenance=provenance or {},
        error=error,
    )
