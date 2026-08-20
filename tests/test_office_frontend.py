import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_office_keeps_only_backend_supported_navigation() -> None:
    response = client.get("/static/office/js/app.js")

    assert response.status_code == 200
    script = response.text
    for label in (
        "投研大厅",
        "专家中心",
        "研究报告",
        "用户画像",
        "研究能力",
    ):
        assert f'label: "{label}"' in script
    assert 'label: "任务中心"' not in script
    assert 'el("button", "pill", "🕘 历史记录")' in script
    for label in ("数据市场", "策略库", "监控看板", "知识库", "帮助中心"):
        assert f'label: "{label}"' not in script


def test_office_opens_the_glossary_as_a_full_page_route() -> None:
    script = client.get("/static/office/js/app.js").text
    controller = client.get("/static/office/js/glossary-ui.js").text
    styles = client.get("/static/office/css/office.css").text

    glossary_item = '{ route: "glossary", ico: "📚", label: "投研知识库" }'
    assert glossary_item in script
    assert script.index('label: "研究报告"') < script.index(glossary_item)
    assert script.index(glossary_item) < script.index('label: "用户画像"')
    assert 'case "glossary":' in script
    assert "buildOfficeGlossaryPage()" in script
    assert 'navigate("glossary")' in script
    assert "glossary-overlay" not in controller
    assert "glossary-panel" not in controller
    assert 'className = "glossary-page"' in controller
    assert ".glossary-page {" in styles
    assert ".glossary-library {" in styles


def test_office_does_not_render_unimplemented_actions() -> None:
    response = client.get("/static/office/js/app.js")

    assert response.status_code == 200
    script = response.text
    for label in (
        "设置面板规划中",
        "导出 PDF",
        "导出 PPT",
        "分享报告",
        "团队管理",
        "更多配置（模型、温度、Skill 授权）规划中",
        "查看完整对话记录",
    ):
        assert label not in script


def test_office_demo_skills_mirror_supported_skill_surface() -> None:
    app_response = client.get("/static/office/js/app.js")
    mock_response = client.get("/static/office/js/mock.js")

    assert app_response.status_code == 200
    assert mock_response.status_code == 200
    assert "function pageSkills()" in app_response.text
    assert "page.appendChild(live ? pageSkillsLive() : pageSkills())" in app_response.text
    for skill_id in (
        "factor_idea_generation",
        "r020_volume_expansion",
        "a_share_stock_dossier",
    ):
        assert skill_id in mock_response.text


def test_demo_and_live_reports_share_the_research_presentation_adapter() -> None:
    script = client.get("/static/office/js/app.js").text

    assert "const researchReport = buildDemoResearchReport(report);" in script
    assert "buildReportMainLive(researchReport)" in script
    assert "researchPresentation.buildResearchViewModel" in script
    assert "if (vm.failed)" in script
    assert "renderResearchFailure(vm)" in script
    assert "formatReportTimestamp(report.created_at)" in script



