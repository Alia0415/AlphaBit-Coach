"""Evidence bundle construction for ResultAggregator (spec §13.1).

Builds a deterministic, dimension-organized evidence structure from
actual ExpertResult data. Used as the input to SynthesisDraft generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.core.contracts import (
    EvidenceCoverage,
    EvidenceStatus,
    ExecutionPlan,
    ExpertResult,
)
from backend.core.task_spec import ResearchDimension, TaskSpec


@dataclass
class DimensionEvidence:
    """All evidence collected for one research dimension."""

    dimension: ResearchDimension
    evidence_ids: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    source_steps: list[str] = field(default_factory=list)
    status: EvidenceStatus = "unavailable"


@dataclass
class EvidenceBundle:
    """Deterministic, dimension-organized evidence for aggregation."""

    dimensions: dict[ResearchDimension, DimensionEvidence] = field(
        default_factory=dict
    )
    all_evidence_ids: set[str] = field(default_factory=set)
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    blocked_steps: list[str] = field(default_factory=list)
    missing_dimensions: list[ResearchDimension] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def coverage_list(self) -> list[EvidenceCoverage]:
        """Generate coverage summaries for each required dimension."""
        coverages: list[EvidenceCoverage] = []
        for dim, evidence in sorted(
            self.dimensions.items(), key=lambda x: x[0]
        ):
            coverages.append(
                EvidenceCoverage(
                    dimension=dim,
                    status=evidence.status,
                    expected_items=max(1, len(evidence.items)),
                    available_items=len(evidence.items),
                    missing_items=(
                        [f"{dim} evidence unavailable"]
                        if evidence.status == "unavailable"
                        else []
                    ),
                )
            )
        return coverages


def build_evidence_bundle(
    task_spec: TaskSpec,
    plan: ExecutionPlan,
    results: dict[str, ExpertResult],
) -> EvidenceBundle:
    """Construct an EvidenceBundle from plan structure and actual results.

    This is the sole deterministic input preparation for the synthesis model.
    """
    bundle = EvidenceBundle()

    # Initialize dimensions from TaskSpec
    all_dims = set(task_spec.required_dimensions) | set(
        task_spec.optional_dimensions
    )
    for dim in all_dims:
        bundle.dimensions[dim] = DimensionEvidence(dimension=dim)

    # Map plan steps to dimensions
    step_dimension_map: dict[str, list[ResearchDimension]] = {}
    for step in plan.steps:
        step_dimension_map[step.id] = list(step.covers_dimensions)

    # Process results
    evidence_counter = 0
    for step in plan.steps:
        result = results.get(step.id)
        if result is None:
            bundle.blocked_steps.append(step.id)
            continue

        if result.status == "completed":
            bundle.completed_steps.append(step.id)
        elif result.status == "failed":
            bundle.failed_steps.append(step.id)
        elif result.status == "blocked":
            bundle.blocked_steps.append(step.id)

        # Assign evidence to dimensions
        step_dims = step_dimension_map.get(step.id, [])
        for dim in step_dims:
            if dim not in bundle.dimensions:
                bundle.dimensions[dim] = DimensionEvidence(dimension=dim)
            dim_evidence = bundle.dimensions[dim]
            dim_evidence.source_steps.append(step.id)

            if result.status == "completed":
                # Generate evidence IDs for each evidence item
                for item in result.evidence:
                    evidence_counter += 1
                    eid = f"ev-{step.id}-{evidence_counter:04d}"
                    dim_evidence.evidence_ids.append(eid)
                    dim_evidence.items.append({
                        "evidence_id": eid,
                        "step_id": step.id,
                        "agent": result.agent.value,
                        "data": item,
                    })
                    bundle.all_evidence_ids.add(eid)

                # Also include summary as evidence if no structured items
                if not result.evidence and result.summary:
                    evidence_counter += 1
                    eid = f"ev-{step.id}-{evidence_counter:04d}"
                    dim_evidence.evidence_ids.append(eid)
                    dim_evidence.items.append({
                        "evidence_id": eid,
                        "step_id": step.id,
                        "agent": result.agent.value,
                        "data": {"type": "summary", "text": result.summary},
                    })
                    bundle.all_evidence_ids.add(eid)

    # Determine dimension statuses
    for dim, dim_evidence in bundle.dimensions.items():
        if not dim_evidence.source_steps:
            dim_evidence.status = "unavailable"
        elif not dim_evidence.items:
            # Steps assigned but no evidence produced
            if any(s in bundle.failed_steps for s in dim_evidence.source_steps):
                dim_evidence.status = "unavailable"
            elif any(s in bundle.blocked_steps for s in dim_evidence.source_steps):
                dim_evidence.status = "unavailable"
            else:
                dim_evidence.status = "insufficient"
        elif len(dim_evidence.items) < 3:
            dim_evidence.status = "partial"
        else:
            dim_evidence.status = "sufficient"

    # Identify missing required dimensions
    for dim in task_spec.required_dimensions:
        dim_ev = bundle.dimensions.get(dim)
        if dim_ev is None or dim_ev.status == "unavailable":
            bundle.missing_dimensions.append(dim)

    return bundle


def validate_evidence_ids(
    claimed_ids: list[str],
    allowlist: set[str],
) -> tuple[list[str], list[str]]:
    """Validate that claimed evidence IDs exist in the allowlist.

    Returns (valid_ids, invalid_ids).
    """
    valid = [eid for eid in claimed_ids if eid in allowlist]
    invalid = [eid for eid in claimed_ids if eid not in allowlist]
    return valid, invalid
