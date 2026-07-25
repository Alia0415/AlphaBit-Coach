"""AlphaOS FastAPI application entry point."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from backend.agents.router_agent import (
    RouteDecision,
    RouterAgent,
    RouterAgentError,
)
from backend.agents.manager_agent import ManagerAgent, ManagerAgentError
from backend.core.agent_registry import DEFAULT_EXPERTS
from backend.core.contracts import (
    AgentId,
    CoachGuide,
    CoachMessage,
    CoachNarration,
    ExecutionEvent,
    ExecutionPlan,
    ExpertInfo,
    ExpertResult,
    FollowupAnswer,
    OverviewStats,
    RESEARCH_DISCLAIMER,
    ReportDetail,
    ReportSummary,
    SkillInfo,
    TaskDetail,
    TaskExecutionResponse,
    TaskSummary,
)
from backend.core.evidence_validator import EvidenceValidator
from backend.core.coach_service import (
    MAX_NARRATIONS_PER_TASK,
    CoachService,
    CoachServiceError,
    validate_quoted_text,
)
from backend.core.policy_gate import PolicyGate
from backend.core.profile_service import UserProfileService
from backend.core.registry_factory import build_registry
from backend.core.reporting import build_report_record
from backend.core.result_aggregator import ResultAggregator
from backend.core.result_policy_checker import ResultPolicyChecker
from backend.core.store import get_store
from backend.core.task_interpreter import TaskInterpreter
from backend.core.task_spec import TaskSpec
from backend.core.user_profile import (
    PERSONAL_DECISION_REQUIRED_FIELDS,
    UserInvestmentProfile,
    UserProfilePatch,
    UserProfilePut,
)
from backend.core.workflow_executor import WorkflowExecutor
from backend.services.pandadata_client import (
    PandaDataClient,
    PandaDataConfigurationError,
)
from backend.services.stock_chart_service import (
    ChartRequest,
    StockChartError,
    StockChartService,
    StockDataUnavailableError,
    StockNotFoundError,
)
from backend.services.glossary_extractor import (
    GlossaryExtractionError,
    GlossaryExtractionResult,
    GlossaryExtractor,
)
from backend.services.ark_client import ArkClient, ArkClientError
from backend.skills.runtime_bootstrap import ensure_bundled_instruction_skills
from backend.skills.skill_registry import SkillRegistry


app = FastAPI(title="AlphaBit Coach API", version="0.4.0")
REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"
PUBLIC_DIR = REPO_ROOT / "public"
A2A_AGENT_CARD_PATH = "/.well-known/agent-card.json"
A2A_ENDPOINT_PATH = "/a2a"
A2A_TOKEN_ENV = "ALPHAOS_A2A_TOKEN"
A2A_PUBLIC_BASE_URL_ENV = "ALPHAOS_PUBLIC_BASE_URL"
app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="frontend-static",
)
app.mount(
    "/pixel",
    StaticFiles(directory=PUBLIC_DIR / "pixel"),
    name="pixel-sprites",
)
pandadata = PandaDataClient()
stock_charts = StockChartService(pandadata)
router = RouterAgent()
store = get_store()
ensure_bundled_instruction_skills()
skill_registry = SkillRegistry()
result_aggregator = ResultAggregator()
policy_gate = PolicyGate()


def _build_task_interpreter(
    client_factory: Any = ArkClient,
) -> TaskInterpreter:
    try:
        return TaskInterpreter(ark_client=client_factory())
    except ArkClientError:
        return TaskInterpreter()


task_interpreter = _build_task_interpreter()


def _build_coach_service(
    client_factory: Any = ArkClient,
) -> CoachService:
    try:
        return CoachService(ark_client=client_factory())
    except ArkClientError:
        return CoachService()


coach_service = _build_coach_service()
evidence_validator = EvidenceValidator()
result_policy_checker = ResultPolicyChecker()
manager = ManagerAgent(registry=build_registry(store))
workflow_executor = WorkflowExecutor(registry=build_registry(store))
glossary_extractor = GlossaryExtractor()


def _rebuild_experts() -> None:
    """Rebuild Manager and Executor with the current effective registry.

    The effective registry applies persisted enable/disable overrides, so a
    toggle takes effect for both planning and execution on the next request.
    """

    global manager, workflow_executor
    registry = build_registry(store)
    manager = ManagerAgent(registry=registry)
    workflow_executor = WorkflowExecutor(registry=registry)


class RouteRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        prompt = value.strip()
        if not prompt:
            raise ValueError("prompt 不能为空")
        return prompt


class ExpertToggleRequest(BaseModel):
    enabled: bool


class ClarifyRequest(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


class FollowupRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("question 不能为空")
        return question


class CoachAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    quoted_text: str | None = Field(default=None, max_length=500)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("question 不能为空")
        return question

    @field_validator("quoted_text")
    @classmethod
    def validate_quoted_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        quoted = value.strip()
        return quoted or None


class SessionResponse(BaseModel):
    task_id: str
    plan: ExecutionPlan | None
    action_required: str | None = None
    required_profile_fields: list[str] = Field(default_factory=list)


class UserProfileEnvelope(BaseModel):
    profile: UserInvestmentProfile | None
    derived_metrics: dict[str, int | float | None] = Field(default_factory=dict)


class MarketDataRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)
    start_date: str = Field(pattern=r"^\d{8}$")
    end_date: str = Field(pattern=r"^\d{8}$")
    fields: list[str] = Field(default_factory=list, max_length=100)
    indicator: str = Field(default="000300", pattern=r"^[A-Za-z0-9.]+$")
    st: bool = True

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().upper() for value in values]
        if any(
            not value
            or "." not in value
            or not all(part.isalnum() for part in value.split(".", maxsplit=1))
            for value in normalized
        ):
            raise ValueError("股票代码格式应类似 000001.SZ")
        return normalized

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or not value.replace("_", "").isalnum() for value in normalized):
            raise ValueError("字段名只能包含字母、数字和下划线")
        return normalized


class MarketDataResponse(BaseModel):
    source: str = "PandaData"
    symbols: list[str]
    start_date: str
    end_date: str
    data: Any


class A2AJsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


@app.get("/", include_in_schema=False)
async def frontend() -> RedirectResponse:
    return RedirectResponse(url="/office", status_code=307)


@app.get("/office", include_in_schema=False)
async def office_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "office" / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(A2A_AGENT_CARD_PATH)
async def a2a_agent_card(request: Request) -> dict[str, Any]:
    return _build_a2a_agent_card(request)


@app.get("/agent-card.json")
async def a2a_agent_card_compat(request: Request) -> dict[str, Any]:
    return _build_a2a_agent_card(request)


@app.post(A2A_ENDPOINT_PATH)
async def a2a_json_rpc(
    request: A2AJsonRpcRequest,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _verify_a2a_auth(authorization)
    try:
        if request.method == "message/send":
            task = await _a2a_send_message(request.params)
            return _json_rpc_result(request.id, task)
        if request.method == "tasks/get":
            task_id = _extract_a2a_task_id(request.params)
            return _json_rpc_result(request.id, _a2a_task_response(task_id))
    except HTTPException as exc:
        return _json_rpc_error(request.id, exc.status_code, str(exc.detail))
    except ManagerAgentError as exc:
        return _json_rpc_error(request.id, -32002, str(exc))
    return _json_rpc_error(
        request.id,
        -32601,
        f"Unsupported A2A method: {request.method}",
    )


@app.post("/a2a/message:send")
async def a2a_rest_message_send(
    params: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _verify_a2a_auth(authorization)
    return await _a2a_send_message(params)


@app.get("/a2a/tasks/{task_id}")
async def a2a_rest_task_get(
    task_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _verify_a2a_auth(authorization)
    return _a2a_task_response(task_id)


@app.get("/api/pandadata/status")
async def pandadata_status() -> dict[str, object]:
    return pandadata.status()


@app.get("/api/stocks")
async def list_stocks() -> dict[str, list[dict[str, str]]]:
    return {"stocks": stock_charts.list_stocks()}


@app.get("/api/stocks/search")
async def search_stocks(
    q: str = Query(default="", max_length=100),
) -> dict[str, Any]:
    return {"query": q.strip(), "stocks": stock_charts.search(q)}


@app.get("/api/stocks/{symbol}/chart")
async def stock_chart(
    symbol: str,
    period: str = Query(default="1d"),
    range_name: str = Query(default="1y", alias="range"),
    demo: bool = Query(default=False),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            stock_charts.chart,
            ChartRequest(
                symbol=symbol,
                period=period,
                range_name=range_name,
                force_demo=demo,
            ),
        )
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StockDataUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except StockChartError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/user-profile", response_model=UserProfileEnvelope)
async def get_user_profile() -> UserProfileEnvelope:
    return _profile_envelope(_profile_service().get())


@app.put("/api/user-profile", response_model=UserProfileEnvelope)
async def put_user_profile(request: UserProfilePut) -> UserProfileEnvelope:
    return _profile_envelope(_profile_service().put(request))


@app.patch("/api/user-profile", response_model=UserProfileEnvelope)
async def patch_user_profile(request: UserProfilePatch) -> UserProfileEnvelope:
    return _profile_envelope(_profile_service().patch(request))


@app.delete("/api/user-profile")
async def delete_user_profile() -> dict[str, bool]:
    return {"deleted": _profile_service().delete()}


@app.get("/api/user-profile/status")
async def user_profile_status() -> dict[str, Any]:
    return _profile_service().status()


# -- read-only surfaces ------------------------------------------------------


@app.get("/api/experts", response_model=list[ExpertInfo])
async def list_experts() -> list[ExpertInfo]:
    registry = build_registry(store)
    experts: list[ExpertInfo] = []
    for definition in DEFAULT_EXPERTS:
        effective = registry.get(definition.id)
        skills = [
            spec.id
            for spec in skill_registry.allowed_for_agent(definition.id.value)
        ]
        experts.append(
            ExpertInfo(
                id=effective.id.value,
                name=effective.name,
                description=effective.description,
                enabled=effective.enabled,
                capabilities=list(effective.capabilities),
                tools=list(effective.tools),
                skills=skills,
            )
        )
    return experts


@app.get("/api/skills", response_model=list[SkillInfo])
async def list_skills() -> list[SkillInfo]:
    return [
        SkillInfo(
            id=spec.id,
            name=spec.name,
            description=spec.description,
            mode=spec.mode.value,
            enabled=spec.enabled,
            owner_agents=list(spec.owner_agents),
            capabilities=list(spec.capabilities),
        )
        for spec in skill_registry.specs()
    ]


@app.get("/api/overview", response_model=OverviewStats)
async def overview() -> OverviewStats:
    registry = build_registry(store)
    counts = store.overview_counts()
    enabled_skills = sum(1 for spec in skill_registry.specs() if spec.enabled)
    return OverviewStats(
        enabled_experts=len(registry.ids(enabled_only=True)),
        enabled_skills=enabled_skills,
        total_tasks=counts["total_tasks"],
        completed_tasks=counts["completed_tasks"],
        report_count=counts["report_count"],
        average_completion=counts["average_completion"],
    )


@app.get("/api/tasks", response_model=list[TaskSummary])
async def list_tasks() -> list[TaskSummary]:
    return [TaskSummary(**row) for row in store.list_tasks()]


@app.get("/api/tasks/{task_id}", response_model=TaskDetail)
async def get_task(task_id: str) -> TaskDetail:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskDetail(**task)


@app.get("/api/reports", response_model=list[ReportSummary])
async def list_reports() -> list[ReportSummary]:
    return [ReportSummary(**row) for row in store.list_reports()]


@app.get("/api/reports/{report_id}", response_model=ReportDetail)
async def get_report(report_id: str) -> ReportDetail:
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return ReportDetail(**report)


@app.post(
    "/api/reports/{report_id}/glossary",
    response_model=GlossaryExtractionResult,
)
async def extract_report_glossary(report_id: str) -> GlossaryExtractionResult:
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    fragments = _aggregation_fragments(report.get("aggregation"))
    source = "\n".join(
        fragment["text"]
        for fragment in fragments
        if isinstance(fragment.get("text"), str)
    )
    if not source:
        return GlossaryExtractionResult(status="extracted", terms=[])
    try:
        terms = await run_in_threadpool(glossary_extractor.extract, source)
    except GlossaryExtractionError:
        return GlossaryExtractionResult(status="unavailable", terms=[])
    return GlossaryExtractionResult(status="extracted", terms=terms)


# -- expert enable/disable ---------------------------------------------------


@app.post("/api/experts/{agent_id}/enabled", response_model=ExpertInfo)
async def set_expert_enabled(
    agent_id: str,
    request: ExpertToggleRequest,
) -> ExpertInfo:
    try:
        expert = AgentId(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未知专家") from exc
    store.set_override(expert.value, request.enabled)
    _rebuild_experts()
    definition = build_registry(store).get(expert)
    return ExpertInfo(
        id=definition.id.value,
        name=definition.name,
        description=definition.description,
        enabled=definition.enabled,
        capabilities=list(definition.capabilities),
        tools=list(definition.tools),
        skills=[
            spec.id for spec in skill_registry.allowed_for_agent(expert.value)
        ],
    )


# -- planning session / clarify / stream -------------------------------------


@app.post("/api/tasks/sessions", response_model=SessionResponse)
async def create_session(request: RouteRequest) -> SessionResponse:
    task_id = uuid.uuid4().hex
    policy = policy_gate.evaluate(request.prompt)
    if not policy.allowed:
        raise HTTPException(status_code=422, detail=policy.safe_response)
    task_spec = await run_in_threadpool(task_interpreter.interpret, request.prompt, policy)
    profile_summary: dict[str, Any] | None = None
    if task_spec.task_type == "personal_investment_decision":
        profile = _profile_service().get()
        if profile is None or not profile.onboarding_completed:
            return _create_profile_action_session(
                task_id,
                request.prompt,
                "profile_onboarding_required",
                list(PERSONAL_DECISION_REQUIRED_FIELDS),
            )
        missing = profile.missing_fields(PERSONAL_DECISION_REQUIRED_FIELDS)
        if missing:
            return _create_profile_action_session(
                task_id,
                request.prompt,
                "profile_update_required",
                missing,
            )
        profile_summary = profile.risk_summary()
    try:
        if profile_summary is None:
            plan = await run_in_threadpool(
                manager.create_plan,
                task_spec,
                request.prompt,
            )
        else:
            task_spec = task_spec.model_copy(
                update={
                    "missing_fields": [],
                    "execution_decision": "execute_with_defaults",
                    "clarification_question": None,
                }
            )
            plan = await run_in_threadpool(
                manager.create_plan,
                task_spec,
                request.prompt,
                profile_summary,
            )
            plan = _attach_profile_to_risk(plan, profile_summary)
    except ManagerAgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    status = "needs_clarification" if plan.needs_clarification else "planned"
    store.create_task(
        task_id=task_id,
        prompt=request.prompt,
        status=status,
        plan=plan.model_dump(mode="json"),
    )
    store.append_event(
        task_id,
        type="plan_created",
        message="Manager Agent 已创建并验证动态任务图。",
        metadata={
            "step_count": len(plan.steps),
            "selected_agents": [
                selection.agent.value for selection in plan.selected_agents
            ],
        },
    )
    if plan.needs_clarification:
        store.append_event(
            task_id,
            type="clarification_required",
            message=plan.clarification_question or "任务需要补充关键信息。",
            metadata={
                "options": [
                    group.model_dump(mode="json")
                    for group in plan.clarification_options
                ]
            },
        )
    return SessionResponse(task_id=task_id, plan=plan)


@app.post("/api/tasks/{task_id}/clarify", response_model=SessionResponse)
async def clarify_session(task_id: str, request: ClarifyRequest) -> SessionResponse:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in {
        "profile_onboarding_required",
        "profile_update_required",
    }:
        raise HTTPException(
            status_code=409,
            detail="请先在用户画像页面完成所需更新，再重新提交个人投资任务。",
        )
    try:
        plan = await run_in_threadpool(
            manager.resume,
            task["prompt"],
            request.answers,
        )
    except ManagerAgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    status = "needs_clarification" if plan.needs_clarification else "planned"
    store.update_task_plan(task_id, status=status, plan=plan.model_dump(mode="json"))
    store.append_event(
        task_id,
        type="plan_created",
        message="Manager Agent 已根据澄清答案重新规划任务图。",
        metadata={
            "step_count": len(plan.steps),
            "selected_agents": [
                selection.agent.value for selection in plan.selected_agents
            ],
        },
    )
    if plan.needs_clarification:
        store.append_event(
            task_id,
            type="clarification_required",
            message=plan.clarification_question or "任务仍需补充关键信息。",
            metadata={
                "options": [
                    group.model_dump(mode="json")
                    for group in plan.clarification_options
                ]
            },
        )
    return SessionResponse(task_id=task_id, plan=plan)


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str) -> StreamingResponse:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["plan"] is None:
        raise HTTPException(status_code=409, detail="任务尚未生成计划")
    plan = ExecutionPlan.model_validate(task["plan"])
    prompt = task["prompt"]
    already_executed = task["status"] not in {"planned"}
    persisted_events = task["events"]
    profile = _profile_service().get()

    async def event_stream() -> Any:
        for event in persisted_events:
            yield _sse(event)
        if plan.needs_clarification or already_executed:
            yield _sse_named("done", {"task_id": task_id, "status": task["status"]})
            return

        queue: asyncio.Queue[Any] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # -- 过程陪练（投研课堂）：里程碑触发、异步生成、失败即跳过 --------------
        coach_tasks: list[asyncio.Task[None]] = []
        narration_count = 0
        pending_context: list[dict[str, Any]] = list(persisted_events)

        async def narrate(
            milestone: str,
            step_id: str | None,
            agent: str | None,
            context: list[dict[str, Any]],
        ) -> None:
            try:
                draft = await run_in_threadpool(
                    coach_service.narrate_milestone,
                    prompt,
                    context,
                    milestone,
                    profile,
                )
            except CoachServiceError:
                return  # 解说失败只跳过，绝不影响任务执行与聚合
            payload = {
                "milestone": milestone,
                "step_id": step_id,
                "agent": agent,
                "narration": draft.narration,
                "teaching_point": draft.teaching_point,
                "generated_by": "model",
            }
            seq = store.add_coach_narration(task_id, payload=payload)
            queue.put_nowait(
                ("__coach__", {"task_id": task_id, "seq": seq, **payload})
            )

        def trigger_narration(
            milestone: str,
            *,
            step_id: str | None = None,
            agent: str | None = None,
        ) -> None:
            nonlocal narration_count, pending_context
            if not coach_service.available:
                return
            if narration_count >= MAX_NARRATIONS_PER_TASK:
                return
            narration_count += 1
            context = pending_context
            pending_context = []
            coach_tasks.append(
                loop.create_task(narrate(milestone, step_id, agent, context))
            )

        def sink(event: ExecutionEvent) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def run() -> None:
            try:
                events, results = workflow_executor.execute(
                    plan, prompt, event_sink=sink
                )
                loop.call_soon_threadsafe(
                    queue.put_nowait, ("__done__", events, results)
                )
            except Exception as exc:  # surface failure to the stream, never hang
                loop.call_soon_threadsafe(queue.put_nowait, ("__error__", exc))

        loop.run_in_executor(None, run)
        trigger_narration("plan_created")

        results: dict[str, ExpertResult] = {}
        while True:
            item = await queue.get()
            if isinstance(item, tuple) and item and item[0] == "__coach__":
                yield _sse_named("coach", item[1])
                continue
            if isinstance(item, tuple) and item and item[0] == "__done__":
                results = item[2]
                break
            if isinstance(item, tuple) and item and item[0] == "__error__":
                store.finish_task(task_id, status="failed")
                yield _sse_named("error", {"detail": "任务执行失败"})
                return
            event = item
            _persist_event(task_id, event)
            event_dict = _event_to_dict(event)
            yield _sse(event_dict)
            pending_context.append(event_dict)
            if event.type in {"step_completed", "step_failed"}:
                trigger_narration(
                    event.type,
                    step_id=event.step_id,
                    agent=event.agent.value if event.agent else None,
                )

        synthesis = ExecutionEvent(
            type="synthesis_started",
            message="Result Aggregator 开始整理实际执行结果。",
            metadata={"component": "result_aggregator"},
        )
        _persist_event(task_id, synthesis)
        yield _sse(_event_to_dict(synthesis))

        aggregation = await run_in_threadpool(
            result_aggregator.aggregate, prompt, plan, results
        )
        completed = ExecutionEvent(
            type="task_completed",
            message={
                "completed": "AlphaBit Coach 任务成功完成。",
                "partially_completed": "AlphaBit Coach 任务部分完成。",
                "failed": "AlphaBit Coach 任务执行失败。",
                "needs_clarification": "AlphaBit Coach 任务需要补充信息。",
                "rejected": "AlphaBit Coach 任务已拒绝执行。",
            }.get(aggregation.completion_status, "AlphaBit Coach 任务处理结束。"),
            metadata={
                "status": aggregation.completion_status,
                "completed_steps": sum(
                    r.status == "completed" for r in results.values()
                ),
                "failed_steps": sum(
                    r.status in {"failed", "blocked"} for r in results.values()
                ),
            },
        )
        _persist_event(task_id, completed)
        yield _sse(_event_to_dict(completed))
        pending_context.append(_event_to_dict(completed))
        trigger_narration("task_completed")

        record = build_report_record(task_id, plan, aggregation, results)
        report_id = uuid.uuid4().hex
        store.create_report(
            report_id=report_id,
            task_id=task_id,
            title=record["title"],
            completeness=record["completeness"],
            aggregation=record["aggregation"],
        )
        store.finish_task(
            task_id,
            status=aggregation.completion_status,
            aggregation=aggregation.model_dump(mode="json"),
            final_answer=(
                f"{aggregation.direct_answer.headline}\n\n"
                f"{aggregation.direct_answer.explanation}"
            ),
        )
        yield _sse_named(
            "aggregation",
            {
                "report_id": report_id,
                "completeness": record["completeness"],
                "aggregation": record["aggregation"],
            },
        )
        # done 前短超时等待尚未完成的解说；超时则放弃（后台仍会落库供回放）
        if coach_tasks:
            await asyncio.wait(coach_tasks, timeout=8.0)
            while not queue.empty():
                item = queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__coach__":
                    yield _sse_named("coach", item[1])
        yield _sse_named(
            "done",
            {"task_id": task_id, "status": aggregation.completion_status},
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# -- report follow-up (deterministic evidence retrieval) ---------------------


@app.post("/api/reports/{report_id}/followup", response_model=FollowupAnswer)
async def report_followup(
    report_id: str,
    request: FollowupRequest,
) -> FollowupAnswer:
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    store.add_followup(
        followup_id=uuid.uuid4().hex,
        report_id=report_id,
        role="user",
        text=request.question,
    )
    evidence = _retrieve_evidence(report.get("aggregation"), request.question)
    answer_text = (
        "以下为报告内证据检索结果，未调用模型，也不构成新的分析。"
        if evidence
        else "报告证据中未检索到与该问题直接相关的片段，请参考完整报告或补充提问。"
    )
    return FollowupAnswer.model_validate(
        store.add_followup(
            followup_id=uuid.uuid4().hex,
            report_id=report_id,
            role="assistant",
            text=answer_text,
            evidence=evidence,
        )
    )


# -- coach layer (model-driven learning companion) ----------------------------


@app.post("/api/reports/{report_id}/coach", response_model=CoachMessage)
async def report_coach_ask(
    report_id: str,
    request: CoachAskRequest,
) -> CoachMessage:
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if request.quoted_text is not None and not validate_quoted_text(
        report.get("aggregation"), request.quoted_text
    ):
        raise HTTPException(
            status_code=422,
            detail="引用片段必须来自报告正文，请重新选择后再提问。",
        )
    profile = _profile_service().get()
    try:
        reply = await run_in_threadpool(
            coach_service.answer,
            report,
            request.question,
            request.quoted_text,
            profile,
        )
    except CoachServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    store.add_coach_message(
        message_id=uuid.uuid4().hex,
        report_id=report_id,
        role="user",
        text=request.question,
        payload={"quoted_text": request.quoted_text, "generated_by": "user"},
    )
    coach_record = store.add_coach_message(
        message_id=uuid.uuid4().hex,
        report_id=report_id,
        role="coach",
        text=reply.answer,
        payload={
            "quoted_text": request.quoted_text,
            "concept_notes": [note.model_dump() for note in reply.concept_notes],
            "cited_evidence": reply.cited_evidence,
            "uncertainty_note": reply.uncertainty_note,
            "is_general_knowledge_included": reply.is_general_knowledge_included,
            "generated_by": "model",
        },
    )
    return CoachMessage.model_validate(coach_record)


@app.get("/api/reports/{report_id}/coach/guide", response_model=CoachGuide)
async def report_coach_guide(
    report_id: str,
    refresh: bool = False,
) -> CoachGuide:
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if not refresh:
        cached = store.get_coach_guide(report_id)
        if cached is not None:
            return CoachGuide.model_validate(cached)
    profile = _profile_service().get()
    try:
        guide = await run_in_threadpool(
            coach_service.build_guide, report, profile
        )
    except CoachServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    store.save_coach_guide(report_id, guide.model_dump(mode="json"))
    return guide


@app.get(
    "/api/tasks/{task_id}/coach-narrations",
    response_model=list[CoachNarration],
)
async def task_coach_narrations(task_id: str) -> list[CoachNarration]:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return [
        CoachNarration.model_validate(record)
        for record in store.list_coach_narrations(task_id)
    ]


# -- legacy endpoints (kept for compatibility) -------------------------------


@app.post("/api/route", response_model=RouteDecision, deprecated=True)
async def route_request(request: RouteRequest) -> RouteDecision:
    try:
        return await run_in_threadpool(router.route, request.prompt)
    except RouterAgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/plan", response_model=ExecutionPlan)
async def plan_request(request: RouteRequest) -> ExecutionPlan:
    try:
        return await run_in_threadpool(manager.create_plan, request.prompt)
    except ManagerAgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/tasks", response_model=TaskExecutionResponse)
async def execute_task(request: RouteRequest) -> TaskExecutionResponse:
    started_at = perf_counter()
    task_id = uuid.uuid4().hex
    try:
        policy = policy_gate.evaluate(request.prompt)
        if not policy.allowed:
            aggregation = result_policy_checker.check(
                result_aggregator.build_boundary_response(request.prompt, policy)
            )
            events = [
                ExecutionEvent(
                    type="policy_checked",
                    message="AlphaBit Coach 已完成请求边界判断。",
                    metadata={
                        "decision": policy.decision,
                        "allowed": False,
                        "policy_tags": policy.policy_tags,
                    },
                ),
                ExecutionEvent(
                    type="result_policy_checked",
                    message="AlphaBit Coach 已完成最终结果合规检查。",
                    metadata={"policy_rewrite": aggregation.metadata["policy_rewrite"]},
                ),
                ExecutionEvent(
                    type="task_completed",
                    message="AlphaBit Coach 已返回能力边界说明。",
                    metadata={"completed_steps": 0, "failed_steps": 0},
                ),
            ]
            return TaskExecutionResponse(
                plan=None,
                events=events,
                results={},
                aggregation=aggregation,
                final_answer=(
                    f"{aggregation.direct_answer.headline}\n\n"
                    f"{aggregation.direct_answer.explanation}"
                ),
                duration_ms=max(
                    0,
                    round((perf_counter() - started_at) * 1000),
                ),
                disclaimer=RESEARCH_DISCLAIMER,
            )

        task_spec = await run_in_threadpool(task_interpreter.interpret, request.prompt, policy)
        profile: UserInvestmentProfile | None = None
        profile_summary: dict[str, Any] | None = None
        if task_spec.task_type == "personal_investment_decision":
            profile = _profile_service().get()
            if profile is None or not profile.onboarding_completed:
                return _profile_action_task_response(
                    task_spec,
                    action="profile_onboarding_required",
                    missing_fields=list(PERSONAL_DECISION_REQUIRED_FIELDS),
                    started_at=started_at,
                )
            missing_profile_fields = profile.missing_fields(
                PERSONAL_DECISION_REQUIRED_FIELDS
            )
            if missing_profile_fields:
                return _profile_action_task_response(
                    task_spec,
                    action="profile_update_required",
                    missing_fields=missing_profile_fields,
                    started_at=started_at,
                )
            task_spec = task_spec.model_copy(
                update={
                    "missing_fields": [],
                    "execution_decision": "execute_with_defaults",
                    "clarification_question": None,
                }
            )
            profile_summary = profile.risk_summary()
        if task_spec.execution_decision == "clarify":
            aggregation = result_policy_checker.check(
                result_aggregator.build_clarification_response(task_spec)
            )
            events = [
                ExecutionEvent(
                    type="clarification_required",
                    message=task_spec.clarification_question
                    or "任务需要补充关键信息。",
                    metadata={"missing_fields": task_spec.missing_fields},
                ),
                ExecutionEvent(
                    type="task_completed",
                    message="AlphaBit Coach 已返回澄清请求。",
                    metadata={"completed_steps": 0, "failed_steps": 0},
                ),
            ]
            return TaskExecutionResponse(
                plan=None,
                events=events,
                results={},
                aggregation=aggregation,
                final_answer=(
                    f"{aggregation.direct_answer.headline}\n\n"
                    f"{aggregation.direct_answer.explanation}"
                ),
                duration_ms=max(
                    0,
                    round((perf_counter() - started_at) * 1000),
                ),
                disclaimer=RESEARCH_DISCLAIMER,
            )

        if profile_summary is None:
            plan = await run_in_threadpool(
                manager.create_plan,
                task_spec,
                request.prompt,
            )
        else:
            plan = await run_in_threadpool(
                manager.create_plan,
                task_spec,
                request.prompt,
                profile_summary,
            )
            plan = _attach_profile_to_risk(plan, profile_summary)
        status = "needs_clarification" if plan.needs_clarification else "running"
        store.create_task(
            task_id=task_id,
            prompt=request.prompt,
            status=status,
            plan=plan.model_dump(mode="json"),
        )
        events = [
            ExecutionEvent(
                type="plan_created",
                message="Manager Agent 已创建并验证动态任务图。",
                metadata={
                    "step_count": len(plan.steps),
                    "selected_agents": [
                        selection.agent.value
                        for selection in plan.selected_agents
                    ],
                },
            )
        ]
        results: dict[str, ExpertResult]
        if plan.needs_clarification:
            events.append(
                ExecutionEvent(
                    type="clarification_required",
                    message=plan.clarification_question
                    or "任务需要补充关键信息。",
                )
            )
            results = {}
            clarification_spec = task_spec.model_copy(
                update={
                    "execution_decision": "clarify",
                    "clarification_question": plan.clarification_question,
                }
            )
            aggregation = result_policy_checker.check(
                result_aggregator.build_clarification_response(
                    clarification_spec
                )
            )
        else:
            execution_events, results = await run_in_threadpool(
                workflow_executor.execute,
                plan,
                request.prompt,
            )
            events.extend(execution_events)
            events.append(
                ExecutionEvent(
                    type="synthesis_started",
                    message="Result Aggregator 开始整理实际执行结果。",
                    metadata={"component": "result_aggregator"},
                )
            )
            evidence_validation = await run_in_threadpool(
                evidence_validator.validate,
                task_spec,
                plan,
                results,
            )
            aggregation = await run_in_threadpool(
                result_aggregator.aggregate,
                task_spec,
                plan,
                evidence_validation,
            )
            aggregation = await run_in_threadpool(
                result_policy_checker.check,
                aggregation,
            )
        final_answer = (
            f"{aggregation.direct_answer.headline}\n\n"
            f"{aggregation.direct_answer.explanation}"
        )
        events.append(
            ExecutionEvent(
                type="task_completed",
                message="AlphaBit Coach 任务处理完成。",
                metadata={
                    "completed_steps": sum(
                        result.status == "completed"
                        for result in results.values()
                    ),
                    "failed_steps": sum(
                        result.status in {"failed", "blocked"}
                        for result in results.values()
                    ),
                },
            )
        )
    except ManagerAgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    for event in events:
        _persist_event(task_id, event)
    if not plan.needs_clarification:
        record = build_report_record(task_id, plan, aggregation, results)
        store.create_report(
            report_id=uuid.uuid4().hex,
            task_id=task_id,
            title=record["title"],
            completeness=record["completeness"],
            aggregation=record["aggregation"],
        )
    store.finish_task(
        task_id,
        status=aggregation.completion_status,
        aggregation=aggregation.model_dump(mode="json"),
        final_answer=final_answer,
        duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
    )
    return TaskExecutionResponse(
        plan=plan,
        events=events,
        results=results,
        aggregation=aggregation,
        final_answer=final_answer,
        duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
        disclaimer=RESEARCH_DISCLAIMER,
    )


@app.post("/api/market-data", response_model=MarketDataResponse)
async def market_data(request: MarketDataRequest) -> MarketDataResponse:
    if request.start_date > request.end_date:
        raise HTTPException(status_code=422, detail="start_date 不能晚于 end_date")
    try:
        data = await run_in_threadpool(
            pandadata.get_market_data,
            symbols=request.symbols,
            start_date=request.start_date,
            end_date=request.end_date,
            fields=request.fields,
            indicator=request.indicator,
            st=request.st,
        )
    except PandaDataConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PandaData 调用失败: {exc}") from exc
    return MarketDataResponse(
        symbols=request.symbols,
        start_date=request.start_date,
        end_date=request.end_date,
        data=data,
    )


# -- helpers -----------------------------------------------------------------


def _profile_service() -> UserProfileService:
    return UserProfileService(store)


def _profile_envelope(
    profile: UserInvestmentProfile | None,
) -> UserProfileEnvelope:
    if profile is None:
        return UserProfileEnvelope(profile=None)
    return UserProfileEnvelope(
        profile=profile,
        derived_metrics={
            "monthly_surplus_cny": profile.monthly_surplus_cny,
            "essential_cash_outflow_cny": profile.essential_cash_outflow_cny,
            "savings_rate": profile.savings_rate,
            "emergency_fund_months": profile.emergency_fund_months,
            "debt_payment_ratio": profile.debt_payment_ratio,
            "known_portfolio_value_cny": profile.known_portfolio_value_cny,
            "largest_position_ratio": profile.largest_position_ratio,
            "profile_completeness": profile.profile_completeness,
        },
    )


def _build_a2a_agent_card(request: Request) -> dict[str, Any]:
    base_url = os.environ.get(A2A_PUBLIC_BASE_URL_ENV)
    if not base_url:
        base_url = str(request.base_url).rstrip("/")
    else:
        base_url = base_url.rstrip("/")
    token_configured = bool(os.environ.get(A2A_TOKEN_ENV))
    specs = [spec for spec in skill_registry.specs() if spec.enabled]
    return {
        "name": "AlphaOS Quant Research Organization",
        "description": (
            "Autonomous multi-agent AI quant research organization. "
            "The Manager Agent dynamically plans a validated expert DAG, "
            "expert agents execute authorized research Skills, and the "
            "Result Aggregator returns evidence-bounded explanations."
        ),
        "version": app.version,
        "protocolVersion": "0.3.0",
        "url": f"{base_url}{A2A_ENDPOINT_PATH}",
        "documentationUrl": f"{base_url}/",
        "preferredTransport": "JSONRPC",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "securitySchemes": (
            {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": f"Set by {A2A_TOKEN_ENV}.",
                }
            }
            if token_configured
            else {}
        ),
        "security": [{"bearerAuth": []}] if token_configured else [],
        "provider": {
            "organization": "AlphaOS",
            "url": base_url,
        },
        "skills": [
            {
                "id": "multi_agent_quant_research",
                "name": "multi_agent_quant_research",
                "description": (
                    "Handle natural-language quant, market, company, macro, "
                    "factor, and risk research tasks through dynamic expert "
                    "selection and DAG execution."
                ),
                "tags": ["quant-research", "multi-agent", "A-share"],
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain", "application/json"],
                "examples": [
                    "分析 000001.SZ 过去一年的股价表现和主要风险。",
                    "计算 000001.SZ、000002.SZ 在 2024 年的 R020，并说明局限。",
                    "扫描 600519.SH 从 20260401 到 20260725 的事件风险。",
                ],
            },
            *[
                {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "tags": [*spec.owner_agents, *spec.capabilities],
                    "inputModes": ["text/plain", "application/json"],
                    "outputModes": ["text/plain", "application/json"],
                }
                for spec in specs
            ],
        ],
    }


def _verify_a2a_auth(authorization: str | None) -> None:
    expected = os.environ.get(A2A_TOKEN_ENV)
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="A2A Bearer token is invalid")


async def _a2a_send_message(params: dict[str, Any]) -> dict[str, Any]:
    prompt = _extract_a2a_prompt(params)
    if not prompt:
        raise HTTPException(status_code=422, detail="A2A message text is required")
    task_id = str(
        params.get("taskId")
        or params.get("id")
        or params.get("message", {}).get("taskId")
        or uuid.uuid4().hex
    )
    response = await _execute_a2a_prompt(task_id, prompt)
    return _a2a_task_from_execution(task_id, prompt, response)


async def _execute_a2a_prompt(
    task_id: str,
    prompt: str,
) -> TaskExecutionResponse:
    started_at = perf_counter()
    plan: ExecutionPlan | None = None
    results: dict[str, ExpertResult] = {}
    try:
        policy = policy_gate.evaluate(prompt)
        if not policy.allowed:
            aggregation = result_policy_checker.check(
                result_aggregator.build_boundary_response(prompt, policy)
            )
            events = [
                ExecutionEvent(
                    type="policy_checked",
                    message="AlphaOS 已完成请求边界判断。",
                    metadata={
                        "decision": policy.decision,
                        "allowed": False,
                        "policy_tags": policy.policy_tags,
                    },
                ),
                ExecutionEvent(
                    type="result_policy_checked",
                    message="AlphaOS 已完成最终结果合规检查。",
                    metadata={"policy_rewrite": aggregation.metadata["policy_rewrite"]},
                ),
                ExecutionEvent(
                    type="task_completed",
                    message="AlphaOS 已返回能力边界说明。",
                    metadata={"completed_steps": 0, "failed_steps": 0},
                ),
            ]
            final_answer = (
                f"{aggregation.direct_answer.headline}\n\n"
                f"{aggregation.direct_answer.explanation}"
            )
            _persist_a2a_task(
                task_id,
                prompt,
                "rejected",
                None,
                events,
                aggregation,
                final_answer,
                started_at,
            )
            return TaskExecutionResponse(
                plan=None,
                events=events,
                results={},
                aggregation=aggregation,
                final_answer=final_answer,
                duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
                disclaimer=RESEARCH_DISCLAIMER,
            )

        task_spec = await run_in_threadpool(task_interpreter.interpret, prompt, policy)
        profile_summary: dict[str, Any] | None = None
        if task_spec.task_type == "personal_investment_decision":
            profile = _profile_service().get()
            if profile is None or not profile.onboarding_completed:
                task_spec = task_spec.model_copy(
                    update={
                        "execution_decision": "clarify",
                        "missing_fields": list(PERSONAL_DECISION_REQUIRED_FIELDS),
                        "clarification_question": (
                            "这是个人投资决策。请先进入 AlphaOS 用户画像完成建档；"
                            "画像完成前不会给出买卖或具体仓位建议。"
                        ),
                    }
                )
            else:
                missing = profile.missing_fields(PERSONAL_DECISION_REQUIRED_FIELDS)
                if missing:
                    task_spec = task_spec.model_copy(
                        update={
                            "execution_decision": "clarify",
                            "missing_fields": missing,
                            "clarification_question": (
                                "当前个人投资任务仍缺少必要画像字段："
                                + "、".join(missing)
                                + "。请先补充用户画像。"
                            ),
                        }
                    )
                else:
                    task_spec = task_spec.model_copy(
                        update={
                            "missing_fields": [],
                            "execution_decision": "execute_with_defaults",
                            "clarification_question": None,
                        }
                    )
                    profile_summary = profile.risk_summary()

        if task_spec.execution_decision == "clarify":
            aggregation = result_policy_checker.check(
                result_aggregator.build_clarification_response(task_spec)
            )
            events = [
                ExecutionEvent(
                    type="clarification_required",
                    message=task_spec.clarification_question
                    or "任务需要补充关键信息。",
                    metadata={"missing_fields": task_spec.missing_fields},
                ),
                ExecutionEvent(
                    type="task_completed",
                    message="AlphaOS 已返回澄清请求。",
                    metadata={"completed_steps": 0, "failed_steps": 0},
                ),
            ]
            final_answer = (
                f"{aggregation.direct_answer.headline}\n\n"
                f"{aggregation.direct_answer.explanation}"
            )
            _persist_a2a_task(
                task_id,
                prompt,
                "needs_clarification",
                None,
                events,
                aggregation,
                final_answer,
                started_at,
            )
            return TaskExecutionResponse(
                plan=None,
                events=events,
                results={},
                aggregation=aggregation,
                final_answer=final_answer,
                duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
                disclaimer=RESEARCH_DISCLAIMER,
            )

        if profile_summary is None:
            plan = await run_in_threadpool(manager.create_plan, task_spec, prompt)
        else:
            plan = await run_in_threadpool(
                manager.create_plan,
                task_spec,
                prompt,
                profile_summary,
            )
            plan = _attach_profile_to_risk(plan, profile_summary)

        events = [
            ExecutionEvent(
                type="plan_created",
                message="Manager Agent 已创建并验证动态任务图。",
                metadata={
                    "step_count": len(plan.steps),
                    "selected_agents": [
                        selection.agent.value for selection in plan.selected_agents
                    ],
                },
            )
        ]
        if plan.needs_clarification:
            events.append(
                ExecutionEvent(
                    type="clarification_required",
                    message=plan.clarification_question or "任务需要补充关键信息。",
                )
            )
            clarification_spec = task_spec.model_copy(
                update={
                    "execution_decision": "clarify",
                    "clarification_question": plan.clarification_question,
                }
            )
            aggregation = result_policy_checker.check(
                result_aggregator.build_clarification_response(clarification_spec)
            )
        else:
            execution_events, results = await run_in_threadpool(
                workflow_executor.execute,
                plan,
                prompt,
            )
            events.extend(execution_events)
            events.append(
                ExecutionEvent(
                    type="synthesis_started",
                    message="Result Aggregator 开始整理实际执行结果。",
                    metadata={"component": "result_aggregator"},
                )
            )
            evidence_validation = await run_in_threadpool(
                evidence_validator.validate,
                task_spec,
                plan,
                results,
            )
            aggregation = await run_in_threadpool(
                result_aggregator.aggregate,
                task_spec,
                plan,
                evidence_validation,
            )
            aggregation = await run_in_threadpool(
                result_policy_checker.check,
                aggregation,
            )
        final_answer = (
            f"{aggregation.direct_answer.headline}\n\n"
            f"{aggregation.direct_answer.explanation}"
        )
        events.append(
            ExecutionEvent(
                type="task_completed",
                message="AlphaOS 任务处理完成。",
                metadata={
                    "completed_steps": sum(
                        result.status == "completed" for result in results.values()
                    ),
                    "failed_steps": sum(
                        result.status in {"failed", "blocked"}
                        for result in results.values()
                    ),
                },
            )
        )
        _persist_a2a_task(
            task_id,
            prompt,
            aggregation.completion_status,
            plan,
            events,
            aggregation,
            final_answer,
            started_at,
        )
        if plan is not None and not plan.needs_clarification:
            record = build_report_record(task_id, plan, aggregation, results)
            store.create_report(
                report_id=uuid.uuid4().hex,
                task_id=task_id,
                title=record["title"],
                completeness=record["completeness"],
                aggregation=record["aggregation"],
            )
        return TaskExecutionResponse(
            plan=plan,
            events=events,
            results=results,
            aggregation=aggregation,
            final_answer=final_answer,
            duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
            disclaimer=RESEARCH_DISCLAIMER,
        )
    except ManagerAgentError:
        store.create_task(task_id=task_id, prompt=prompt, status="failed", plan=None)
        raise


def _persist_a2a_task(
    task_id: str,
    prompt: str,
    status: str,
    plan: ExecutionPlan | None,
    events: list[ExecutionEvent],
    aggregation: Any,
    final_answer: str,
    started_at: float,
) -> None:
    existing = store.get_task(task_id)
    if existing is None:
        store.create_task(
            task_id=task_id,
            prompt=prompt,
            status="running",
            plan=plan.model_dump(mode="json") if plan is not None else None,
            owner="a2a",
        )
    for event in events:
        _persist_event(task_id, event)
    store.finish_task(
        task_id,
        status=status,
        aggregation=aggregation.model_dump(mode="json"),
        final_answer=final_answer,
        duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
    )


def _extract_a2a_prompt(params: dict[str, Any]) -> str:
    for key in ("prompt", "text", "query"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    message = params.get("message")
    if not isinstance(message, dict):
        return ""
    for key in ("text", "content"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    parts = message.get("parts", [])
    texts: list[str] = []
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            root = part.get("text") or part.get("data")
            if isinstance(root, str) and root.strip():
                texts.append(root.strip())
                continue
            text_part = part.get("text")
            if isinstance(text_part, dict):
                text = text_part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    return "\n".join(texts).strip()


def _extract_a2a_task_id(params: dict[str, Any]) -> str:
    task_id = params.get("id") or params.get("taskId")
    if not isinstance(task_id, str) or not task_id.strip():
        raise HTTPException(status_code=422, detail="A2A task id is required")
    return task_id.strip()


def _a2a_task_from_execution(
    task_id: str,
    prompt: str,
    response: TaskExecutionResponse,
) -> dict[str, Any]:
    state = _a2a_state(response.aggregation.completion_status)
    return {
        "kind": "task",
        "id": task_id,
        "contextId": task_id,
        "status": {
            "state": state,
            "message": {
                "kind": "message",
                "role": "agent",
                "messageId": f"{task_id}-status",
                "parts": [{"kind": "text", "text": response.final_answer}],
            },
        },
        "history": [
            {
                "kind": "message",
                "role": "user",
                "messageId": f"{task_id}-user",
                "parts": [{"kind": "text", "text": prompt}],
            }
        ],
        "artifacts": [
            {
                "artifactId": f"{task_id}-answer",
                "name": "AlphaOS Research Result",
                "parts": [
                    {"kind": "text", "text": response.final_answer},
                    {
                        "kind": "data",
                        "data": response.model_dump(mode="json"),
                    },
                ],
            }
        ],
        "metadata": {
            "duration_ms": response.duration_ms,
            "completion_status": response.aggregation.completion_status,
            "selected_agents": (
                [
                    selection.agent.value
                    for selection in response.plan.selected_agents
                ]
                if response.plan is not None
                else []
            ),
            "disclaimer": response.disclaimer,
        },
    }


def _a2a_task_response(task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="A2A task not found")
    state = _a2a_state(task["status"])
    final_answer = task.get("final_answer") or ""
    return {
        "kind": "task",
        "id": task["id"],
        "contextId": task["id"],
        "status": {
            "state": state,
            "message": {
                "kind": "message",
                "role": "agent",
                "messageId": f"{task['id']}-status",
                "parts": [{"kind": "text", "text": final_answer}],
            },
        },
        "artifacts": [
            {
                "artifactId": f"{task['id']}-answer",
                "name": "AlphaOS Research Result",
                "parts": [
                    {"kind": "text", "text": final_answer},
                    {
                        "kind": "data",
                        "data": {
                            "plan": task.get("plan"),
                            "aggregation": task.get("aggregation"),
                            "events": task.get("events"),
                            "duration_ms": task.get("duration_ms"),
                        },
                    },
                ],
            }
        ],
        "metadata": {
            "completion_status": task["status"],
            "created_at": task["created_at"],
            "duration_ms": task.get("duration_ms"),
        },
    }


def _a2a_state(status: str) -> str:
    if status in {"completed", "partially_completed", "rejected"}:
        return "completed"
    if status in {"needs_clarification", "profile_onboarding_required", "profile_update_required"}:
        return "input-required"
    if status == "failed":
        return "failed"
    return "working"


def _json_rpc_result(request_id: str | int | None, result: Any) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "result": result}
    )


def _json_rpc_error(
    request_id: str | int | None,
    code: int,
    message: str,
) -> JSONResponse:
    status_code = code if 400 <= code < 600 else 200
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        },
        status_code=status_code,
    )


def _profile_action_task_response(
    task_spec: TaskSpec,
    *,
    action: Literal[
        "profile_onboarding_required",
        "profile_update_required",
    ],
    missing_fields: list[str],
    started_at: float,
) -> JSONResponse:
    onboarding = action == "profile_onboarding_required"
    missing_labels = [
        "投资知识水平" if field == "investment_experience" else field
        for field in missing_fields
    ]
    explanation = (
        "这是个人投资决策。请先进入“用户画像”完成一次建档；"
        "建档唯一必答项是投资知识水平，其余画像问题可以一次性跳过并保持为空。"
        "画像完成前不会创建专家任务图，也不会给出买卖或具体仓位建议。"
        if onboarding
        else "当前个人投资任务仍缺少必要画像字段："
        + "、".join(missing_labels)
        + "。请在“用户画像”页面补充这些字段，不会重新启动整套问卷。"
    )
    clarification = task_spec.model_copy(
        update={
            "missing_fields": missing_fields,
            "execution_decision": "clarify",
            "clarification_question": explanation,
        }
    )
    aggregation = result_policy_checker.check(
        result_aggregator.build_clarification_response(clarification)
    )
    aggregation = aggregation.model_copy(
        update={
            "direct_answer": aggregation.direct_answer.model_copy(
                update={
                    "headline": (
                        "需要先完成用户画像"
                        if onboarding
                        else "需要补充用户画像"
                    ),
                    "explanation": explanation,
                }
            )
        }
    )
    duration_ms = max(0, round((perf_counter() - started_at) * 1000))
    events = [
        ExecutionEvent(
            type="clarification_required",
            message=explanation,
            metadata={
                "action_required": action,
                "missing_fields": missing_fields,
            },
        ),
        ExecutionEvent(
            type="task_completed",
            message="AlphaBit Coach 已在创建任务图前暂停个人投资决策。",
            metadata={"completed_steps": 0, "failed_steps": 0},
        ),
    ]
    response = TaskExecutionResponse(
        plan=None,
        events=events,
        results={},
        aggregation=aggregation,
        final_answer=f"{aggregation.direct_answer.headline}\n\n{explanation}",
        duration_ms=duration_ms,
        disclaimer=RESEARCH_DISCLAIMER,
    )
    return JSONResponse(
        content={
            **response.model_dump(mode="json"),
            "action_required": action,
            "required_profile_fields": missing_fields,
        }
    )


def _create_profile_action_session(
    task_id: str,
    prompt: str,
    action: Literal[
        "profile_onboarding_required",
        "profile_update_required",
    ],
    missing_fields: list[str],
) -> SessionResponse:
    message = (
        "请先完成首次用户画像建档；唯一必答项为投资知识水平，其余问题可跳过。"
        if action == "profile_onboarding_required"
        else "请在用户画像页面补充当前任务所需字段。"
    )
    store.create_task(
        task_id=task_id,
        prompt=prompt,
        status=action,
        plan=None,
    )
    store.append_event(
        task_id,
        type="clarification_required",
        message=message,
        metadata={
            "action_required": action,
            "missing_fields": missing_fields,
        },
    )
    return SessionResponse(
        task_id=task_id,
        plan=None,
        action_required=action,
        required_profile_fields=missing_fields,
    )


def _attach_profile_to_risk(
    plan: ExecutionPlan,
    summary: dict[str, Any],
) -> ExecutionPlan:
    """Attach the minimal canonical summary only to selected Risk steps."""

    steps = [
        step.model_copy(
            update={
                "inputs": {
                    **step.inputs,
                    "risk_context": summary,
                }
            }
        )
        if step.agent == AgentId.RISK
        else step
        for step in plan.steps
    ]
    return plan.model_copy(update={"steps": steps})


def _event_to_dict(event: ExecutionEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


def _persist_event(task_id: str, event: ExecutionEvent) -> None:
    store.append_event(
        task_id,
        type=event.type,
        message=event.message,
        agent=event.agent.value if event.agent else None,
        step_id=event.step_id,
        metadata=event.metadata,
        ts=event.timestamp.isoformat(),
    )


def _sse(data: dict[str, Any]) -> str:
    return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


def _sse_named(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\n" + "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


def _retrieve_evidence(
    aggregation: dict[str, Any] | None,
    question: str,
) -> list[dict[str, Any]]:
    """Deterministically rank stored evidence fragments against the question."""

    fragments = _aggregation_fragments(aggregation)
    if not fragments:
        return []
    terms = _query_terms(question)
    if not terms:
        return []

    scored: list[dict[str, Any]] = []
    for fragment in fragments:
        haystack = fragment["text"].lower()
        score = sum(haystack.count(term) for term in terms)
        if score > 0:
            scored.append({**fragment, "score": score})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:5]


def _query_terms(question: str) -> list[str]:
    """Build match terms: latin/number word tokens plus CJK character bigrams.

    Chinese has no whitespace tokens, so a whole phrase would form one oversized
    token that never matches. Emitting CJK bigrams keeps retrieval deterministic
    while actually matching Chinese report text.
    """

    lowered = question.lower()
    terms: set[str] = set()
    for token in re.split(r"\W+", lowered):
        if len(token) >= 2 and token.isascii():
            terms.add(token)
    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[i : i + 2] for i in range(len(run) - 1))
    return list(terms)


def _aggregation_fragments(
    aggregation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(aggregation, dict):
        return []
    fragments: list[dict[str, Any]] = []
    direct = aggregation.get("direct_answer")
    if isinstance(direct, dict):
        for key in ("headline", "explanation"):
            text = direct.get(key)
            if isinstance(text, str) and text.strip():
                fragments.append({"source": f"direct_answer.{key}", "text": text.strip()})
    for block in aggregation.get("content_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        source = block.get("id") or block.get("type") or "block"
        for key in ("title", "description"):
            text = block.get(key)
            if isinstance(text, str) and text.strip():
                fragments.append({"source": str(source), "text": text.strip()})
        data = block.get("data")
        rendered = _stringify_block_data(data)
        if rendered:
            fragments.append({"source": str(source), "text": rendered})
    return fragments


def _stringify_block_data(data: Any) -> str:
    texts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if value.strip():
                texts.append(value.strip())
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return " ".join(texts)[:2_000]
