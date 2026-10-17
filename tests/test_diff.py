from __future__ import annotations

import copy
from typing import Any

from conftest import del_path, report_of, set_path

from transparency_report_schema import diff_reports
from transparency_report_schema.diff import severity_rank, worst


def kinds(old: dict[str, Any], new: dict[str, Any], **kw: Any) -> list[tuple[str, str, str]]:
    return [
        (c.kind, c.subject, c.severity) for c in diff_reports(report_of(old), report_of(new), **kw)
    ]


def test_an_unchanged_report_for_the_next_period_has_no_differences(q3: dict[str, Any]) -> None:
    following = copy.deepcopy(q3)
    set_path(following, "period", {"start": "2026-10-01", "end": "2026-12-31"})
    set_path(following, "published_at", "2027-01-15T09:00:00Z")
    set_path(following, "qualitative_notes", [])  # notes are period-scoped and need not recur
    assert diff_reports(report_of(q3), report_of(following)) == []
    assert worst([]) == -1
    # Comparing a report with itself is flagged: the two periods coincide.
    assert [c.kind for c in diff_reports(report_of(q3), report_of(copy.deepcopy(q3)))] == [
        "period_overlap"
    ]


def test_the_example_quarters_produce_the_documented_changes(
    q3: dict[str, Any], q4: dict[str, Any]
) -> None:
    changes = kinds(q3, q4)
    assert ("model_added", "beta-1", "info") in changes
    assert ("model_status_changed", "alpha-3-preview", "notice") in changes
    assert ("spec_revised", "alpha-spec", "notice") in changes
    assert ("spec_scope_changed", "alpha-spec", "notice") in changes
    assert ("evaluation_removed", "eval-redteam-1", "warning") in changes
    assert ("compute_share_changed", "internal_deployment_total", "info") in changes
    assert ("compute_total_changed", "total_gpu_hours", "info") in changes
    assert not any(k.startswith("note_") or k == "incident_removed" for k, _, _ in changes)


def test_period_continuity_and_developer(q3: dict[str, Any]) -> None:
    gap = copy.deepcopy(q3)
    set_path(gap, "period", {"start": "2026-10-05", "end": "2026-12-31"})
    set_path(gap, "published_at", "2027-01-15T09:00:00Z")
    set_path(gap, "qualitative_notes", [])
    assert ("period_gap", "period", "warning") in kinds(q3, gap)
    overlap = copy.deepcopy(gap)
    set_path(overlap, "period", {"start": "2026-09-01", "end": "2026-12-31"})
    assert ("period_overlap", "period", "warning") in kinds(q3, overlap)
    other = copy.deepcopy(q3)
    set_path(other, "developer.identifier", "someone-else.invalid")
    assert ("developer_changed", "developer", "warning") in kinds(q3, other)


def test_models(q3: dict[str, Any]) -> None:
    removed = copy.deepcopy(q3)
    del_path(removed, "models.1")
    set_path(removed, "specs.0.applies_to", ["alpha-2"])
    del_path(removed, "evaluations.1")
    del_path(removed, "incidents.0")
    assert ("model_removed", "alpha-3-preview", "warning") in kinds(q3, removed)
    retired_before = copy.deepcopy(q3)
    set_path(retired_before, "models.1.status", "retired")
    assert not any(k == "model_removed" for k, _, _ in kinds(retired_before, removed))
    revised = copy.deepcopy(q3)
    set_path(revised, "models.0.first_internal_use", "2026-01-01")
    set_path(revised, "models.0.first_external_availability", "2026-05-01")
    revisions = [c for c in kinds(q3, revised) if c[0] == "model_dates_revised"]
    assert len(revisions) == 2 and all(c[2] == "warning" for c in revisions)


def test_spec_changes(q3: dict[str, Any]) -> None:
    text_only = copy.deepcopy(q3)
    set_path(text_only, "specs.0.sha256", "b" * 64)
    assert ("spec_changed_without_version_bump", "alpha-spec", "warning") in kinds(q3, text_only)
    version_only = copy.deepcopy(q3)
    set_path(version_only, "specs.0.version", "9")
    assert ("spec_version_changed_without_content_change", "alpha-spec", "warning") in kinds(
        q3, version_only
    )
    renamed = copy.deepcopy(q3)
    set_path(renamed, "specs.0.spec_id", "beta-spec")
    set_path(renamed, "evaluations.0.spec_id", "beta-spec")
    set_path(renamed, "evaluations.1.spec_id", "beta-spec")
    changes = kinds(q3, renamed)
    assert ("spec_added", "beta-spec", "info") in changes
    assert ("spec_removed", "alpha-spec", "warning") in changes


