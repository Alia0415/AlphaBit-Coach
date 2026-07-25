# Quant Thesis Validation MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded Quant thesis-validation path that connects existing Research and Macro conclusions to deterministic historical market evidence and surfaces that calibration in the final report.

**Architecture:** Manager selects `thesis_validation` only when Quant has upstream Research or Macro dependencies. Quant uses Ark only to select existing bounded claim IDs and directions, reuses PandaData plus `run_cross_check` for numbers, and emits deterministic alignment evidence. ResultAggregator maps that evidence into an existing `finding_cards` block, so no frontend or shared-result schema change is required.

**Tech Stack:** Python 3.13, Pydantic 2, pytest, Volcano Ark structured JSON, PandaData, existing AlphaOS task/result contracts.

---

### Task 1: Planning Contract

**Files:**
- Modify: `backend/agents/manager_agent.py`
- Modify: `backend/core/plan_validator.py`
- Test: `tests/test_planning_kernel.py`

- [ ] **Step 1: Write failing planning tests**

Add tests proving that a Quant step covering `quantitative_cross_check` accepts
`analysis_mode="thesis_validation"` only when it declares at least one
dependency, while standalone `historical_cross_check` remains valid.

```python
def test_quant_thesis_validation_requires_upstream_dependency() -> None:
    step = _quant_step(mode="thesis_validation", depends_on=[])
    with pytest.raises(PlanValidationError, match="dependency"):
        validate_execution_plan(_single_step_plan(step), AgentRegistry())
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest -q tests/test_planning_kernel.py -k "thesis_validation"
```

Expected: failure because `thesis_validation` is not accepted by the current
cross-check contract.

- [ ] **Step 3: Implement the minimal planning contract**

Allow the two analysis modes and require an upstream edge only for thesis
validation:

```python
if mode not in {"historical_cross_check", "thesis_validation"}:
    raise PlanValidationError(...)
if mode == "thesis_validation" and not step.all_dependency_step_ids():
    raise PlanValidationError(...)
```

Extend the Manager prompt so multidimensional claim calibration uses
`thesis_validation`, while standalone historical analysis remains
`historical_cross_check`. Manager still selects only agents and dependencies,
never Skills.

- [ ] **Step 4: Run the focused planning tests**

Run the command from Step 2. Expected: all selected tests pass.

### Task 2: Quant Thesis Calibration

**Files:**
- Modify: `backend/agents/quant_agent.py`
- Modify: `backend/agents/quant_cross_check.py`
- Test: `tests/test_quant_runtime.py`

- [ ] **Step 1: Write failing Quant tests**

Cover:

```python
def test_quant_thesis_validation_uses_dependency_claims_and_market_metrics():
    result = agent.execute(_thesis_task(research_dependency))
    assert result.status == "completed"
    assert result.metadata["execution_path"] == "thesis_validation"
    assert result.evidence[0]["type"] == "quant_thesis_validation"
    assert result.evidence[0]["claim_source_step"] == "research_1"

def test_quant_thesis_validation_rejects_unknown_claim_id():
    result = agent.execute(_thesis_task(research_dependency))
    assert result.status == "completed"
    assert result.evidence[0]["assessment"] == "inconclusive"
```

Also prove that Ark failure falls back to bounded dependency summaries, market
data is fetched once, factor/R020 routing is unchanged, and no signal/backtest
claims appear.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest -q tests/test_quant_runtime.py -k "thesis_validation"
```

Expected: failure because Quant currently recognizes only
`historical_cross_check`.

- [ ] **Step 3: Add bounded claim selection**

Define local Pydantic models for at most three selections:

```python
class ThesisClaimSelection(BaseModel):
    claim_id: str
    direction: Literal["positive", "negative", "risk", "neutral"]

class ThesisSelectionPlan(BaseModel):
    claims: list[ThesisClaimSelection] = Field(max_length=3)
```

Build candidates only from completed dependency summaries and risks. Validate
selected IDs against the candidate map. On Ark failure or invalid membership,
select up to three summaries with neutral direction.

- [ ] **Step 4: Add deterministic assessment**

Extend `assess_consistency` to accept an explicit allowlisted direction and
classify the signs of `period_return`, `return_20d`, `return_60d`, and
`return_120d` as aligned, divergent, mixed, or inconclusive. Keep volatility,
drawdown, and volume as context only.

- [ ] **Step 5: Reuse the existing market-data path**

Extract the shared PandaData fetch and row conversion used by
`historical_cross_check`, call it once, run `run_cross_check`, and create
`quant_thesis_validation` evidence with original claim text, metric snapshots,
reason, limitations, and falsification conditions.

- [ ] **Step 6: Run focused Quant tests**

Run the command from Step 2. Expected: all selected tests pass.

### Task 3: Report Injection And End-To-End Verification

**Files:**
- Modify: `backend/core/result_aggregator.py`
- Test: `tests/test_result_aggregator.py` or the existing aggregation test module
- Test: `tests/test_e2e_multidimensional.py`

- [ ] **Step 1: Write failing aggregation test**

```python
def test_aggregator_adds_quant_decision_calibration_block():
    result = aggregator.aggregate(spec, plan, validated_evidence)
    block = next(
        item for item in result.content_blocks
        if item.title == "量化决策校验"
    )
    assert block.type == "finding_cards"
    assert block.source_steps == ["quant_1"]
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest -q tests -k "quant_decision_calibration"
```

Expected: failure because Aggregator currently treats the evidence only as
generic metrics or summaries.

- [ ] **Step 3: Add evidence-profile mapping**

Add `quant_validations` to `EvidenceProfile`, recognize
`type="quant_thesis_validation"` in `_inspect_evidence_item`, and prepend one
existing `finding_cards` block:

```python
_block(
    "quant-thesis-validation",
    "finding_cards",
    "量化决策校验",
    _source_steps(profile.quant_validations),
    {"items": profile.quant_validations},
    "primary",
)
```

- [ ] **Step 4: Run focused GREEN and full verification**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest -q tests/test_planning_kernel.py tests/test_quant_runtime.py tests/test_e2e_multidimensional.py
python -m pytest -q
python -m ruff check backend/agents/manager_agent.py backend/agents/quant_agent.py backend/agents/quant_cross_check.py backend/core/plan_validator.py backend/core/result_aggregator.py
```

Expected: zero failures and zero Ruff errors.

- [ ] **Step 5: Run one real flow**

Use the real Manager, Research/Macro dependencies as selected by its DAG,
PandaData, Quant, and ResultAggregator. Record Manager time, Quant time, chosen
mode, validation count, assessment labels, and aggregate block title without
printing credentials or raw market rows.

- [ ] **Step 6: Commit and push only MVP changes**

Commit the plan, implementation, and tests without staging unrelated concurrent
worktree changes:

```powershell
git commit --only <MVP paths> -m "feat: add quant thesis validation"
git push origin main
```
