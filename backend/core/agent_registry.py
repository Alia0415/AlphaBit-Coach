"""Single source of truth for the AlphaOS expert pool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.core.contracts import AgentId
from backend.core.task_spec import ResearchDimension


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Reviewable metadata and availability for one expert."""

    id: AgentId
    name: str
    description: str
    enabled: bool
    tools: tuple[str, ...]
    accepted_inputs: tuple[str, ...]
    capabilities: tuple[str, ...]
    covers_dimensions: tuple[ResearchDimension, ...] = ()

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "tools": list(self.tools),
            "accepted_inputs": list(self.accepted_inputs),
            "capabilities": list(self.capabilities),
            "covers_dimensions": list(self.covers_dimensions),
        }


DEFAULT_EXPERTS = (
    AgentDefinition(
        id=AgentId.RESEARCH,
        name="Research Agent",
        description=(
            "负责公司、行业和市场研究，以及单公司财报、基本面和财务风险分析"
        ),
        enabled=True,
        tools=("pandadata_market_data", "a_share_stock_dossier"),
        accepted_inputs=(
            "symbol",
            "symbols",
            "start_date",
            "end_date",
            "fields",
            "period",
            "start_period",
            "end_period",
            "scope",
            "industry",
            "time_range",
            "focus",
            "research_goal",
        ),
        capabilities=(
            "market_analysis",
            "company_research",
            "industry_research",
            "financial_statement_analysis",
            "company_fundamental_analysis",
            "a_share_due_diligence",
            "financial_risk_screening",
        ),
        covers_dimensions=("company_fundamentals", "industry_competition"),
    ),
    AgentDefinition(
        id=AgentId.QUANT,
        name="Quant Agent",
        description="负责因子假设生成、因子计算、量化验证准备和量化交叉验证",
        enabled=True,
        tools=(
            "factor_idea_generation",
            "r020_volume_expansion",
            "pandadata_market_data",
        ),
        accepted_inputs=(
            "symbols",
            "start_date",
            "end_date",
            "fields",
            "candidate_count",
            "factor_id",
            "horizon",
        ),
        capabilities=(
            "factor_ideation",
            "factor_computation",
            "quantitative_research",
            "quantitative_cross_check",
        ),
        covers_dimensions=("quantitative_cross_check",),
    ),
    AgentDefinition(
        id=AgentId.RISK,
        name="Risk Agent",
        description="独立或结合上游证据进行风险审查，并可扫描 A 股事件风险",
        enabled=True,
        tools=("event_risk_alert", "pandadata_event_data"),
        accepted_inputs=(
            "strategy",
            "thesis",
            "risk_context",
            "symbol",
            "symbols",
            "start_date",
            "end_date",
        ),
        capabilities=(
            "risk_review",
            "stress_testing",
            "assumption_review",
            "event_risk_monitoring",
            "watchlist_risk_screening",
        ),
        covers_dimensions=("risk_assessment",),
    ),
    AgentDefinition(
        id=AgentId.PORTFOLIO,
        name="Portfolio Agent",
        description="组合构建、仓位配置、约束、再平衡和流动性压力测试",
        enabled=False,
        tools=("portfolio_liquidity_stress",),
        accepted_inputs=(
            "holdings",
            "participation",
            "volume_shock",
            "horizon_days",
            "eta",
            "redemption_value",
        ),
        capabilities=(
            "portfolio_construction",
            "allocation",
            "rebalancing",
            "liquidity_stress_testing",
        ),
        covers_dimensions=(),
    ),
    AgentDefinition(
        id=AgentId.MACRO,
        name="Macro Agent",
        description="基于 PandaData 分析宏观环境、政策、周期、利率与流动性",
        enabled=True,
        tools=("macro_monitor", "pandadata_macro_data"),
        accepted_inputs=(
            "industry",
            "time_range",
            "research_goal",
            "start_date",
            "end_date",
        ),
        capabilities=("macro_analysis", "policy_analysis", "cycle_analysis"),
        covers_dimensions=("macro_environment",),
    ),
    AgentDefinition(
        id=AgentId.REPORT,
        name="Report Agent",
        description="仅在需要正式输出或复杂整合时组织已有专家结果",
        enabled=True,
        tools=(),
        accepted_inputs=("format", "audience"),
        capabilities=("report_writing", "evidence_synthesis", "result_presentation"),
        covers_dimensions=("formal_report",),
    ),
)


class AgentRegistry:
    """Immutable lookup surface for all and enabled experts."""

    def __init__(self, agents: Iterable[AgentDefinition] = DEFAULT_EXPERTS) -> None:
        definitions = tuple(agents)
        by_id = {definition.id: definition for definition in definitions}
        if len(by_id) != len(definitions):
            raise ValueError("Agent registry contains duplicate agent IDs")
        self._agents = by_id

    def contains(self, agent_id: AgentId, *, enabled_only: bool = False) -> bool:
        definition = self._agents.get(agent_id)
        return definition is not None and (
            definition.enabled or not enabled_only
        )

    def is_enabled(self, agent_id: AgentId) -> bool:
        definition = self._agents.get(agent_id)
        return bool(definition and definition.enabled)

    def get(self, agent_id: AgentId) -> AgentDefinition:
        try:
            return self._agents[agent_id]
        except KeyError:
            raise KeyError(f"Unknown expert: {agent_id}") from None

    def ids(self, *, enabled_only: bool = False) -> frozenset[AgentId]:
        return frozenset(
            agent_id
            for agent_id, definition in self._agents.items()
            if definition.enabled or not enabled_only
        )

    def prompt_payload(self) -> list[dict[str, object]]:
        """Only enabled experts are exposed to Manager planning."""

        return [
            self._agents[agent_id].to_prompt_dict()
            for agent_id in sorted(
                self.ids(enabled_only=True),
                key=lambda item: item.value,
            )
        ]

    def dimensions_for(self, agent_id: AgentId) -> tuple[ResearchDimension, ...]:
        """Return the research dimensions an agent is authorized to cover."""
        return self.get(agent_id).covers_dimensions

    def agents_covering(
        self, dimension: ResearchDimension, *, enabled_only: bool = True
    ) -> frozenset[AgentId]:
        """Return all agents capable of covering a given dimension."""
        return frozenset(
            agent_id
            for agent_id, defn in self._agents.items()
            if dimension in defn.covers_dimensions
            and (defn.enabled or not enabled_only)
        )
