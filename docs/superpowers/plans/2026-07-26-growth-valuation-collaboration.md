# Growth and Valuation Collaboration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure single-company requests that jointly ask about growth and valuation cannot execute as a Research-only plan.

**Architecture:** Correct model underclassification at the TaskInterpreter boundary by replacing a single-dimension result with four focused required dimensions. Keep Manager as the sole planner and rely on existing Registry authorization plus dimension validation to require Research, Quant, and Risk coverage; add prompt guidance so the first model plan assigns credible, non-duplicative work.

**Tech Stack:** Python 3, Pydantic, pytest, Ruff

---

### Task 1: Reproduce model underclassification

**Files:**
- Create: `tests/test_growth_valuation_collaboration.py`

- [x] **Step 1: Write the failing interpreter test**

```python
PROMPT = "评估宁德时代（300750.SZ）的成长性与估值水平"


class _SingleDimensionArk:
    def chat_json(self, request):
        return request.response_model.model_validate(
            {
                "request_scope": "focused",
                "required_dimensions": ["company_fundamentals"],
                "optional_dimensions": [],
                "reasoning": "公司基本面问题",
            }
        )


def test_growth_valuation_dimensions_survive_model_underclassification():
    spec = TaskInterpreter(ark_client=_SingleDimensionArk()).interpret(
        PROMPT,
        _allowed_policy(),
    )
    assert spec.request_scope == "focused"
    assert spec.required_dimensions == [
        "company_fundamentals",
        "industry_competition",
        "quantitative_cross_check",
        "risk_assessment",
    ]
```

- [x] **Step 2: Run the focused test and verify RED**

Run: `pytest tests/test_growth_valuation_collaboration.py::test_growth_valuation_dimensions_survive_model_underclassification -q`

Expected: FAIL because the current interpreter returns only `company_fundamentals`.

### Task 2: Correct compound growth-and-valuation interpretation

**Files:**
- Modify: `backend/core/task_interpreter.py`
- Test: `tests/test_growth_valuation_collaboration.py`

- [x] **Step 1: Add narrow marker groups and semantic predicate**

```python
_GROWTH_REVIEW = ("成长性", "成长能力", "增长能力", "业绩增长")
_VALUATION_REVIEW = ("估值", "估值水平", "贵不贵")


def _requires_growth_valuation_review(task_type, subject_type, lowered):
    return (
        subject_type == "company"
        and task_type == "company_research"
        and any(marker in lowered for marker in _GROWTH_REVIEW)
        and any(marker in lowered for marker in _VALUATION_REVIEW)
    )
```

- [x] **Step 2: Apply the correction after model or fallback extraction**

```python
if _requires_growth_valuation_review(task_type, subject_type, lowered):
    request_scope = "focused"
    required_dimensions = [
        "company_fundamentals",
        "industry_competition",
        "quantitative_cross_check",
        "risk_assessment",
    ]
    optional_dimensions = [
        dimension
        for dimension in optional_dimensions
        if dimension not in required_dimensions
    ]
```

- [x] **Step 3: Update deterministic classification and prompt guidance**

Add the same compound rule to `_DIMENSION_PROMPT_TEMPLATE` and return the four focused dimensions from `_deterministic_dimensions`.

- [x] **Step 4: Add non-trigger regression cases**

```python
@pytest.mark.parametrize(
    "prompt",
    [
        "评估宁德时代（300750.SZ）的成长性",
        "评估宁德时代（300750.SZ）的估值水平",
    ],
)
def test_single_growth_or_valuation_goal_does_not_force_compound_dimensions(prompt):
    spec = TaskInterpreter(ark_client=_SingleDimensionArk()).interpret(
        prompt,
        _allowed_policy(),
    )
    assert spec.required_dimensions == ["company_fundamentals"]
```

- [x] **Step 5: Run interpreter tests and verify GREEN**

Run: `pytest tests/test_growth_valuation_collaboration.py -q`

Expected: all interpreter tests PASS.

### Task 3: Enforce credible multi-agent planning

**Files:**
- Modify: `backend/agents/manager_agent.py`
- Test: `tests/test_growth_valuation_collaboration.py`

- [x] **Step 1: Add a validator regression test for Research-only plans**

Create a focused TaskSpec from `PROMPT`, build a one-step Research plan covering only `company_fundamentals`, and assert:

```python
with pytest.raises(PlanValidationError, match="does not cover required dimensions"):
    validate_plan_dimensions(plan, spec, AgentRegistry())
```

- [x] **Step 2: Add Manager prompt assertions**

```python
assert "成长性与估值" in prompt
assert "市场行为交叉验证不能替代估值指标" in prompt
assert "不得把价格表现表述为估值高低" in prompt
```

- [x] **Step 3: Add planning guidance**

Document that compound growth-and-valuation tasks require company and industry Research, Quant market cross-check, and Risk review. State that Quant does not calculate unsupported valuation and missing PE/PB/EV or percentile evidence must be exposed.

- [x] **Step 4: Verify focused behavior**

Run: `pytest tests/test_growth_valuation_collaboration.py tests/test_financial_quality_collaboration.py tests/test_planning_kernel.py -q`

Expected: all selected tests PASS.

### Task 4: Full verification and delivery

**Files:**
- Modify: `docs/superpowers/plans/2026-07-26-growth-valuation-collaboration.md` only to mark completed checkboxes

- [x] **Step 1: Run formatting and lint checks**

Run: `ruff check backend tests`

Expected: exit 0.

Result: the changed Python files pass Ruff. The full repository scan remains
blocked by nine unrelated pre-existing unused imports in
`backend/core/store.py` and `tests/test_multidimensional_research.py`.

- [x] **Step 2: Run the full automated suite**

Run: `pytest -q`

Expected: exit 0 with no failures.

- [x] **Step 3: Inspect repository state**

Run: `git diff --check && git status --short`

Expected: only the implementation, its tests, and plan are new task changes; pre-existing frontend edits remain unstaged.

- [ ] **Step 4: Commit only task files**

```bash
git add backend/core/task_interpreter.py backend/agents/manager_agent.py \
  tests/test_growth_valuation_collaboration.py \
  docs/superpowers/plans/2026-07-26-growth-valuation-collaboration.md
git commit -m "fix: require collaboration for growth valuation research"
```

- [ ] **Step 5: Push main**

Run: `git push origin main`

Expected: the new commit is accepted by `origin/main`.
