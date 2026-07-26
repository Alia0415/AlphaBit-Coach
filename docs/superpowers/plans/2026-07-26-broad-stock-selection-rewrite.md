# Broad Stock-Selection Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reliably convert direct stock-selection questions into a confirmed, research-only A-share screening question before Manager planning.

**Architecture:** Add a deterministic post-processing guard to `ResearchQueryRefiner`. It examines only the normalized original query and overrides recommendation-style model drafts with one fixed research-only query; all other rewrites retain current behavior.

**Tech Stack:** Python 3.13, Pydantic, pytest

---

### Task 1: Deterministic Research Rewrite

**Files:**
- Modify: `backend/services/research_query_refiner.py`
- Modify: `tests/test_research_query_refinement.py`

- [x] **Step 1: Write the failing test**

Add a test whose mock model returns `"当前市场环境下，哪些股票具有投资价值？"` for
`"我应该买什么股票"`. Assert that `ResearchQueryRefiner.refine` instead returns
`"综合研究当前 A 股市场值得关注的行业方向、市场筛选框架、宏观与行业证据及关键不确定性，不提供具体买卖建议。"`
and sets `requires_confirmation=True`.

- [x] **Step 2: Run test to verify it fails**

Run:
`python -m pytest -q tests/test_research_query_refinement.py::test_stock_selection_request_is_deterministically_rewritten_for_research`

Expected: FAIL because the current service returns the model draft.

- [x] **Step 3: Write minimal implementation**

Add a bounded phrase matcher for explicit stock-selection language and a fixed
research-only rewrite. Apply it after the model response and before constructing
`ResearchQueryRefinement`. Force confirmation for matches; preserve existing
behavior for every non-match. Verify the fixed query is interpreted as
comprehensive `market_research` without a missing company identifier.

- [x] **Step 4: Run focused and related tests**

Run:
`python -m pytest -q tests/test_research_query_refinement.py tests/test_governed_workflow.py tests/test_planning_kernel.py`

Expected: all tests pass.

- [x] **Step 5: Verify the live planning path**

Call the running rewrite endpoint with `"我应该买什么股票"`, submit its returned
query to `/api/research/runs`, and poll until `plan_ready` or `failed`.

Expected: deterministic research-only rewrite and `plan_ready`.
