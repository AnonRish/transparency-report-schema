"""Policy checks: compare a report against limits chosen by whoever is reviewing it.

The limits are *parameters*. This module takes no position on what the right values are or
on what any law requires; it only evaluates a report against the numbers it is given.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from .compute import (
    AI_RD_CATEGORIES,
    INTERNAL_DEPLOYMENT_CATEGORIES,
    exceeds_bps,
    format_bps,
    share_bps,
)
from .models import Strict, TransparencyReport
from .types import Bps, Category, NonNegInt


class Policy(Strict):
    """Limits to check. ``None`` disables a check."""

    max_ai_rd_share_bps: Bps | None = None
    ai_rd_categories: Annotated[list[Category], Field(min_length=1)] = Field(
        default_factory=lambda: list(AI_RD_CATEGORIES)  # type: ignore[arg-type]
    )
    max_internal_deployment_share_bps: Bps | None = None
    max_internal_external_gap_days: NonNegInt | None = None
    require_adherence_evaluation_per_model: bool = True
    min_trials_per_evaluation: NonNegInt = 0
    max_violation_rate_bps: Bps | None = None


@dataclass(frozen=True)
class Finding:
    """One way in which a report exceeds a policy."""

    code: str
    subject: str
    message: str


def check_policy(report: TransparencyReport, policy: Policy) -> list[Finding]:
    """Return every policy violation found in ``report`` (empty if none)."""
    findings: list[Finding] = []
    compute = report.compute
    if policy.max_ai_rd_share_bps is not None and exceeds_bps(
        compute, policy.ai_rd_categories, policy.max_ai_rd_share_bps
    ):
        findings.append(
            Finding(
                "AI_RD_SHARE_EXCEEDS_CAP",
                "compute",
                f"AI R&D share {format_bps(share_bps(compute, policy.ai_rd_categories))} exceeds "
                f"the cap of {format_bps(policy.max_ai_rd_share_bps)}",
            )
        )
    if policy.max_internal_deployment_share_bps is not None and exceeds_bps(
        compute, INTERNAL_DEPLOYMENT_CATEGORIES, policy.max_internal_deployment_share_bps
    ):
        findings.append(
            Finding(
                "INTERNAL_DEPLOYMENT_SHARE_EXCEEDS_CAP",
                "compute",
                "internal deployment share "
                f"{format_bps(share_bps(compute, INTERNAL_DEPLOYMENT_CATEGORIES))} exceeds the cap "
                f"of {format_bps(policy.max_internal_deployment_share_bps)}",
            )
        )
    evaluated = {e.model_id for e in report.evaluations}
    for model in report.models:
        gap = model.gap_days(report.period.end_date)
        cap = policy.max_internal_external_gap_days
        if cap is not None and gap is not None and gap > cap:
            findings.append(
                Finding(
                    "INTERNAL_EXTERNAL_GAP_EXCEEDS_CAP",
                    model.model_id,
                    f"internal-to-external gap of {gap} days exceeds the cap of {cap} days",
                )
            )
        if (
            policy.require_adherence_evaluation_per_model
            and model.status != "retired"
            and model.model_id not in evaluated
        ):
            findings.append(
                Finding(
                    "MODEL_WITHOUT_ADHERENCE_EVALUATION",
                    model.model_id,
                    "no spec-adherence evaluation is reported for this model",
                )
            )
    for ev in report.evaluations:
        if ev.n_trials < policy.min_trials_per_evaluation:
            findings.append(
                Finding(
                    "EVALUATION_TOO_SMALL",
                    ev.evaluation_id,
                    f"{ev.n_trials} trials is below the minimum of "
                    f"{policy.min_trials_per_evaluation}",
                )
            )
        cap_bps = policy.max_violation_rate_bps
        if cap_bps is not None and ev.n_violations * 10_000 > cap_bps * ev.n_trials:
            rate = (20_000 * ev.n_violations + ev.n_trials) // (2 * ev.n_trials)
            findings.append(
                Finding(
                    "VIOLATION_RATE_ABOVE_THRESHOLD",
                    ev.evaluation_id,
                    f"violation rate {format_bps(rate)} exceeds {format_bps(cap_bps)}",
                )
            )
    return findings