def test_office_wires_the_coach_layer_into_reports_and_war_room() -> None:
    script = client.get("/static/office/js/app.js").text
    coach_script = client.get("/static/office/js/coach.js").text
    api_script = client.get("/static/office/js/api.js").text
    live_script = client.get("/static/office/js/live.js").text
    mock_script = client.get("/static/office/js/mock.js").text
    styles = client.get("/static/office/css/office.css").text

    # report pages mount the coach sidebar with IDE-style selection quoting
    assert "buildCoachSidebar" in script
    assert "attachSelectionQuoting" in script
    assert "createClassroomPanel" in script
    assert 'from "./coach.js?v=' in script
    assert '"coach-chat-section"' in coach_script
    assert '"coach-compose"' in coach_script
    assert '"研究复盘"' in coach_script
    assert '"对话记录"' in coach_script
    assert '"提问区"' in coach_script
    # sidebar sections fold into tab-style bars so the panel never feels cramped
    assert "coach-fold-toggle" in coach_script
    assert 'makeFold("reading", "本节导读", contextSlot, { open: false })' in coach_script
    assert 'makeFold("guide", "研究复盘", guideSlot, { open: false })' in coach_script
    # transports: live hits the coach endpoints, demo replays labeled samples
    assert "coachAsk" in api_script
    assert "coachGuide" in api_script
    assert "coachNarrations" in api_script
    assert 'addEventListener("coach"' in live_script
    assert "DEMO_COACH" in mock_script
    # coach output is always labeled by origin and never silently degrades
    assert "模型生成" in coach_script
    assert "证据检索 · 未调模型" in coach_script
    assert ".coach-panel" in styles
    assert ".coach-guide-slot" in styles
    assert ".coach-chat-section" in styles
    assert ".coach-fold-toggle" in styles
    assert ".coach-guide-slot.folded { display: none; }" in styles
    # expanded sections share the panel height adaptively instead of fixed caps
    assert ".coach-guide-slot:not(.folded) { flex: 1 1 0; min-height: 130px; max-height: none; }" in styles
    assert ".coach-reading-slot:not(.folded) { flex: 1 1 0; min-height: 110px; max-height: none; }" in styles
    assert ".coach-compose" in styles
    assert ".classroom-panel" in styles


def test_report_page_uses_dynamic_sections_scrollspy_and_sticky_coach() -> None:
    script = client.get("/static/office/js/app.js").text
    coach_script = client.get("/static/office/js/coach.js").text
    styles = client.get("/static/office/css/office.css").text
    companion_styles = client.get("/static/office/css/companion.css").text
    presentation = client.get(
        "/static/presentation/build-research-view-model.js"
    ).text

    # Body and navigation are driven by the actual view-model chapters.
    assert "(vm.chapters || []).forEach" in script
    assert "vm.learningSummary.evidenceBoundary.length" in script
    assert "chapters," in presentation
    assert "navigation," in presentation
    assert "actualAgentIds" in presentation
    assert 'label: "宏观与政策"' not in script
    assert 'label: "量化验证"' not in script

    # Navigation, progress and Coach context stay synchronized while reading.
    assert "new IntersectionObserver" in script
    assert 'scrollIntoView({ behavior: "smooth"' in script
    assert "coach?.setContext?.(id)" in script
    assert "sectionContexts" in coach_script
    assert "setContext" in coach_script
    assert "一句话读懂" in coach_script
    assert "本节学习重点" in coach_script
    assert "相关追问建议" in coach_script

    # Desktop is approximately 68/32 with a sticky, viewport-height Coach.
    assert "minmax(0, 68fr) minmax(310px, 32fr)" in styles
    assert ".coach-side { position: sticky" in styles
    assert "height:calc(100vh - 136px)" in styles
    assert ".coach-scroll { flex: 1; overflow-y: auto" in styles
    assert ".coach-compose {" in styles

    # Small screens use a fixed bottom drawer, while chapter Coach cards remain.
    assert "@media (max-width: 900px)" in styles
    assert "position:fixed;" in styles
    assert ".section-coach-card" in companion_styles
    assert ".coach-reading-slot" in companion_styles


def test_live_war_room_uses_real_plan_flow_and_event_driven_office_motion() -> None:
    script = client.get("/static/office/js/app.js").text
    styles = client.get("/static/office/css/office.css").text
    companion_styles = client.get("/static/office/css/companion.css").text

    assert 'el("div", "dag-wrap dag-stack")' in script
    assert 'layers[d].forEach((s) =>' in script
    assert 's.dependsOn.length' in script
    assert 'status: "idle"' in script
    assert 'const stageController = createOfficeStageController(canvas, planAgents);' in script
    assert 'stageController.setAgentStatus(agent, "working")' in script
    assert 'stageController.setAgentStatus(agent, "done")' in script
    assert 'stageController.stop();' in script
    assert ".dag-stack" in styles
    assert ".dag-layer" in styles
    assert ".dag-stack .dag-node" in styles
    assert ".war-right-col > .companion-panel" in styles
    assert "flex: 0 0 44%;" in styles
    assert ".war-right-col > .classroom-panel" in styles
    assert "flex: 0 0 30%;" in styles
    assert "max-height: 230px" not in companion_styles


