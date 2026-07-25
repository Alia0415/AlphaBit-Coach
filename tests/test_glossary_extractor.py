from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ark_client import ArkClientError


class MockArk:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def chat(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def _module():
    try:
        return importlib.import_module("backend.services.glossary_extractor")
    except ModuleNotFoundError:
        pytest.fail("glossary extractor module is missing")


def test_extractor_keeps_only_terms_that_appear_in_report() -> None:
    module = _module()
    response = json.dumps(
        {
            "terms": [
                {
                    "term": "归母净利润",
                    "explanation": "归属于上市公司普通股股东的净利润口径。",
                    "category": "财务报表",
                },
                {
                    "term": "净息差",
                    "explanation": "银行利息收入与利息支出的收益差额口径。",
                    "category": "银行指标",
                },
            ]
        },
        ensure_ascii=False,
    )
    extractor = module.GlossaryExtractor(client=MockArk(response))

    terms = extractor.extract("报告显示归母净利润同比增长 12%。")

    assert [item.term for item in terms] == ["归母净利润"]


def test_extractor_repairs_invalid_model_output_once() -> None:
    module = _module()
    repaired = json.dumps(
        {
            "terms": [
                {
                    "term": "净息差",
                    "explanation": "净息差衡量银行生息资产的净利息收益能力。",
                    "category": "银行指标",
                }
            ]
        },
        ensure_ascii=False,
    )
    ark = MockArk("not-json", repaired)
    extractor = module.GlossaryExtractor(client=ark)

    terms = extractor.extract("该银行净息差较上期改善。")

    assert [item.term for item in terms] == ["净息差"]
    assert len(ark.prompts) == 2


def test_extractor_does_not_retry_unavailable_model() -> None:
    module = _module()

    class OfflineArk:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, prompt: str) -> str:
            self.calls += 1
            raise ArkClientError("offline")

    ark = OfflineArk()
    extractor = module.GlossaryExtractor(client=ark)

    with pytest.raises(module.GlossaryExtractionError):
        extractor.extract("报告中的净息差有所改善。")

    assert ark.calls == 1


def test_dynamic_term_rejects_markup_and_attribute_characters() -> None:
    module = _module()

    with pytest.raises(ValueError):
        module.GlossaryTerm(
            term='净息差" onclick="alert(1)',
            explanation="该内容不应成为可以注册到前端的动态术语。",
            category="银行指标",
        )


def test_report_glossary_endpoint_uses_persisted_report_text(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store,
) -> None:
    module = _module()

    class StubExtractor:
        def extract(self, text: str):
            assert "归母净利润同比增长" in text
            return [
                module.GlossaryTerm(
                    term="归母净利润",
                    explanation="归属于上市公司普通股股东的净利润口径。",
                    category="财务报表",
                )
            ]

    isolated_store.create_task(
        task_id="task-glossary",
        prompt="分析公司盈利",
        status="completed",
    )
    isolated_store.create_report(
        report_id="report-glossary",
        task_id="task-glossary",
        title="盈利分析",
        completeness={"completion_ratio": 1.0},
        aggregation={
            "direct_answer": {
                "headline": "盈利改善",
                "explanation": "归母净利润同比增长 12%。",
            },
            "content_blocks": [],
        },
    )
    main_module = importlib.import_module("backend.main")
    monkeypatch.setattr(main_module, "glossary_extractor", StubExtractor())

    response = TestClient(app).post("/api/reports/report-glossary/glossary")

    assert response.status_code == 200
    assert response.json()["terms"][0]["term"] == "归母净利润"
