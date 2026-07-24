from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from backend.agents.risk_agent import RiskAgent
from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import AgentId, ExpertTask
from backend.services.ark_client import ArkClientError
from backend.skills.contracts import SkillInvocation, SkillStatus
from backend.skills.skill_registry import SkillRegistry


class OfflineArk:
    def chat(self, prompt: str, model: str | None = None) -> str:
        raise ArkClientError("offline")


class FakeEventData:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _call(self, method: str, kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((method, kwargs))
        if method == "get_stock_status_change":
            return [
                {
                    "symbol": kwargs["symbol"],
                    "announcement_date": "20260701",
                    "status": "披露记录",
                }
            ]
        return []

    def get_stock_status_change(self, **kwargs: Any) -> Any:
        return self._call("get_stock_status_change", kwargs)

    def get_restricted_list(self, **kwargs: Any) -> Any:
        return self._call("get_restricted_list", kwargs)

    def get_stock_pledge(self, **kwargs: Any) -> Any:
        return self._call("get_stock_pledge", kwargs)

    def get_stock_shareholder_change(self, **kwargs: Any) -> Any:
        return self._call("get_stock_shareholder_change", kwargs)

    def get_holder_count(self, **kwargs: Any) -> Any:
        return self._call("get_holder_count", kwargs)


@pytest.fixture()
def additional_runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    runtime = tmp_path / ".runtime_skills"
    lock: dict[str, Any] = {"version": 1, "skills": {}}

    macro_root = runtime / "skill-macro-monitor"
    macro_ref = macro_root / "references"
    macro_ref.mkdir(parents=True)
    macro_skill = macro_root / "SKILL.md"
    macro_guide = macro_ref / "macro-monitor-guide.md"
    macro_skill.write_text("# Macro Monitor\n", encoding="utf-8")
    macro_guide.write_text("# Controlled guide\n", encoding="utf-8")
    lock["skills"]["macro_monitor"] = _lock_entry(
        repository="quantskills/skill-macro-monitor",
        commit="cf1f76aaf7be751988343c73363199a0b422bf15",
        license_name="GPL-3.0",
        entrypoint="SKILL.md",
        entrypoint_path=macro_skill,
        owner="macro",
        mode="instruction",
        extra_hashes={"references/macro-monitor-guide.md": macro_guide},
    )

    event_root = runtime / "skill-event-risk-alert"
    event_ref = event_root / "references"
    event_ref.mkdir(parents=True)
    event_skill = event_root / "SKILL.md"
    event_guide = event_ref / "event-risk-alert-guide.md"
    event_skill.write_text("# Event Risk Alert\n", encoding="utf-8")
    event_guide.write_text("# Controlled guide\n", encoding="utf-8")
    lock["skills"]["event_risk_alert"] = _lock_entry(
        repository="quantskills/skill-event-risk-alert",
        commit="7a7cbf1d4f94c0b02486a3102c3fab65d35b64a2",
        license_name="GPL-3.0-only",
        entrypoint="SKILL.md",
        entrypoint_path=event_skill,
        owner="risk",
        mode="instruction",
        extra_hashes={"references/event-risk-alert-guide.md": event_guide},
    )

    portfolio_root = runtime / "skill-portfolio-liquidity-stress-test"
    script_dir = portfolio_root / "scripts"
    script_dir.mkdir(parents=True)
    portfolio_script = script_dir / "stress_liquidity.py"
    portfolio_script.write_text(
        """
def analyze(rows, participation, volume_shock, horizon_days, eta, redemption_value):
    details = [
        {
            "symbol": row["symbol"],
            "days_to_liquidate": 2.0,
            "horizon_liquidated_ratio": 1.0,
        }
        for row in rows
    ]
    return {"rows": len(rows), "symbols": len(rows), "details": details}

def build_report(result):
    return {"status": "pass", "domain_result": result, "limitations": []}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    lock["skills"]["portfolio_liquidity_stress"] = _lock_entry(
        repository="quantskills/skill-portfolio-liquidity-stress-test",
        commit="fe7a958611aa7ed8f05a49d7f63fa8afd036acf8",
        license_name="GPL-3.0-only",
        entrypoint="scripts/stress_liquidity.py",
        entrypoint_path=portfolio_script,
        owner="portfolio",
        mode="executable",
    )

    lock_path = tmp_path / "skills.lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    return tmp_path, runtime, lock_path


def _lock_entry(
    *,
    repository: str,
    commit: str,
    license_name: str,
    entrypoint: str,
    entrypoint_path: Path,
    owner: str,
    mode: str,
    extra_hashes: dict[str, Path] | None = None,
) -> dict[str, Any]:
    hashes = {entrypoint: _hash(entrypoint_path)}
    hashes.update(
        {
            name: _hash(path)
            for name, path in (extra_hashes or {}).items()
        }
    )
    return {
        "repository": repository,
        "commit_sha": commit,
        "skill_path": ".",
        "license": license_name,
        "installed_at": "2026-07-25T00:00:00+00:00",
        "expected_entrypoint": entrypoint,
        "owner": owner,
        "mode": mode,
        "entrypoint_sha256": _hash(entrypoint_path),
        "file_sha256": hashes,
        "dependency_mapping": {},
    }


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry(
    runtime: tuple[Path, Path, Path],
    *,
    data_client: Any | None = None,
) -> SkillRegistry:
    project, home, lock = runtime
    return SkillRegistry(
        project_root=project,
        runtime_home=home,
        lock_path=lock,
        pandadata_client=data_client,
    )


def test_macro_monitor_instruction_is_lock_verified(
    additional_runtime: tuple[Path, Path, Path],
) -> None:
    result = _registry(additional_runtime).execute(
        SkillInvocation(
            invocation_id="macro-invocation",
            skill_id="macro_monitor",
            agent="macro",
            objective="monitor macro conditions",
            inputs={
                "industry": "新能源",
                "time_range": "未来12个月",
                "research_goal": "判断宏观环境",
            },
        )
    )

    assert result.status == SkillStatus.COMPLETED
    assert result.data["methodology_loaded"] is True
    assert result.provenance["source_commit"].startswith("cf1f76")


def test_risk_agent_runs_event_skill_and_real_client_boundary(
    additional_runtime: tuple[Path, Path, Path],
) -> None:
    data = FakeEventData()
    registry = _registry(additional_runtime, data_client=data)
    task = ExpertTask(
        task_id="risk-event-1",
        agent=AgentId.RISK,
        objective="扫描观察名单事件风险",
        original_user_request="扫描贵州茅台最近事件风险",
        inputs={
            "symbols": ["600519.SH"],
            "start_date": "20260401",
            "end_date": "20260725",
        },
    )

    result = RiskAgent(
        ark_client=OfflineArk(),
        data_client=data,
        skill_registry=registry,
    ).execute(task)

    assert result.status == "completed"
    assert result.metadata["actual_skills"] == ["event_risk_alert"]
    assert result.metadata["fact_judgment_boundary"]["facts"]
    assert len(data.calls) == 5
    assert all(call["symbol"] == "600519.SH" for _, call in data.calls)
    assert result.data_sources[0]["name"] == "PandaData"
    assert any(call["tool"] == "event_risk_alert" for call in result.tool_calls)
    assert not any("交易成本" in item for item in result.limitations)
    assert any("公告原文" in item for item in result.limitations)


def test_portfolio_skill_uses_only_caller_holdings(
    additional_runtime: tuple[Path, Path, Path],
) -> None:
    result = _registry(additional_runtime).execute(
        SkillInvocation(
            invocation_id="portfolio-invocation",
            skill_id="portfolio_liquidity_stress",
            agent="portfolio",
            objective="stress portfolio liquidity",
            inputs={
                "holdings": [
                    {
                        "symbol": "600519.SH",
                        "position_value": 1_000_000,
                        "adv": 50_000_000,
                        "spread_bps": 8,
                        "volatility": 0.03,
                    }
                ],
                "horizon_days": 5,
            },
        )
    )

    assert result.status == SkillStatus.COMPLETED
    assert result.data["validation_status"] == "scenario_estimate_not_validated"
    assert result.evidence[0]["symbol"] == "600519.SH"
    assert {item["symbol"] for item in result.evidence} == {"600519.SH"}


def test_portfolio_skill_rejects_missing_holdings(
    additional_runtime: tuple[Path, Path, Path],
) -> None:
    result = _registry(additional_runtime).execute(
        SkillInvocation(
            invocation_id="portfolio-missing",
            skill_id="portfolio_liquidity_stress",
            agent="portfolio",
            objective="stress portfolio liquidity",
            inputs={},
        )
    )

    assert result.status == SkillStatus.FAILED
    assert "holdings" in (result.error or "")


def test_portfolio_capability_is_deployed_but_expert_remains_disabled() -> None:
    definition = AgentRegistry().get(AgentId.PORTFOLIO)

    assert definition.enabled is False
    assert definition.tools == ("portfolio_liquidity_stress",)
    assert AgentId.PORTFOLIO not in AgentRegistry().ids(enabled_only=True)
