from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app


REPO_ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_stock_workspace_assets_are_served_locally() -> None:
    office = client.get("/office")
    library = client.get("/static/stock-library.js")
    chart = client.get("/static/stock-chart.js")
    workspace = client.get("/static/stock-workspace.js")
    styles = client.get("/static/stock-workspace.css")
    vendor = client.get(
        "/static/vendor/lightweight-charts.standalone.production.js"
    )

    assert office.status_code == 200
    assert "/static/stock-workspace.css" in office.text
    assert "/static/vendor/lightweight-charts.standalone.production.js" in office.text
    for response in (library, chart, workspace, styles, vendor):
        assert response.status_code == 200
    assert "class StockLibrary" in library.text
    assert "class StockChart" in chart.text
    assert "AbortController" in workspace.text
    assert "setData(undefined)" not in chart.text


def test_office_defaults_to_stock_workspace_without_removing_research_routes() -> None:
    source = (
        REPO_ROOT / "frontend" / "office" / "js" / "app.js"
    ).read_text(encoding="utf-8")

    assert 'let currentRoute = "stocks";' in source
    assert 'case "stocks"' in source
    assert '{ route: "hall", ico: "🏛", label: "投研大厅" }' in source
    assert '{ route: "war", ico: "🛰", label: "多 Agent 作战室" }' in source
    assert "mountStockWorkspace" in source
    assert "navigate(\"hall\")" in source


def test_stock_frontend_state_helpers() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for stock frontend state tests")

    completed = subprocess.run(
        [node, "tests/test_stock_frontend.mjs"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "stock frontend state tests passed" in completed.stdout
