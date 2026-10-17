from __future__ import annotations

import copy
from typing import Any

import pytest
from conftest import del_path, problems_of, report_of, set_path

from transparency_report_schema import consistency_problems


def _dup_spec(d: dict[str, Any]) -> None:
    d["specs"].append(copy.deepcopy(d["specs"][0]))


def _dup_incident(d: dict[str, Any]) -> None:
    d["incidents"].append(copy.deepcopy(d["incidents"][0]))


def _dup_note(d: dict[str, Any]) -> None:
    d["qualitative_notes"].append(copy.deepcopy(d["qualitative_notes"][0]))


def _dup_category(d: dict[str, Any]) -> None:
    d["compute"]["breakdown"].append(copy.deepcopy(d["compute"]["breakdown"][0]))


def _second_spec_for_beta(d: dict[str, Any]) -> None:
    spec = copy.deepcopy(d["specs"][0])
    spec.update({"spec_id": "other-spec", "applies_to": ["alpha-3-preview"]})
    d["specs"].append(spec)
    d["evaluations"][0]["spec_id"] = "other-spec"  # eval of alpha-2 under a spec that excludes it


CASES: list[tuple[str, Any, str]] = [
    (
        "published before period end",
        lambda d: set_path(d, "published_at", "2026-09-29T00:00:00Z"),
        "published_at is before",
    ),
    (
        "duplicate model",
        lambda d: set_path(d, "models.1.model_id", "alpha-2"),
        "model_id 'alpha-2' appears 2 times",
    ),
    ("duplicate spec", _dup_spec, "spec_id 'alpha-spec' appears 2 times"),
    (
        "duplicate evaluation",
        lambda d: set_path(d, "evaluations.1.evaluation_id", "eval-instr-1"),
        "evaluation_id 'eval-instr-1' appears 2 times",
    ),
    ("duplicate incident", _dup_incident, "incident_id 'INC-2026-07' appears 2 times"),
    ("duplicate note", _dup_note, "note_id 'note-1' appears 2 times"),
    ("duplicate compute category", _dup_category, "compute category 'pretraining' appears 2 times"),
    (
        "internal use after period end",
        lambda d: set_path(d, "models.1.first_internal_use", "2026-10-05"),
        "first_internal_use is after the period end",
    ),
    (
        "internal-only with external date",
        lambda d: set_path(d, "models.1.first_external_availability", "2026-09-01"),
        "internal_only but has an external date",
    ),
    (
        "GA without external date",
        lambda d: del_path(d, "models.0.first_external_availability"),
        "requires an external date",
    ),
    (
        "external before internal",
        lambda d: set_path(d, "models.0.first_external_availability", "2026-01-01"),
        "precedes internal use",
    ),
    (
        "external after period end",
        lambda d: set_path(d, "models.0.first_external_availability", "2026-10-15"),
        "external availability is after the period end",
    ),
    (
        "spec effective after period end",
        lambda d: set_path(d, "specs.0.effective_date", "2026-10-01"),
        "effective_date is after the period end",
    ),
    (
        "spec for unknown model",
        lambda d: d["specs"][0]["applies_to"].append("ghost"),
        "applies_to unknown model 'ghost'",
    ),
    (
        "duplicate applies_to entry",
        lambda d: d["specs"][0]["applies_to"].append("alpha-2"),
        "applies_to entry 'alpha-2' appears 2 times",
    ),
    (
        "model without spec",
        lambda d: set_path(d, "specs.0.applies_to", ["alpha-2"]),
        "model 'alpha-3-preview' is not covered by any spec",
    ),
    (
        "evaluation of unknown model",
        lambda d: set_path(d, "evaluations.0.model_id", "ghost"),
        "unknown model 'ghost'",
    ),
    (
        "evaluation of unknown spec",
        lambda d: set_path(d, "evaluations.0.spec_id", "ghost"),
        "unknown spec 'ghost'",
    ),
    (
        "spec does not apply to the evaluated model",
        _second_spec_for_beta,
        "does not apply to model 'alpha-2'",
    ),
    (
        "more violations than trials",
        lambda d: set_path(d, "evaluations.0.n_trials", 10),
        "n_violations exceeds n_trials",
    ),
    (
        "severity breakdown mismatch",
        lambda d: set_path(d, "evaluations.0.severity_breakdown", {"low": 1}),
        "severity_breakdown must sum to n_violations",
    ),
    (
        "violations without breakdown",
        lambda d: set_path(d, "evaluations.0.severity_breakdown", {}),
        "severity_breakdown must sum",
    ),
    (
        "incident for unknown model",
        lambda d: set_path(d, "incidents.0.model_id", "ghost"),
        "unknown model 'ghost'",
    ),
    (
        "compute does not add up",
        lambda d: set_path(d, "compute.total_gpu_hours", 80_000_001),
        "sums to 80000000 GPU-hours but total_gpu_hours is 80000001",
    ),
    (
        "note outside the period",
        lambda d: set_path(d, "qualitative_notes.0.noted_on", "2026-06-30"),
        "noted_on is outside the reporting period",
    ),
]


@pytest.mark.parametrize("name,mutate,expected", CASES, ids=[c[0] for c in CASES])
def test_each_consistency_rule_fires(
    q3: dict[str, Any], name: str, mutate: Any, expected: str
) -> None:
    mutate(q3)
    problems = problems_of(q3)
    assert any(expected in p for p in problems), (name, problems)
    assert all(p.startswith("(report): ") for p in problems)


def test_all_inconsistencies_are_reported_together(q3: dict[str, Any]) -> None:
    set_path(q3, "compute.total_gpu_hours", 1)
    set_path(q3, "published_at", "2026-01-01T00:00:00Z")
    set_path(q3, "evaluations.0.n_trials", 5)
    problems = problems_of(q3)
    assert len(problems) >= 3
    assert any("GPU-hours" in p for p in problems)
    assert any("published_at" in p for p in problems)
    assert any("n_violations exceeds" in p for p in problems)


def test_a_valid_report_has_no_problems(q3: dict[str, Any]) -> None:
    assert consistency_problems(report_of(q3)) == []
