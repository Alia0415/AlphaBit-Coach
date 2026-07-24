from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_office_keeps_only_backend_supported_navigation() -> None:
    response = client.get("/static/office/js/app.js")

    assert response.status_code == 200
    script = response.text
    for label in ("投研大厅", "任务中心", "专家中心", "研究报告", "用户画像", "Skills"):
        assert f'label: "{label}"' in script
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


def test_office_versions_the_demo_data_module_import() -> None:
    response = client.get("/static/office/js/app.js")

    assert response.status_code == 200
    assert 'from "./mock.js?v=' in response.text
