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


def test_office_separates_stock_library_and_chart_without_removing_research_routes() -> None:
    source = (
        REPO_ROOT / "frontend" / "office" / "js" / "app.js"
    ).read_text(encoding="utf-8")
    workspace = (
        REPO_ROOT / "frontend" / "stock-workspace.js"
    ).read_text(encoding="utf-8")
    styles = (
        REPO_ROOT / "frontend" / "stock-workspace.css"
    ).read_text(encoding="utf-8")

    assert 'let currentRoute = "stock-library";' in source
    assert 'case "stock-library"' in source
    assert 'case "stocks"' in source
    assert '{ route: "stock-library", ico: "▦", label: "股票库" }' in source
    assert '{ route: "stocks", ico: "📈", label: "股票行情" }' in source
    assert '{ route: "hall", ico: "🏛", label: "投研大厅" }' in source
    assert '{ route: "war", ico: "🛰", label: "多 Agent 作战室" }' in source
    assert "mountStockLibraryPage" in source
    assert "mountStockChartPage" in source
    assert "onOpenChart: (stock) => navigate(\"stocks\", stock)" in source
    assert source.index('label: "研究报告"') < source.index('label: "股票库"')
    assert source.index('label: "股票行情"') < source.index('label: "投研知识库"')
    assert "stock-research-button" not in workspace
    assert '{ value: "1m"' not in workspace
    assert ".stock-market-workspace" in styles
    assert ".stock-chart-state[hidden]" in styles
    assert "groupStocksByBoard" in (
        REPO_ROOT / "frontend" / "stock-library.js"
    ).read_text(encoding="utf-8")
    assert "PandaData" not in workspace
    assert "演示数据" not in workspace
    assert "/api/stocks/search" not in workspace


def test_office_sidebar_can_be_collapsed_and_persists_the_choice() -> None:
    source = (
        REPO_ROOT / "frontend" / "office" / "js" / "app.js"
    ).read_text(encoding="utf-8")
    styles = (
        REPO_ROOT / "frontend" / "office" / "css" / "office.css"
    ).read_text(encoding="utf-8")

    assert 'SIDEBAR_COLLAPSED_KEY = "alphabit-coach.sidebar-collapsed"' in source
    assert 'className = `sidebar${sidebarCollapsed ? " collapsed" : ""}`' in source
    assert 'sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"' in source
    assert ".sidebar.collapsed {" in styles
    assert ".sidebar.collapsed .nav-label" in styles


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
