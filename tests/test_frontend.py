import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_frontend_entrypoint_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "<title>AlphaOS · AI 投资研究操作系统</title>" in response.text
    assert '<link rel="icon" href="data:," />' in response.text
    assert 'href="/static/office/css/office.css?v=' in response.text
    assert 'src="/static/office/js/app.js?v=' in response.text
    assert "Research Console" not in response.text


def test_office_path_redirects_to_primary_root_entrypoint() -> None:
    response = client.get("/office", follow_redirects=False)

    assert response.status_code in (307, 308)
    assert response.headers["location"] == "/"


def test_frontend_assets_are_served() -> None:
    script = client.get("/static/app.js")
    styles = client.get("/static/styles.css")

    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "renderResponse" in script.text
    assert "用户无需填写任何 API Key" in script.text
    assert styles.status_code == 200
    assert "text/css" in styles.headers["content-type"]
    assert ".console-card" in styles.text
    assert "buildPlainLanguageResult" in script.text
    assert "BLOCK_RENDERERS" in script.text
    assert "renderContentBlocks" in script.text


def test_office_user_profile_module_is_served() -> None:
    client = TestClient(app)

    profile = client.get("/static/office/js/profile.js")
    office = client.get("/office")

    assert profile.status_code == 200
    assert "openProfileOnboarding" in profile.text
    assert "SQLite" in profile.text
    assert office.status_code == 200


def test_presentation_modules_are_served() -> None:
    status = client.get("/static/presentation/status-labels.js")
    events = client.get("/static/presentation/event-labels.js")
    adapter = client.get("/static/presentation/build-plain-language-result.js")
    research_adapter = client.get(
        "/static/presentation/build-research-view-model.js"
    )

    assert status.status_code == 200
    assert "computed_not_validated" in status.text
    assert events.status_code == 200
    assert "pandadata_market_data" in events.text
    assert adapter.status_code == 200
    assert "buildPlainLanguageResult" in adapter.text
    assert "source.aggregation" in adapter.text
    assert research_adapter.status_code == 200
    assert "buildResearchViewModel" in research_adapter.text
    assert "translateProgressEvent" in research_adapter.text


def test_frontend_presentation_adapter() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the zero-dependency frontend unit tests")

    completed = subprocess.run(
        [node, "tests/test_frontend_presentation.cjs"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "frontend presentation tests passed" in completed.stdout


def test_research_presentation_adapter() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the zero-dependency frontend unit tests")

    completed = subprocess.run(
        [node, "tests/test_research_presentation.cjs"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "research presentation tests passed" in completed.stdout


def test_research_terms_connect_to_knowledge_base() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the zero-dependency frontend unit tests")

    completed = subprocess.run(
        [node, "tests/test_glossary_knowledge.cjs"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "glossary knowledge tests passed" in completed.stdout


def test_office_capability_pages_do_not_render_runtime_internals() -> None:
    source = (REPO_ROOT / "frontend" / "office" / "js" / "app.js").read_text(
        encoding="utf-8"
    )

    assert '"Skills"' not in source
    assert "Skills · 实时" not in source
    assert "skill_registry" not in source
    assert "${esc(s.id)}" not in source
    assert "归属 ${esc(s.owner_agents" not in source
    assert "后端不可用" not in source
    assert "后端拒绝" not in source
    assert "配置 ARK 凭证" not in source
    assert "Skill 来源" not in source
