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
    assert "layout.appendChild(buildReportMainLive(researchReport));" in script
    assert "researchPresentation.buildResearchViewModel" in script


def test_office_versions_the_demo_data_module_import() -> None:
    response = client.get("/static/office/js/app.js")

    assert response.status_code == 200
    assert 'from "./mock.js?v=' in response.text
    assert 'from "./live.js?v=' in response.text
    assert 'from "./api.js?v=' in client.get("/static/office/js/live.js").text


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

    assert 'id = "glossaryToggle"' in script
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
