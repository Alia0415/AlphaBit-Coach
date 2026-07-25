"""Semantic validation for Manager-generated execution plans."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import AgentId, ExecutionPlan, PlanStep
from backend.core.task_spec import ResearchDimension, TaskSpec


class PlanValidationError(ValueError):
    """Raised when a structurally valid plan violates graph invariants."""


def validate_execution_plan(
    plan: ExecutionPlan,
    registry: AgentRegistry,
) -> ExecutionPlan:
    """Validate registry membership and task-graph invariants."""

    if len(plan.steps) > 8:
        raise PlanValidationError("Execution plans may contain at most 8 steps")

    selected = [selection.agent for selection in plan.selected_agents]
    if len(selected) != len(set(selected)):
        raise PlanValidationError("selected_agents contains duplicate agents")

    unknown_selected = set(selected) - registry.ids(enabled_only=True)
    if unknown_selected:
        raise PlanValidationError(
            f"Unknown or disabled selected agents: {_format_agents(unknown_selected)}"
        )

    step_ids = [step.id for step in plan.steps]
    if len(step_ids) != len(set(step_ids)):
        raise PlanValidationError("All step IDs must be unique")

    known_step_ids = set(step_ids)
    used_agents: set[AgentId] = set()
    dependencies: dict[str, list[str]] = {}
    for step in plan.steps:
        if not registry.contains(step.agent, enabled_only=True):
            raise PlanValidationError(
                f"Unknown or disabled step agent: {step.agent.value}"
            )
        used_agents.add(step.agent)
        dependencies[step.id] = step.depends_on
        unknown_dependencies = set(step.depends_on) - known_step_ids
        if unknown_dependencies:
            names = ", ".join(sorted(unknown_dependencies))
            raise PlanValidationError(
                f"Step {step.id} references unknown dependencies: {names}"
            )
        if step.id in step.depends_on:
            raise PlanValidationError(f"Step {step.id} cannot depend on itself")
        _validate_step_contract(step, registry)

    if set(selected) != used_agents:
        raise PlanValidationError(
            "selected_agents must exactly match the agents used by plan steps"
        )

    _assert_acyclic(dependencies)
    return plan


def _validate_step_contract(
    step: PlanStep,
    registry: AgentRegistry,
) -> None:
    definition = registry.get(step.agent)
    unknown_inputs = set(step.inputs) - set(definition.accepted_inputs)
    if unknown_inputs:
        names = ", ".join(sorted(unknown_inputs))
        raise PlanValidationError(
            f"Step {step.id} has unsupported inputs for "
            f"{step.agent.value}: {names}"
        )

    if step.agent == AgentId.RESEARCH:
        _validate_research_inputs(step)
    elif step.agent == AgentId.MACRO:
        _validate_macro_inputs(step)
    elif step.agent == AgentId.REPORT and not step.depends_on:
        raise PlanValidationError(
            f"Report step {step.id} requires at least one declared dependency"
        )


_DOSSIER_SCOPES = {"financials", "financial_risk", "full_dossier"}
_MARKET_FIELDS = {"trade_date", "symbol", "close", "volume"}
_A_SHARE_SYMBOL = re.compile(r"^\d{6}\.(?:SH|SZ)$")


def _validate_research_inputs(step: PlanStep) -> None:
    inputs = step.inputs
    scope = inputs.get("scope")
    if scope is not None and (
        not isinstance(scope, str) or scope not in _DOSSIER_SCOPES
    ):
        raise PlanValidationError(
            f"Research step {step.id} has unsupported scope: {scope}"
        )

    if "industry" in inputs:
        _validate_industry_research_inputs(step, inputs, scope)
        return

    if scope in _DOSSIER_SCOPES:
        symbol = _single_research_symbol(inputs)
        if symbol is None:
            raise PlanValidationError(
                f"Dossier research step {step.id} requires one A-share symbol"
            )
        _validate_period_pair(step, inputs)
        return

    if "symbol" in inputs:
        raise PlanValidationError(
            f"Market research step {step.id} must use inputs.symbols as a list, "
            "not inputs.symbol"
        )

    symbols = inputs.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise PlanValidationError(
            f"Market research step {step.id} requires a non-empty symbols list"
        )
    if any(
        not isinstance(symbol, str)
        or _A_SHARE_SYMBOL.fullmatch(symbol.strip().upper()) is None
        for symbol in symbols
    ):
        raise PlanValidationError(
            f"Market research step {step.id} contains an invalid A-share symbol"
        )

    start_date = _validated_date(step, inputs, "start_date")
    end_date = _validated_date(step, inputs, "end_date")
    if start_date > end_date:
        raise PlanValidationError(
            f"Market research step {step.id} start_date is after end_date"
        )

    fields = inputs.get("fields", [])
    if not isinstance(fields, list) or any(
        not isinstance(field, str) for field in fields
    ):
        raise PlanValidationError(
            f"Market research step {step.id} fields must be a string list"
        )
    if fields and not _MARKET_FIELDS.issubset(set(fields)):
        raise PlanValidationError(
            f"Market research step {step.id} fields must include "
            "trade_date, symbol, close, and volume"
        )


def _validate_industry_research_inputs(
    step: PlanStep,
    inputs: dict[str, Any],
    scope: Any,
) -> None:
    industry = inputs.get("industry")
    if not isinstance(industry, str) or not industry.strip():
        raise PlanValidationError(
            f"Industry research step {step.id} requires a non-empty industry"
        )
    # symbol (singular) is allowed for industry research (spec §7.1 competitor lookup)
    # but symbols (plural list) is the market-research format and must be rejected
    if "symbols" in inputs:
        raise PlanValidationError(
            f"Industry research step {step.id} cannot include symbol or symbols"
        )
    if scope in _DOSSIER_SCOPES:
        raise PlanValidationError(
            f"Industry research step {step.id} cannot include dossier scope"
        )

    for name in ("time_range", "research_goal", "focus"):
        if name not in inputs:
            continue
        value = inputs[name]
        if not isinstance(value, str) or not value.strip():
            raise PlanValidationError(
                f"Industry research step {step.id} {name} must be "
                "a non-empty string"
            )


def _validate_macro_inputs(step: PlanStep) -> None:
    inputs = step.inputs
    for name in ("industry", "time_range", "research_goal"):
        value = inputs.get(name)
        if not isinstance(value, str) or not value.strip():
            raise PlanValidationError(
                f"Macro step {step.id} requires a non-empty {name}"
            )

    start = inputs.get("start_date")
    end = inputs.get("end_date")
    start_missing = start is None or (isinstance(start, str) and not start.strip())
    end_missing = end is None or (isinstance(end, str) and not end.strip())
    if start_missing != end_missing:
        raise PlanValidationError(
            f"Macro step {step.id} must provide both start_date and end_date"
        )
    if not start_missing:
        start_date = _validated_macro_date(step, "start_date", start)
        end_date = _validated_macro_date(step, "end_date", end)
        if start_date > end_date:
            raise PlanValidationError(
                f"Macro step {step.id} start_date is after end_date"
            )


def _validated_macro_date(step: PlanStep, name: str, value: Any) -> datetime:
    if not isinstance(value, str):
        raise PlanValidationError(
            f"Macro step {step.id} requires {name} in YYYYMMDD format"
        )
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        raise PlanValidationError(
            f"Macro step {step.id} has invalid {name}: {value}"
        ) from None


def _single_research_symbol(inputs: dict[str, Any]) -> str | None:
    candidate = inputs.get("symbol")
    if candidate is None:
        symbols = inputs.get("symbols")
        if isinstance(symbols, list) and len(symbols) == 1:
            candidate = symbols[0]
    if not isinstance(candidate, str):
        return None
    value = candidate.strip().upper()
    return value if _A_SHARE_SYMBOL.fullmatch(value) else None


def _validated_date(
    step: PlanStep,
    inputs: dict[str, Any],
    name: str,
) -> datetime:
    value = inputs.get(name)
    if not isinstance(value, str):
        raise PlanValidationError(
            f"Market research step {step.id} requires {name} in YYYYMMDD format"
        )
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        raise PlanValidationError(
            f"Market research step {step.id} has invalid {name}: {value}"
        ) from None


def _validate_period_pair(
    step: PlanStep,
    inputs: dict[str, Any],
) -> None:
    start = inputs.get("start_period")
    end = inputs.get("end_period")
    if (start is None) != (end is None):
        raise PlanValidationError(
            f"Dossier research step {step.id} must provide both "
            "start_period and end_period"
        )


def _assert_acyclic(dependencies: dict[str, list[str]]) -> None:
    state: dict[str, int] = {}

    def visit(step_id: str) -> None:
        current = state.get(step_id, 0)
        if current == 1:
            raise PlanValidationError("Task graph contains a dependency cycle")
        if current == 2:
            return
        state[step_id] = 1
        for dependency in dependencies[step_id]:
            visit(dependency)
        state[step_id] = 2

    for step_id in dependencies:
        visit(step_id)


def _format_agents(agents: set[AgentId]) -> str:
    return ", ".join(sorted(agent.value for agent in agents))


# ---------------------------------------------------------------------------
# Dimension-coverage semantic validation (spec §6.3)
# ---------------------------------------------------------------------------


def validate_plan_dimensions(
    plan: ExecutionPlan,
    task_spec: TaskSpec,
    registry: AgentRegistry,
) -> ExecutionPlan:
    """Validate dimension coverage, step authorization, and scope rules.

    Must be called after structural validation (validate_execution_plan).
    Raises PlanValidationError on any semantic violation.
    """
    # 1. Each step's covers_dimensions must be authorized by the Registry
    for step in plan.steps:
        if not step.covers_dimensions:
            continue
        authorized = set(registry.dimensions_for(step.agent))
        claimed = set(step.covers_dimensions)
        unauthorized = claimed - authorized
        if unauthorized:
            dims = ", ".join(sorted(unauthorized))
            raise PlanValidationError(
                f"Step {step.id} ({step.agent.value}) claims unauthorized "
                f"dimensions: {dims}"
            )

    # 2. All required dimensions must be covered by at least one step
    #    Skip this check if no step declares any covers_dimensions (legacy plan format)
    covered_dimensions: set[ResearchDimension] = set()
    any_step_has_dimensions = False
    for step in plan.steps:
        if step.covers_dimensions:
            any_step_has_dimensions = True
        covered_dimensions.update(step.covers_dimensions)

    if any_step_has_dimensions:
        missing_required = set(task_spec.required_dimensions) - covered_dimensions
        if missing_required:
            dims = ", ".join(sorted(missing_required))
            raise PlanValidationError(
                f"Plan does not cover required dimensions: {dims}"
            )

    # 3. Focused requests must not add unrelated steps
    if task_spec.request_scope == "focused":
        allowed_dimensions = set(task_spec.required_dimensions) | set(
            task_spec.optional_dimensions
        )
        for step in plan.steps:
            if not step.covers_dimensions:
                # Steps without declared dimensions are OK (utility steps)
                continue
            step_dims = set(step.covers_dimensions)
            unrelated = step_dims - allowed_dimensions
            if unrelated:
                dims = ", ".join(sorted(unrelated))
                raise PlanValidationError(
                    f"Focused plan step {step.id} covers unrelated "
                    f"dimensions: {dims}"
                )

    # 4. formal_report not in TaskSpec → reject any Report step
    task_dimensions = set(task_spec.required_dimensions) | set(
        task_spec.optional_dimensions
    )
    if "formal_report" not in task_dimensions:
        for step in plan.steps:
            if step.agent == AgentId.REPORT:
                raise PlanValidationError(
                    f"Report step {step.id} is not allowed when formal_report "
                    "is not in task dimensions"
                )

    # 5. formal_report in TaskSpec → Report must depend on research evidence
    if "formal_report" in task_dimensions:
        for step in plan.steps:
            if step.agent == AgentId.REPORT:
                all_deps = step.all_dependency_step_ids()
                if not all_deps:
                    raise PlanValidationError(
                        f"Report step {step.id} must depend on at least one "
                        "research evidence step"
                    )

    # 6. Manager must not appear in selected_agents or as a step agent
    #    (Manager is not an expert, checked as AgentId not in enum but
    #     this is a semantic rule — verify no step.agent == 'manager')
    for selection in plan.selected_agents:
        if selection.agent.value == "manager":
            raise PlanValidationError(
                "Manager must not appear in selected_agents"
            )

    # 7. Validate typed dependencies for cycle and unknown refs
    step_id_set = {step.id for step in plan.steps}
    all_dependencies: dict[str, list[str]] = {}
    for step in plan.steps:
        deps = step.all_dependency_step_ids()
        all_dependencies[step.id] = deps
        unknown = set(deps) - step_id_set
        if unknown:
            names = ", ".join(sorted(unknown))
            raise PlanValidationError(
                f"Step {step.id} typed dependencies reference unknown "
                f"steps: {names}"
            )
        if step.id in deps:
            raise PlanValidationError(
                f"Step {step.id} cannot depend on itself (typed dependency)"
            )

    _assert_acyclic(all_dependencies)

    return plan
