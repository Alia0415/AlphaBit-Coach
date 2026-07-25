# Quant Real-Scenario Thesis Validation Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse Research financial and peer evidence so Quant thesis validation can add deterministic fundamental consistency and peer-relative performance to real company reports.

**Architecture:** Add focused extraction and assessment helpers beside the existing Quant cross-check engine. The Quant Agent consumes only completed dependency evidence, expands the existing single PandaData request with a bounded peer pool, and emits the existing `quant_thesis_validation` contract with new assessment scopes.

**Tech Stack:** Python 3.12, Pydantic contracts, pytest, Ruff, existing PandaData client and ResultAggregator.

---

### Task 1: Fundamental Evidence Extraction And Assessment

**Files:**
- Modify: `tests/test_quant_runtime.py`
- Modify: `backend/agents/quant_cross_check.py`
- Modify: `backend/agents/quant_agent.py`

- [x] **Step 1: Write failing tests for financial evidence**

Add tests that build a completed Research dependency containing dossier
`derived_metrics`. Assert that positive revenue growth produces a
`fundamental_metric_alignment` item and that a single margin observation is not
classified.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
pytest tests/test_quant_runtime.py -k "fundamental_metric_alignment or single_margin" -q
```

Expected: failures because Quant does not extract or assess dossier metrics.

- [x] **Step 3: Implement bounded deterministic helpers**

Add allowlisted metric extraction from `skill_result.data`, chronological
normalization, and an assessment function with these exact rules:

```python
growth_metrics = {
    "revenue_yoy",
    "operating_profit_yoy",
    "net_profit_yoy",
    "net_profit_excluding_nonrecurring_yoy",
}
trend_metrics = {
    "gross_margin",
    "operating_margin",
    "net_margin",
    "operating_cash_flow_to_net_profit",
    "asset_liability_ratio",
    "current_ratio",
    "accounts_receivable_to_revenue",
    "inventory_to_revenue",
    "total_asset_turnover",
}
```

Growth metrics use their latest sign. Trend metrics require two ordered periods.
Single levels, non-finite numbers, and neutral claims remain unclassified.

- [x] **Step 4: Emit fundamental validation evidence**

For each selected Research claim, emit at most three relevant observations with
`assessment_scope="fundamental_metric_alignment"`, metric snapshot, reason,
limitations, and falsification conditions. Preserve all existing market
validation evidence.

- [x] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
pytest tests/test_quant_runtime.py -k "thesis_validation or fundamental_metric_alignment or single_margin" -q
```

Expected: all selected tests pass.

### Task 2: Evidence-Backed Peer Relative Performance

**Files:**
- Modify: `tests/test_quant_runtime.py`
- Modify: `backend/agents/quant_agent.py`
- Modify: `backend/agents/quant_cross_check.py`

- [x] **Step 1: Write failing peer tests**

Add tests asserting that Quant extracts unique peers from
`competitor_candidates`, excludes the target, bounds the candidate scan at
twelve, retains at most five valid peers, fetches target and candidates in one
PandaData call, and reports target return, peer median, percentile, and sample
size.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```powershell
pytest tests/test_quant_runtime.py -k "peer_relative or bounded_peer" -q
```

Expected: failures because thesis validation currently fetches only Manager
symbols and only emits absolute market alignment.

- [x] **Step 3: Implement peer extraction and shared fetch**

Read peer symbols only from completed Research evidence of type
`competitor_candidates`, normalize them through the existing symbol rules,
exclude targets, deduplicate in source order, and scan at most twelve. Extend
only the thesis-validation market task symbols so the existing controlled
PandaData call fetches target and candidates together, then retain at most five
peers with valid observations.

- [x] **Step 4: Implement relative assessment**

Compute same-window period returns for the target and valid peers. Require at
least two peers. Emit one `peer_relative_performance` item per selected claim
and target containing:

```python
{
    "target_return": float,
    "peer_median_return": float,
    "percentile": float,
    "peer_sample_size": int,
}
```

Map positive or negative claim direction to `aligned` or `divergent` only from
the target-minus-peer-median sign. Neutral and risk claims remain inconclusive.

- [x] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
pytest tests/test_quant_runtime.py -k "thesis_validation or peer_relative or bounded_peer" -q
```

Expected: all selected tests pass.

### Task 3: Regression, Real Flow, And Delivery

**Files:**
- Modify only if needed: `backend/core/result_aggregator.py`
- Modify only if needed: `tests/test_result_aggregator.py`
- Create: `scripts/manual_test_quant_real_scenario.py`

- [x] **Step 1: Verify aggregator compatibility**

Run:

```powershell
pytest tests/test_result_aggregator.py -q
```

The existing `量化决策校验` block must include the new items without a frontend
contract change. Add a focused aggregator test only if the existing generic
collection behavior does not preserve the new fields.

- [x] **Step 2: Add a manual real-flow script**

Create a script that executes a real Research to Quant workflow for one A-share
company using environment credentials, then prints bounded JSON containing
timings, statuses, assessment scopes, assessments, peer sample size, and output
block titles. It must not print credentials or raw responses.

- [x] **Step 3: Run fresh automated verification**

Run:

```powershell
pytest -q
ruff check backend/agents/quant_agent.py backend/agents/quant_cross_check.py tests/test_quant_runtime.py scripts/manual_test_quant_real_scenario.py
git diff --check
```

Expected: zero test failures, zero Ruff errors, and no whitespace errors.

- [x] **Step 4: Run the real workflow**

Run:

```powershell
python scripts/manual_test_quant_real_scenario.py
```

Expected with credentials: Research and Quant complete, the output contains
`量化决策校验`, and at least one of `fundamental_metric_alignment` or
`peer_relative_performance` is present when upstream data is available.
Observed locally without credentials: script returned a bounded
`{"status": "skipped"}` response and did not call PandaData.

- [x] **Step 5: Commit and push**

Stage only the plan, Quant implementation, focused tests, and manual script.
Do not stage unrelated untracked diagnostic files.

```powershell
git add docs/superpowers/plans/2026-07-25-quant-real-scenario-enhancement.md backend/agents/quant_agent.py backend/agents/quant_cross_check.py tests/test_quant_runtime.py scripts/manual_test_quant_real_scenario.py
git commit -m "feat: apply quant validation to real research evidence"
git push origin main
```
