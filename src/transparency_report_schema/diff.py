"""Compare two consecutive reports and flag what changed (and what silently disappeared)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from .compute import (
    AI_RD_CATEGORIES,
    INTERNAL_DEPLOYMENT_CATEGORIES,
    category_hours,
    share_bps,
)
from .models import Evaluation, TransparencyReport
from .types import CATEGORIES

Severity = Literal["info", "notice", "warning"]
_RANK = {"info": 0, "notice": 1, "warning": 2}


@dataclass(frozen=True)
class Change:
    """One difference between two reports."""

    kind: str
    subject: str
    detail: str
    severity: Severity


def worst(changes: list[Change]) -> int:
    """Rank of the most severe change (0 info, 1 notice, 2 warning; -1 if none)."""
    return max((_RANK[c.severity] for c in changes), default=-1)


def severity_rank(name: str) -> int:
    return _RANK[name]


def _rate_bps(ev: Evaluation) -> int:
    return (20_000 * ev.n_violations + ev.n_trials) // (2 * ev.n_trials)


def _delta_severity(delta: int, notice_bps: int) -> Severity:
    return "notice" if abs(delta) >= notice_bps else "info"


def diff_reports(
    old: TransparencyReport, new: TransparencyReport, *, notice_bps: int = 1000
) -> list[Change]:
    """Differences from ``old`` to ``new``.

    ``notice_bps`` only decides when a numeric change is highlighted as a *notice* rather
    than *info*; it is a display threshold, not a judgement.
    """
    changes: list[Change] = []
    _period(old, new, changes)
    _models(old, new, changes)
    _specs(old, new, changes)
    _compute(old, new, changes, notice_bps)
    _evaluations(old, new, changes, notice_bps)
    _incidents(old, new, changes)
    return changes


def _period(old: TransparencyReport, new: TransparencyReport, out: list[Change]) -> None:
    if old.developer.identifier != new.developer.identifier:
        out.append(
            Change(
                "developer_changed",
                "developer",
                f"{old.developer.identifier!r} -> {new.developer.identifier!r}",
                "warning",
            )
        )
    expected = old.period.end_date + dt.timedelta(days=1)
    offset = (new.period.start_date - expected).days
    if offset > 0:
        detail = f"{offset} day(s) between the two reporting periods are not covered"
        out.append(Change("period_gap", "period", detail, "warning"))
    elif offset < 0:
        detail = f"the reporting periods overlap by {-offset} day(s)"
        out.append(Change("period_overlap", "period", detail, "warning"))


def _models(old: TransparencyReport, new: TransparencyReport, out: list[Change]) -> None:
    before = {m.model_id: m for m in old.models}
    after = {m.model_id: m for m in new.models}
    for model_id in sorted(after.keys() - before.keys()):
        out.append(Change("model_added", model_id, f"status {after[model_id].status}", "info"))
    for model_id in sorted(before.keys() - after.keys()):
        if before[model_id].status == "retired":
            continue
        out.append(
            Change("model_removed", model_id, "no longer reported although not retired", "warning")
        )
    for model_id in sorted(before.keys() & after.keys()):
        a, b = before[model_id], after[model_id]
        if a.status != b.status:
            out.append(
                Change("model_status_changed", model_id, f"{a.status} -> {b.status}", "notice")
            )
        if a.first_internal_use != b.first_internal_use:
            detail = f"first_internal_use {a.first_internal_use} -> {b.first_internal_use}"
            out.append(Change("model_dates_revised", model_id, detail, "warning"))
        if (
            a.first_external_availability is not None
            and a.first_external_availability != b.first_external_availability
        ):
            detail = (
                f"first_external_availability {a.first_external_availability} -> "
                f"{b.first_external_availability}"
            )
            out.append(Change("model_dates_revised", model_id, detail, "warning"))


def _specs(old: TransparencyReport, new: TransparencyReport, out: list[Change]) -> None:
    before = {s.spec_id: s for s in old.specs}
    after = {s.spec_id: s for s in new.specs}
    for spec_id in sorted(after.keys() - before.keys()):
        out.append(Change("spec_added", spec_id, f"version {after[spec_id].version}", "info"))
    for spec_id in sorted(before.keys() - after.keys()):
        out.append(Change("spec_removed", spec_id, "no longer reported", "warning"))
    for spec_id in sorted(before.keys() & after.keys()):
        a, b = before[spec_id], after[spec_id]
        text_changed = a.sha256 != b.sha256
        version_changed = a.version != b.version
        if text_changed and version_changed:
            out.append(
                Change("spec_revised", spec_id, f"version {a.version} -> {b.version}", "notice")
            )
        elif text_changed:
            out.append(
                Change(
                    "spec_changed_without_version_bump",
                    spec_id,
                    f"the document hash changed but the version is still {a.version}",
                    "warning",
                )
            )
        elif version_changed:
            out.append(
                Change(
                    "spec_version_changed_without_content_change",
                    spec_id,
                    f"version {a.version} -> {b.version} but the document hash is unchanged",
                    "warning",
                )
            )
        if sorted(a.applies_to) != sorted(b.applies_to):
            detail = f"applies_to {sorted(a.applies_to)} -> {sorted(b.applies_to)}"
            out.append(Change("spec_scope_changed", spec_id, detail, "notice"))


def _compute(
    old: TransparencyReport, new: TransparencyReport, out: list[Change], notice_bps: int
) -> None:
    groups: list[tuple[str, tuple[str, ...]]] = [(c, (c,)) for c in CATEGORIES]
    groups.append(("ai_rd_total", AI_RD_CATEGORIES))
    groups.append(("internal_deployment_total", INTERNAL_DEPLOYMENT_CATEGORIES))
    for name, categories in groups:
        a = share_bps(old.compute, categories)
        b = share_bps(new.compute, categories)
        if a != b:
            delta = b - a
            out.append(
                Change(
                    "compute_share_changed",
                    name,
                    f"{a / 100:.2f}% -> {b / 100:.2f}% ({delta / 100:+.2f} points)",
                    _delta_severity(delta, notice_bps),
                )
            )
    if old.compute.total_gpu_hours != new.compute.total_gpu_hours:
        detail = f"{old.compute.total_gpu_hours} -> {new.compute.total_gpu_hours}"
        out.append(Change("compute_total_changed", "total_gpu_hours", detail, "info"))
    unused = category_hours(new.compute).keys() - category_hours(old.compute).keys()
    for category in sorted(unused):
        out.append(Change("compute_category_added", category, "newly reported", "info"))


def _evaluations(
    old: TransparencyReport, new: TransparencyReport, out: list[Change], notice_bps: int
) -> None:
    before = {e.evaluation_id: e for e in old.evaluations}
    after = {e.evaluation_id: e for e in new.evaluations}
    for evaluation_id in sorted(after.keys() - before.keys()):
        out.append(Change("evaluation_added", evaluation_id, "newly reported", "info"))
    still_reported = {m.model_id for m in new.models if m.status != "retired"}
    for evaluation_id in sorted(before.keys() - after.keys()):
        if before[evaluation_id].model_id in still_reported:
            detail = "results are no longer reported although the model still is"
            out.append(Change("evaluation_removed", evaluation_id, detail, "warning"))
        else:
            detail = "the model is no longer reported or is retired"
            out.append(Change("evaluation_ended", evaluation_id, detail, "info"))
    for evaluation_id in sorted(before.keys() & after.keys()):
        a, b = before[evaluation_id], after[evaluation_id]
        if (a.n_trials, a.n_violations) != (b.n_trials, b.n_violations):
            delta = _rate_bps(b) - _rate_bps(a)
            detail = (
                f"{a.n_violations}/{a.n_trials} -> {b.n_violations}/{b.n_trials} violations "
                f"({delta / 100:+.2f} points)"
            )
            severity: Severity = "notice" if delta >= notice_bps else "info"
            out.append(Change("evaluation_result_changed", evaluation_id, detail, severity))


_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _incidents(old: TransparencyReport, new: TransparencyReport, out: list[Change]) -> None:
    """Reports are per-period, so incidents or notes that simply do not recur are not flagged;
    an incident that *does* recur is checked for quiet downgrades."""
    before = {i.incident_id: i for i in old.incidents}
    after = {i.incident_id: i for i in new.incidents}
    for incident_id in sorted(after.keys() - before.keys()):
        out.append(
            Change(
                "incident_added", incident_id, f"severity {after[incident_id].severity}", "notice"
            )
        )
    for incident_id in sorted(before.keys() & after.keys()):
        a, b = before[incident_id], after[incident_id]
        change = f"{a.severity} -> {b.severity}"
        if _SEVERITY_ORDER[b.severity] < _SEVERITY_ORDER[a.severity]:
            out.append(Change("incident_downgraded", incident_id, change, "warning"))
        elif _SEVERITY_ORDER[b.severity] > _SEVERITY_ORDER[a.severity]:
            out.append(Change("incident_upgraded", incident_id, change, "notice"))
        if a.summary != b.summary:
            out.append(
                Change(
                    "incident_summary_changed", incident_id, "the summary was rewritten", "notice"
                )
            )
