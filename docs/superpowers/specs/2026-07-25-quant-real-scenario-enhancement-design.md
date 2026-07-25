# Quant Real-Scenario Thesis Validation Enhancement

## Goal

Make thesis validation useful in real single-company research without expanding
AlphaOS architecture. Quant should reuse evidence already produced by Research
to answer two bounded questions:

1. Do reported financial metrics move in the same direction as the selected
   upstream thesis?
2. Did the target stock outperform or underperform a small, evidence-backed
   peer group over the same historical window?

The output remains decision support. It is not a backtest, forecast, trading
signal, or proof of causality.

## Considered Approaches

### Recommended: consume existing Research evidence

Read allowlisted dossier metrics and peer symbols from completed dependency
results. Reuse the existing PandaData market call and deterministic cross-check
engine. This has the smallest latency, quota, and architecture impact.

### Alternative: add financial and industry calls to Quant

Quant could independently query PandaData for financial statements and industry
membership. This duplicates Research, increases quota and latency, and weakens
agent ownership, so it is rejected for the MVP.

### Alternative: add new Runtime Skills

Dedicated fundamental-validation and relative-performance Skills could provide
more extensibility. The current computations are small and deterministic, so
new runtime installation and governance work is not justified yet.

## Data Flow

1. Manager continues to create the dynamic Research to Quant dependency.
2. Research produces its existing dossier and industry evidence.
3. Quant selects at most three existing bounded thesis claims.
4. Quant extracts:
   - allowlisted `derived_metrics` from Research `skill_result.data`;
   - at most five unique peer symbols from `competitor_candidates`, excluding
     the target.
5. Quant requests target and peer OHLCV rows in one existing PandaData call.
6. Deterministic code produces:
   - `fundamental_metric_alignment` evidence from relevant metric direction or
     chronological trend;
   - `peer_relative_performance` evidence from same-window period returns.
7. ResultAggregator continues to render these items in the existing
   `量化决策校验` block.

## Fundamental Rules

Only dossier metrics already accepted by the product are eligible.

- Growth metrics such as revenue and profit YoY use their reported sign.
- Margin and operating-quality metrics require at least two chronological
  observations; the direction is the latest change versus the previous value.
- Leverage, receivables, and inventory ratios are not classified from a single
  level. They require a trend and are presented as risk context.
- A metric is used only when it is directionally relevant to the selected
  positive, negative, or risk claim.
- Neutral claims remain inconclusive.
- Missing, non-finite, or insufficient observations are skipped.

The evidence includes metric IDs, periods, values, reason, limitations, and
falsification conditions. It never claims that a financial metric proves the
thesis.

## Peer Rules

- Peers must come from completed Research dependency evidence.
- Use at most five unique valid symbols and exclude the target.
- Fetch target and peers together with the existing controlled market API.
- Compare period returns only when target and at least two peers have valid
  observations.
- Report target return, peer median, percentile rank, and peer sample size.
- `aligned` or `divergent` reflects only the selected claim direction versus
  relative historical performance. Mixed or insufficient samples remain
  `inconclusive`.

## Failure Handling

- Missing financial evidence does not fail the Quant step; that scope is
  omitted.
- Missing or failed peer rows do not fail target market validation.
- A failed shared PandaData request preserves the existing Quant failure
  behavior.
- Unknown evidence shapes, invalid symbols, and non-finite numbers are ignored.
- Ark continues to select claim IDs and directions only; all calculations and
  evidence access remain deterministic and allowlisted.

## Testing

Automated tests mock Ark and PandaData and cover:

- financial growth alignment;
- financial trend requirements and conservative omissions;
- peer extraction, bounding, and target exclusion;
- relative-performance evidence and small-sample handling;
- preservation of the existing thesis-validation and historical cross-check
  paths;
- existing aggregator rendering without frontend changes.

A final manual workflow should use real Ark and PandaData for a single-company
request with Research and Quant dependencies and inspect the resulting
`量化决策校验` block.
