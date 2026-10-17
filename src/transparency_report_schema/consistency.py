"""Cross-field rules that JSON Schema cannot express.

Each rule appends a human-readable problem; the model validator raises them all together,
so a report with several inconsistencies reports all of them at once.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .types import parse_date, parse_timestamp

if TYPE_CHECKING:
    from .models import TransparencyReport


def _duplicates(label: str, values: Iterable[str], problems: list[str]) -> None:
    for value, count in sorted(Counter(values).items()):
        if count > 1:
            problems.append(f"{label} {value!r} appears {count} times")


def consistency_problems(report: TransparencyReport) -> list[str]:
    """Return every cross-field inconsistency in ``report`` (empty if consistent)."""
    problems: list[str] = []
    start, end = report.period.start_date, report.period.end_date
    if parse_timestamp(report.published_at).date() < end:
        problems.append("published_at is before the end of the reporting period")

    _duplicates("model_id", (m.model_id for m in report.models), problems)
    _duplicates("spec_id", (s.spec_id for s in report.specs), problems)
    _duplicates("evaluation_id", (e.evaluation_id for e in report.evaluations), problems)
    _duplicates("incident_id", (i.incident_id for i in report.incidents), problems)
    _duplicates("note_id", (n.note_id for n in report.qualitative_notes), problems)
    _duplicates("compute category", (a.category for a in report.compute.breakdown), problems)

    model_ids = {m.model_id for m in report.models}
    spec_ids = {s.spec_id for s in report.specs}
    covered: set[str] = set()

    for model in report.models:
        internal = parse_date(model.first_internal_use)
        if internal > end:
            problems.append(f"model {model.model_id!r}: first_internal_use is after the period end")
        external = model.first_external_availability
        if model.status == "internal_only" and external is not None:
            problems.append(f"model {model.model_id!r}: internal_only but has an external date")
        if model.status in ("limited_external", "generally_available") and external is None:
            problems.append(f"model {model.model_id!r}: {model.status} requires an external date")
        if external is not None:
            external_date = parse_date(external)
            if external_date < internal:
                problems.append(
                    f"model {model.model_id!r}: external availability precedes internal use"
                )
            if external_date > end:
                problems.append(
                    f"model {model.model_id!r}: external availability is after the period end"
                )

    for spec in report.specs:
        if parse_date(spec.effective_date) > end:
            problems.append(f"spec {spec.spec_id!r}: effective_date is after the period end")
        _duplicates(f"spec {spec.spec_id!r} applies_to entry", spec.applies_to, problems)
        for model_id in spec.applies_to:
            if model_id not in model_ids:
                problems.append(f"spec {spec.spec_id!r}: applies_to unknown model {model_id!r}")
        covered.update(spec.applies_to)
    for model in report.models:
        if model.model_id not in covered:
            problems.append(f"model {model.model_id!r} is not covered by any spec")

    applies = {s.spec_id: set(s.applies_to) for s in report.specs}
    for ev in report.evaluations:
        label = f"evaluation {ev.evaluation_id!r}"
        if ev.model_id not in model_ids:
            problems.append(f"{label}: unknown model {ev.model_id!r}")
        if ev.spec_id not in spec_ids:
            problems.append(f"{label}: unknown spec {ev.spec_id!r}")
        elif ev.model_id in model_ids and ev.model_id not in applies[ev.spec_id]:
            problems.append(f"{label}: spec {ev.spec_id!r} does not apply to model {ev.model_id!r}")
        if ev.n_violations > ev.n_trials:
            problems.append(f"{label}: n_violations exceeds n_trials")
        if sum(ev.severity_breakdown.values()) != ev.n_violations:
            problems.append(f"{label}: severity_breakdown must sum to n_violations")

    for incident in report.incidents:
        if incident.model_id not in model_ids:
            problems.append(
                f"incident {incident.incident_id!r}: unknown model {incident.model_id!r}"
            )

    total = sum(a.gpu_hours for a in report.compute.breakdown)
    if total != report.compute.total_gpu_hours:
        problems.append(
            f"compute breakdown sums to {total} GPU-hours but total_gpu_hours is "
            f"{report.compute.total_gpu_hours}"
        )

    for note in report.qualitative_notes:
        if not start <= parse_date(note.noted_on) <= end:
            problems.append(f"note {note.note_id!r}: noted_on is outside the reporting period")
    return problems
