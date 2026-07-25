"""The planning page must render only backend-owned ResearchRunState."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "office" / "js" / "app.js").read_text(
    encoding="utf-8"
)
LIVE = (ROOT / "frontend" / "office" / "js" / "live.js").read_text(
    encoding="utf-8"
)
API = (ROOT / "frontend" / "office" / "js" / "api.js").read_text(
    encoding="utf-8"
)


def _planning_page_source() -> str:
    start = APP.index("function pageManagerPlanningLive")
    end = APP.index("function pageWarRoomLive", start)
    return APP[start:end]


def test_planning_page_uses_backend_progress_and_elapsed_time() -> None:
    source = _planning_page_source()
    assert "state.progress" in source
    assert "state.elapsedMs" in source
    assert "state.estimatedRemainingMs" in source
    assert "state?.selectedAgents" in source
    assert "setInterval" not in source
    assert "尚未返回选择结果" in source


def test_research_run_sse_recovers_through_status_endpoint() -> None:
    assert '"/api/research/runs"' in API
    assert "/status" in API
    assert "/events" in API
    assert "new EventSource(api.researchRunEventsUrl(runId))" in LIVE
    assert "await api.researchRunStatus(runId)" in LIVE
    assert 'workflow_mode: queryContext.workflowMode || "dynamic"' in API
    assert 'workflowMode: state.workflow_mode || "dynamic"' in LIVE


def test_live_planning_no_longer_waits_for_blocking_session_response() -> None:
    begin_start = APP.index("function beginLiveResearch")
    begin_end = APP.index("// ---------------------------------------------------------------------------", begin_start)
    source = APP[begin_start:begin_end]
    assert "startResearchRun(normalizedPrompt, versions)" in source
    assert "openResearchRunStream(runId" in source
    assert "liveCreateSession" not in source
    assert '"重新尝试"' in APP


def test_fixed_stock_planning_is_labeled_as_a_preset() -> None:
    source = _planning_page_source()
    assert 'state?.workflowMode === "stock_analysis"' in source
    assert "固定 Agent 工作流 · 效率优先" in source
    assert "固定研究编排器" in source