def test_office_versions_the_demo_data_module_import() -> None:
    response = client.get("/static/office/js/app.js")

    assert response.status_code == 200
    assert 'from "./mock.js?v=' in response.text
    assert 'from "./live.js?v=' in response.text
    assert 'from "./api.js?v=' in client.get("/static/office/js/live.js").text


def test_hall_refines_research_query_inline_without_new_chat_or_modal() -> None:
    script = client.get("/static/office/js/app.js").text
    api_script = client.get("/static/office/js/api.js").text
    live_script = client.get("/static/office/js/live.js").text
    styles = client.get("/static/office/css/office.css").text

    assert "正在整理研究问题…" in script
    assert "我理解你的研究需求是" in script
    assert "可直接修改" in script
    assert "确认并开始研究" in script
    assert "查看原问题" in script
    assert "重新整理" in script
    assert "rec.hidden = true" in script
    assert "query-refinement" in script
    assert "modal" not in script[script.index("function pageHallLive()"):script.index("function pageClarifyLive()")]
    assert "/api/research-query/rewrite" in api_script
    assert "rewriteResearchQuery" in live_script
    assert ".query-refinement" in styles
    assert ".query-option" in styles


def test_query_refinement_helpers_apply_clarification_and_final_priority() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the query refinement unit tests")

    completed = subprocess.run(
        [node, "tests/test_query_refinement.mjs"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "query refinement tests passed" in completed.stdout


def test_office_loads_shared_glossary_and_office_controller() -> None:
    entrypoint = client.get("/")
    controller = client.get("/static/office/js/glossary-ui.js")
    glossary = client.get("/static/glossary.js")

    assert entrypoint.status_code == 200
    assert '<script src="/static/glossary.js?v=' in entrypoint.text
    assert 'from "./glossary-ui.js?v=' in client.get("/static/office/js/app.js").text
    assert controller.status_code == 200
    assert "initOfficeGlossary" in controller.text
    assert "highlightGlossaryScope" in controller.text
    assert "alphaos.glossary.knowledge" in glossary.text


def test_office_glossary_is_functional_and_scoped_to_research_content() -> None:
    script = client.get("/static/office/js/app.js").text
    controller = client.get("/static/office/js/glossary-ui.js").text
    api_script = client.get("/static/office/js/api.js").text
    live_script = client.get("/static/office/js/live.js").text

    assert 'route: "glossary"' in script
    assert "buildOfficeGlossaryPage" in controller
    assert '"glossary-scope"' in script
    assert "highlightGlossaryScope" in script
    assert "extractReportGlossary" in script
    assert "registerGlossaryTerms" in script
    assert 'closest(".glossary-scope")' in controller
    assert "AlphaGlossary.addKnowledge" in controller
    assert "AlphaGlossary.removeKnowledge" in controller
    assert "registerGlossaryTerms" in controller
    assert "reportGlossary" in api_script
    assert "extractReportGlossary" in live_script


def test_glossary_matches_terms_inside_chinese_sentences() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the glossary unit tests")

    completed = subprocess.run(
        [node, "tests/test_glossary.cjs"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "glossary tests passed" in completed.stdout


def test_office_uses_accessible_compact_navigation_on_narrow_screens() -> None:
    script = client.get("/static/office/js/app.js").text
    styles = client.get("/static/office/css/office.css").text

    assert 'btn.setAttribute("aria-label", item.label)' in script
    assert "@media (max-width: 760px)" in styles
    assert ".sidebar { width: 64px;" in styles
    assert ".nav-item > span:last-child" in styles
    assert ".statusbar .sb-item:first-child { display: none; }" in styles
