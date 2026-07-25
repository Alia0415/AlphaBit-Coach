# Quant Thesis Validation MVP

## Goal

Make Quant act as a decision-calibration layer in multidimensional research.
It should connect qualitative upstream findings to historical market evidence,
then give the final report a quantitative lens without claiming that price
behavior proves fundamentals or predicts returns.

## Scope

The MVP adds one Quant execution mode:

- `historical_cross_check`: unchanged standalone price, return, volatility,
  drawdown, volume, and window-sensitivity analysis.
- `thesis_validation`: consume completed Research and Macro dependency results,
  run the same deterministic market calculations, and return bounded
  alignment assessments for selected upstream claims.

Explicit factor ideation and R020 requests remain on the existing dynamic
Runtime Skill Planner. The MVP adds no API, Skill, dependency, database, or
frontend component.

## Considered Approaches

### Deterministic metrics only

Attach the same metrics to every upstream summary. This is fastest and most
stable, but cannot relate the evidence to a particular claim and would remain
an appendix rather than a coaching layer.

### Fully model-generated validation

Ask Ark to read all upstream results and write the assessment. This produces
natural language quickly, but lets the model alter calculations, invent
relationships, and overstate what historical prices establish.

### Bounded hybrid approach

Use Ark only to select at most three existing upstream claim IDs and classify
their direction from an allowlist. Validate that selection locally. Use
PandaData and `quant_cross_check` for all numbers, then apply deterministic
alignment rules. This is the selected approach because it preserves useful
semantic context while keeping calculations and verdict boundaries
reproducible.

## Architecture And Data Flow

Manager remains the sole DAG planner.

1. For standalone historical analysis, Manager emits
   `analysis_mode=historical_cross_check` and Quant may run in parallel.
2. When the user requests multidimensional research and Quant is meant to
   calibrate Research or Macro conclusions, Manager emits
   `analysis_mode=thesis_validation` with at least one typed dependency on an
   upstream Research or Macro step.
3. `WorkflowExecutor` passes complete dependency results through its existing
   `ExpertTask.dependency_results` contract.
4. Quant builds bounded candidate claims from completed dependency summaries
   and risks. Candidate text is assigned a stable local ID.
5. Ark may select at most three candidate IDs and classify each as positive,
   negative, risk, or neutral. Quant rejects unknown IDs and repairs model JSON
   at most once through the existing structured client.
6. Quant fetches the existing PandaData OHLCV fields once and reuses
   `run_cross_check`.
7. Deterministic code classifies historical market evidence as aligned,
   divergent, mixed, or inconclusive. It records the exact metrics and windows
   used. Fundamental truth is never inferred from market behavior.
8. ResultAggregator recognizes `quant_thesis_validation` evidence and emits a
   `finding_cards` block titled `量化决策校验`. Existing frontend rendering is
   reused.

## Output Contract

Each validation evidence item contains:

- `type=quant_thesis_validation`
- `claim_id`, `claim_source_step`, and the original bounded `claim_text`
- `claim_direction`
- `assessment`: `aligned`, `divergent`, `mixed`, or `inconclusive`
- `assessment_scope=historical_market_alignment`
- `metric_ids` and a compact metric snapshot
- `reason`
- `falsification_conditions`
- `limitations`
- `validation_status=historical_computation`

The user-facing `text` field states what the historical data adds to the
upstream claim. It must not contain buy, sell, hold, target-return, position,
IC, backtest, or signal language.

## Deterministic Assessment

The calculation uses period return plus available 20, 60, and 120-day returns:

- consistent signs matching a positive or negative claim are `aligned`;
- consistent opposite signs are `divergent`;
- conflicting window signs are `mixed`;
- neutral claims, insufficient observations, or claims that historical market
  behavior cannot test are `inconclusive`.

Volatility, downside volatility, maximum drawdown, and volume expansion provide
risk and sensitivity context but do not independently prove a qualitative
claim. Threshold-free descriptions are preferred in the MVP.

## Failure And Fallback Behavior

- Missing symbols or dates returns the existing structured clarification.
- Missing or failed dependencies makes `thesis_validation` fail validation
  before execution.
- If no bounded upstream claims exist, Quant returns a clear inconclusive
  result rather than inventing a thesis.
- If Ark claim selection fails, Quant deterministically selects up to three
  dependency summaries with neutral direction; calculations still complete
  and assessments remain inconclusive.
- PandaData failure remains a sanitized Quant failure.
- Partial upstream evidence is explicitly included in limitations.

## Changes

Primary implementation files:

- `backend/agents/manager_agent.py`
- `backend/core/plan_validator.py`
- `backend/agents/quant_agent.py`
- `backend/agents/quant_cross_check.py`
- `backend/core/result_aggregator.py`

Tests extend existing planning, Quant runtime, aggregation, and
multidimensional end-to-end suites. Research, Macro, WorkflowExecutor,
PandaDataClient, Runtime Skills, and frontend code remain unchanged.

## Success Criteria

- A comprehensive stock-research plan can create a dependent
  `thesis_validation` Quant step.
- A standalone price request still uses `historical_cross_check`.
- Quant selects only claim IDs present in dependency results.
- All displayed values come from the existing deterministic calculation
  engine.
- The aggregate result contains a `量化决策校验` finding block tied to the
  Quant source step.
- Ark or PandaData failures follow the bounded fallback behavior.
- Existing factor and R020 Skill planning behavior is unchanged.
- Automated tests mock Ark and PandaData; one explicit manual integration flow
  verifies real services.

## Non-Goals

The MVP does not add financial-factor validation, peer discovery, benchmark
index retrieval, IC, backtesting, portfolio construction, account access,
trading signals, or personalized security recommendations.
