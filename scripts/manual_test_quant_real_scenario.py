"""Run one bounded real Research -> Quant thesis-validation workflow.

Run from the AlphaOS repository root with Ark and PandaData credentials in
`.env`. The script prints timings and assessment metadata only. It never prints
credentials, raw model output, raw financial statements, or OHLCV rows.

The explicit DAG is an integration fixture, not a production routing fallback.
It isolates expert execution from Manager model variability.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.core.agent_registry import AgentRegistry  # noqa: E402
from backend.core.contracts import ExecutionPlan  # noqa: E402
from backend.core.plan_validator import validate_execution_plan  # noqa: E402
from backend.core.result_aggregator import ResultAggregator  # noqa: E402
from backend.core.workflow_executor import WorkflowExecutor  # noqa: E402
from backend.services.pandadata_client import PandaDataClient  # noqa: E402


REQUEST = (
    "分析比亚迪 002594.SZ 在 2024-01-01 至 2025-12-31 的基本面、"
    "行业竞争格局与投资风险，并用量化方法校验财务增长叙事和同行相对表现，"
    "生成面向投资决策的研究报告。"
)


def main() -> None:
    if not PandaDataClient().configured:
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "PandaData credentials are not configured.",
                },
                ensure_ascii=False,
            )
        )
        return

    plan = _focused_plan()

    workflow_started = perf_counter()
    _, results = WorkflowExecutor().execute(plan, REQUEST)
    workflow_seconds = perf_counter() - workflow_started
    response = ResultAggregator().aggregate(REQUEST, plan, results)

    validations = [
        evidence
        for result in results.values()
        if result.agent.value == "quant"
        for evidence in result.evidence
        if evidence.get("type") == "quant_thesis_validation"
    ]
    output: dict[str, Any] = {
        "status": "completed",
        "plan_source": "validated_integration_fixture",
        "workflow_seconds": round(workflow_seconds, 2),
        "selected_agents": [
            selection.agent.value for selection in plan.selected_agents
        ],
        "task_graph": [
            {
                "step_id": step.id,
                "agent": step.agent.value,
                "depends_on": step.depends_on,
                "analysis_mode": step.inputs.get("analysis_mode"),
            }
            for step in plan.steps
        ],
        "step_statuses": {
            step_id: result.status for step_id, result in results.items()
        },
        "quant_execution_paths": [
            result.metadata.get("execution_path")
            for result in results.values()
            if result.agent.value == "quant"
        ],
        "validation_count": len(validations),
        "assessment_scopes": dict(
            Counter(
                str(item.get("assessment_scope") or "unknown")
                for item in validations
            )
        ),
        "assessments": dict(
            Counter(str(item.get("assessment") or "unknown") for item in validations)
        ),
        "peer_sample_sizes": sorted(
            {
                int(item["peer_sample_size"])
                for item in validations
                if isinstance(item.get("peer_sample_size"), int)
            }
        ),
        "block_titles": [block.title for block in response.content_blocks],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _focused_plan() -> ExecutionPlan:
    plan = ExecutionPlan.model_validate(
        {
            "goal": REQUEST,
            "intent": "验证真实公司研究中的财务与同行量化校验",
            "complexity": "high",
            "selected_agents": [
                {"agent": "research", "reason": "获取财务和同行证据"},
                {"agent": "quant", "reason": "校验上游投资观点"},
            ],
            "steps": [
                {
                    "id": "research_fundamentals",
                    "agent": "research",
                    "objective": "分析比亚迪财务增长、盈利质量和财务风险",
                    "inputs": {
                        "symbol": "002594.SZ",
                        "scope": "full_dossier",
                        "start_period": "2022q4",
                        "end_period": "2024q4",
                    },
                    "depends_on": [],
                    "expected_output": "结构化公司财务证据",
                },
                {
                    "id": "research_industry",
                    "agent": "research",
                    "objective": "识别比亚迪所在行业及可比公司",
                    "inputs": {
                        "industry": "汽车",
                        "symbol": "002594.SZ",
                        "time_range": "2024-2025",
                        "research_goal": "评估行业竞争位置",
                        "focus": "可比公司和竞争格局",
                        "start_date": "20240101",
                        "end_date": "20251231",
                    },
                    "depends_on": [],
                    "expected_output": "结构化同行候选证据",
                },
                {
                    "id": "quant_validation",
                    "agent": "quant",
                    "objective": "用财务指标与同行相对表现校验上游投资观点",
                    "inputs": {
                        "analysis_mode": "thesis_validation",
                        "symbols": ["002594.SZ"],
                        "start_date": "20240101",
                        "end_date": "20251231",
                        "fields": [],
                    },
                    "depends_on": [
                        "research_fundamentals",
                        "research_industry",
                    ],
                    "expected_output": "多源量化决策校验证据",
                },
            ],
        }
    )
    return validate_execution_plan(plan, AgentRegistry())


if __name__ == "__main__":
    main()