def test_compute_changes_and_the_notice_threshold(q3: dict[str, Any]) -> None:
    shifted = copy.deepcopy(q3)
    set_path(
        shifted,
        "compute.breakdown",
        [
            {"category": "pretraining", "gpu_hours": 40_000_000},
            {"category": "post_training", "gpu_hours": 6_000_000},
            {"category": "ai_rd_experiments", "gpu_hours": 14_000_000},
            {"category": "safety_research", "gpu_hours": 4_000_000},
            {"category": "external_inference", "gpu_hours": 4_000_000},
            {"category": "internal_inference_ai_rd", "gpu_hours": 8_000_000},
            {"category": "internal_inference_other", "gpu_hours": 2_000_000},
            {"category": "other", "gpu_hours": 2_000_000},
        ],
    )
    changes = {(k, s): sev for k, s, sev in kinds(q3, shifted)}
    assert changes[("compute_share_changed", "pretraining")] == "notice"  # 25% -> 50%
    assert changes[("compute_share_changed", "external_inference")] == "notice"
    loose = {(k, s): sev for k, s, sev in kinds(q3, shifted, notice_bps=5000)}
    assert loose[("compute_share_changed", "pretraining")] == "info"  # +25 points < 50
    added = copy.deepcopy(q3)
    del_path(added, "compute.breakdown.7")
    set_path(added, "compute.total_gpu_hours", 78_000_000)
    assert ("compute_category_added", "other", "info") in kinds(added, q3)


def test_evaluations(q3: dict[str, Any]) -> None:
    worse = copy.deepcopy(q3)
    set_path(worse, "evaluations.0.n_violations", 1500)  # 0.30% -> 12.50% (+12.2 points)
    set_path(worse, "evaluations.0.severity_breakdown", {"low": 1500})
    assert ("evaluation_result_changed", "eval-instr-1", "notice") in kinds(q3, worse)
    assert ("evaluation_result_changed", "eval-instr-1", "info") in kinds(
        q3, worse, notice_bps=2000
    )
    better = copy.deepcopy(q3)
    set_path(better, "evaluations.0.n_violations", 1)
    set_path(better, "evaluations.0.severity_breakdown", {"low": 1})
    assert ("evaluation_result_changed", "eval-instr-1", "info") in kinds(q3, better)
    added = copy.deepcopy(q3)
    set_path(added, "evaluations.1.evaluation_id", "eval-new")
    changes = kinds(q3, added)
    assert ("evaluation_added", "eval-new", "info") in changes
    assert ("evaluation_removed", "eval-redteam-1", "warning") in changes
    retired = copy.deepcopy(q3)
    set_path(retired, "models.1.status", "retired")
    del_path(retired, "evaluations.1")
    assert ("evaluation_ended", "eval-redteam-1", "info") in kinds(q3, retired)


def test_incidents(q3: dict[str, Any]) -> None:
    new = copy.deepcopy(q3)
    new["incidents"].append({**copy.deepcopy(new["incidents"][0]), "incident_id": "INC-NEW"})
    assert ("incident_added", "INC-NEW", "notice") in kinds(q3, new)
    down = copy.deepcopy(q3)
    set_path(down, "incidents.0.severity", "low")
    set_path(down, "incidents.0.summary", "Minor logging omission.")
    changes = kinds(q3, down)
    assert ("incident_downgraded", "INC-2026-07", "warning") in changes
    assert ("incident_summary_changed", "INC-2026-07", "notice") in changes
    up = copy.deepcopy(q3)
    set_path(up, "incidents.0.severity", "critical")
    assert ("incident_upgraded", "INC-2026-07", "notice") in kinds(q3, up)


def test_severity_ranking_helpers(q3: dict[str, Any], q4: dict[str, Any]) -> None:
    assert [severity_rank(s) for s in ("info", "notice", "warning")] == [0, 1, 2]
    assert worst(diff_reports(report_of(q3), report_of(q4))) == 2
