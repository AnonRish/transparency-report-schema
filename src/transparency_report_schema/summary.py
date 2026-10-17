"""A short human-readable summary of a report."""

from __future__ import annotations

from .compute import (
    AI_RD_CATEGORIES,
    INTERNAL_DEPLOYMENT_CATEGORIES,
    category_hours,
    format_bps,
    share_bps,
)
from .models import TransparencyReport
from .types import CATEGORIES


def summarize(report: TransparencyReport) -> str:
    """Render the numbers a reader usually wants first."""
    c = report.compute
    lines = [
        f"Report {report.report_id}: {report.developer.name}",
        f"Period {report.period.start} to {report.period.end}; published {report.published_at}",
        "",
        f"Compute ({c.total_gpu_hours:,} GPU-hours)",
    ]
    hours = category_hours(c)
    for category in CATEGORIES:
        if category in hours:
            lines.append(f"  {category:<26}{format_bps(share_bps(c, (category,))):>9}")
    lines.append(f"  {'AI R&D (total)':<26}{format_bps(share_bps(c, AI_RD_CATEGORIES)):>9}")
    deployed = format_bps(share_bps(c, INTERNAL_DEPLOYMENT_CATEGORIES))
    lines.append(f"  {'internal deployment':<26}{deployed:>9}")
    lines.append("")
    lines.append(f"Models ({len(report.models)})")
    for model in report.models:
        gap = model.gap_days(report.period.end_date)
        gap_text = "n/a" if gap is None else f"{gap} days"
        lines.append(f"  {model.model_id:<24}{model.status:<22}internal->external gap: {gap_text}")
    lines.append("")
    lines.append(f"Spec-adherence evaluations ({len(report.evaluations)})")
    for ev in report.evaluations:
        rate = format_bps((20_000 * ev.n_violations + ev.n_trials) // (2 * ev.n_trials))
        counts = f"{ev.n_violations}/{ev.n_trials} violations ({rate})"
        lines.append(f"  {ev.evaluation_id:<24}{ev.model_id:<20}{counts}")
    lines.append("")
    lines.append(
        f"Incidents: {len(report.incidents)}; qualitative notes: {len(report.qualitative_notes)}"
    )
    return "\n".join(lines)
