"""Pure task-graph execution for Manager-generated AlphaOS plans."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import Lock
from typing import Annotated, Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from backend.agents.macro_agent import MacroAgent
from backend.agents.quant_agent import QuantAgent
from backend.agents.report_agent import ReportAgent
from backend.agents.research_agent import ResearchAgent
from backend.agents.risk_agent import RiskAgent
from backend.core.agent_registry import AgentRegistry
from backend.core.contracts import (
    AgentId,
    ExecutionEvent,
    ExecutionPlan,
    ExpertResult,
    ExpertTask,
    PlanStep,
)

ExpertHandler = Callable[[ExpertTask], ExpertResult]


def _merge_results(
    current: dict[str, ExpertResult],
    update: dict[str, ExpertResult],
) -> dict[str, ExpertResult]:
    return {**current, **update}


class _WorkflowState(TypedDict):
    results: Annotated[dict[str, ExpertResult], _merge_results]


class WorkflowExecutor:
    """Execute exactly the nodes and edges supplied by an arbitrary valid DAG."""

    runtime_name = "langgraph"

    def __init__(
        self,
        handlers: Mapping[AgentId, ExpertHandler] | None = None,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._registry = registry or AgentRegistry()
        self._handlers = (
            dict(handlers) if handlers is not None else _default_handlers()
        )

    def execute(
        self,
        plan: ExecutionPlan,
        original_user_request: str | None = None,
        event_sink: Callable[[ExecutionEvent], None] | None = None,
    ) -> tuple[list[ExecutionEvent], dict[str, ExpertResult]]:
        """Compile and run the validated plan with LangGraph.

        The executor never adds, removes, reorders, or selects business steps.
        When ``event_sink`` is provided, each emitted event is forwarded to it
        as it is produced (for streaming), without changing the graph semantics
        or the returned event list.
        """

        if plan.needs_clarification:
            return [], {}

        events: list[ExecutionEvent] = []
        event_lock = Lock()
        user_request = (original_user_request or plan.goal).strip()

        def emit(event: ExecutionEvent) -> None:
            with event_lock:
                events.append(event)
                if event_sink is not None:
                    event_sink(event)

        def make_wave_start(
            steps: list[PlanStep],
        ) -> Callable[[_WorkflowState], _WorkflowState]:
            def start_wave(state: _WorkflowState) -> _WorkflowState:
                results = state.get("results", {})
                blocked_results: dict[str, ExpertResult] = {}
                for step in sorted(steps, key=lambda item: item.id):
                    if any(
                        results[dependency].status != "completed"
                        for dependency in step.required_dependency_ids()
                    ):
                        blocked_results[step.id] = ExpertResult(
                            task_id=step.id,
                            agent=step.agent,
                            status="blocked",
                            summary="步骤因必需依赖失败而被阻断。",
                            error=(
                                "前置分析未完成，本步骤无法继续。"
                            ),
                        )
                        emit(
                            _event(
                                "step_failed",
                                step.id,
                                step.agent,
                                "步骤因必需依赖失败而被阻断。",
                                {"status": "blocked"},
                            )
                        )
                    else:
                        emit(
                            _event(
                                "step_started",
                                step.id,
                                step.agent,
                                f"{self._registry.get(step.agent).name} 开始执行任务。",
                            )
                        )
                return {"results": blocked_results}

            return start_wave

        def make_node(step: PlanStep) -> Callable[[_WorkflowState], _WorkflowState]:
            def execute_node(state: _WorkflowState) -> _WorkflowState:
                results = state.get("results", {})
                if step.id in results:
                    return {"results": {}}

                all_dep_ids = step.all_dependency_step_ids()
                task = ExpertTask(
                    task_id=step.id,
                    agent=step.agent,
                    objective=step.objective,
                    original_user_request=user_request,
                    inputs=step.inputs,
                    dependency_results={
                        dep_id: results[dep_id]
                        for dep_id in all_dep_ids
                    },
                )
                result = self._execute_task(task)
                for internal_event in _safe_agent_events(result):
                    emit(
                        _event(
                            internal_event["type"],
                            result.task_id,
                            result.agent,
                            _agent_event_message(
                                internal_event["type"],
                                internal_event["metadata"].get("skill_id"),
                            ),
                            internal_event["metadata"],
                        )
                    )
                for call in result.tool_calls:
                    emit(
                        _event(
                            "tool_called",
                            result.task_id,
                            result.agent,
                            f"{result.agent.value} 调用了 {call.get('tool', 'tool')}。",
                            {"tool": call.get("tool"), "status": call.get("status")},
                        )
                    )
                if result.status == "completed":
                    emit(
                        _event(
                            "step_completed",
                            result.task_id,
                            result.agent,
                            f"{result.agent.value} 步骤执行完成。",
                            {
                                "result_summary": result.summary,
                                "evidence": result.evidence[:5],
                                "assumptions": result.assumptions,
                                "risks": result.risks,
                                "limitations": result.limitations,
                                "data_sources": result.data_sources,
                            },
                        )
                    )
                else:
                    emit(
                        _event(
                            "step_failed",
                            result.task_id,
                            result.agent,
                            f"{result.agent.value} 步骤执行失败。",
                        )
                    )
                return {"results": {step.id: result}}

            return execute_node

        graph = StateGraph(_WorkflowState)
        for step in plan.steps:
            graph.add_node(step.id, make_node(step))

        if not plan.steps:
            graph.add_edge(START, END)
        else:
            waves = _execution_waves(plan)
            previous_nodes: list[str] = []
            for index, wave in enumerate(waves):
                start_node = f"__alphaos_wave_{index}__"
                graph.add_node(start_node, make_wave_start(wave))
                graph.add_edge(previous_nodes or START, start_node)
                for step in wave:
                    graph.add_edge(start_node, step.id)
                previous_nodes = [step.id for step in wave]
            graph.add_edge(previous_nodes, END)

        final_state = graph.compile().invoke({"results": {}})
        results = final_state["results"]
        return events, {
            step.id: results[step.id]
            for step in plan.steps
            if step.id in results
        }

    def _execute_task(self, task: ExpertTask) -> ExpertResult:
        if not self._registry.is_enabled(task.agent):
            return _failure(
                task,
                f"Expert '{task.agent.value}' is disabled and cannot execute.",
            )
        handler = self._handlers.get(task.agent)
        if handler is None:
            return _failure(
                task,
                f"No real implementation is registered for '{task.agent.value}'.",
            )
        try:
            raw_result: Any = handler(task)
            result = ExpertResult.model_validate(raw_result)
            if result.task_id != task.task_id or result.agent != task.agent:
                raise ValueError("Expert result does not match its assigned task")
            return result
        except Exception:
            return _failure(task, "Expert execution raised an internal error.")


def _default_handlers() -> dict[AgentId, ExpertHandler]:
    return {
        AgentId.RESEARCH: ResearchAgent(),
        AgentId.QUANT: QuantAgent(),
        AgentId.RISK: RiskAgent(),
        AgentId.MACRO: MacroAgent(),
        AgentId.REPORT: ReportAgent(),
    }


def _execution_waves(plan: ExecutionPlan) -> list[list[PlanStep]]:
    """Return stable dependency-ready batches matching the public SSE contract."""

    pending = {step.id: step for step in plan.steps}
    completed: set[str] = set()
    waves: list[list[PlanStep]] = []
    while pending:
        ready = sorted(
            (
                step
                for step in pending.values()
                if set(step.all_dependency_step_ids()) <= completed
            ),
            key=lambda item: item.id,
        )
        if not ready:
            raise RuntimeError("No executable steps remain in the task graph")
        waves.append(ready)
        for step in ready:
            completed.add(step.id)
            pending.pop(step.id)
    return waves


def _failure(task: ExpertTask, error: str) -> ExpertResult:
    return ExpertResult(
        task_id=task.task_id,
        agent=task.agent,
        status="failed",
        summary="专家步骤未成功执行。",
        limitations=[error],
        error=error,
    )


def _event(
    event_type: str,
    step_id: str | None,
    agent: AgentId | None,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        type=cast(Any, event_type),
        step_id=step_id,
        agent=agent,
        message=message,
        metadata=metadata or {},
    )


_INTERNAL_EVENT_TYPES = {
    "skill_plan_created",
    "skill_started",
    "skill_completed",
    "skill_failed",
}
_SAFE_AGENT_EVENT_METADATA = {
    "skill_id",
    "status",
    "selected_skill_count",
    "skill_step_count",
    "scope",
}


def _safe_agent_events(result: ExpertResult) -> list[dict[str, Any]]:
    """Surface generic expert-internal events without raw data or instructions."""

    raw_events = result.metadata.get("agent_events", [])
    if not isinstance(raw_events, list):
        return []
    safe: list[dict[str, Any]] = []
    for item in raw_events:
        if not isinstance(item, dict) or item.get("type") not in _INTERNAL_EVENT_TYPES:
            continue
        raw_metadata = item.get("metadata", {})
        if not isinstance(raw_metadata, dict):
            raw_metadata = {}
        metadata = {
            key: raw_metadata.get(key)
            for key in _SAFE_AGENT_EVENT_METADATA
            if key in raw_metadata
        }
        metadata.setdefault("skill_id", item.get("skill_id"))
        safe.append({"type": item["type"], "metadata": metadata})
    return safe


def _agent_event_message(event_type: str, skill_id: Any) -> str:
    if event_type == "skill_plan_created":
        return "专家已创建内部 Skill Plan。"
    label = str(skill_id or "skill")
    messages = {
        "skill_started": f"{label} 开始执行。",
        "skill_completed": f"{label} 执行完成。",
        "skill_failed": f"{label} 执行失败。",
    }
    return messages[event_type]
