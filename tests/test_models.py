from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from conftest import del_path, problems_of, report_of, set_path
from pydantic import ValidationError

from transparency_report_schema import (
    TransparencyReport,
    canonicalize,
    validate_report_data,
    validate_report_text,
)
from transparency_report_schema.types import parse_date, parse_timestamp


def test_the_fictional_examples_are_valid(q3: dict[str, Any], q4: dict[str, Any]) -> None:
    assert problems_of(q3) == []
    assert problems_of(q4) == []


BAD_VALUES: list[tuple[str, Any]] = [
    ("schema_version", "trs/2"),
    ("report_id", "bad id"),
    ("report_id", "-leading"),
    ("developer.name", ""),
    ("developer.name", "n" * 201),
    ("developer.extra", 1),
    ("period.start", "2026-9-30"),
    ("period.start", "2026-02-30"),
    ("period.start", "1999-01-01"),
    ("period.start", "2026-07-01T00:00:00"),
    ("period.start", 20260701),
    ("published_at", "2026-10-15"),
    ("published_at", "2026-10-15T25:00:00Z"),
    ("published_at", "1999-10-15T09:00:00Z"),
    ("models.0.status", "bogus"),
    ("models.0.model_id", "x" * 129),
    ("models.0.first_internal_use", "tomorrow"),
    ("specs.0.sha256", "A" * 64),
    ("specs.0.sha256", "abc"),
    ("specs.0.url", "http://example.com"),
    ("specs.0.url", "https://has space.example"),
    ("specs.0.applies_to", []),
    ("specs.0.summary", ""),
    ("evaluations.0.n_trials", 0),
    ("evaluations.0.n_trials", 1.5),
    ("evaluations.0.n_trials", 12000.0),
    ("evaluations.0.n_trials", "12000"),
    ("evaluations.0.n_trials", True),
    ("evaluations.0.n_violations", -1),
    ("evaluations.0.n_violations", 2**53),
    ("evaluations.0.severity_breakdown", {"catastrophic": 1}),
    ("evaluations.0.severity_breakdown", {"low": -1}),
    ("evaluations.0.method", "vibes"),
    ("incidents.0.severity", "apocalyptic"),
    ("incidents.0.evidence.0.kind", "rumour"),
    ("incidents.0.evidence.0.uri", "ftp://x"),
    ("compute.total_gpu_hours", 0),
    ("compute.breakdown", []),
    ("compute.breakdown.0.category", "mining"),
    ("compute.breakdown.0.gpu_hours", -5),
    ("qualitative_notes.0.topic", "gossip"),
    ("qualitative_notes.0.text", ""),
    ("models", []),
    ("specs", []),
    ("evaluations", "none"),
]


@pytest.mark.parametrize("path,value", BAD_VALUES, ids=[f"{p}={v!r}"[:60] for p, v in BAD_VALUES])
def test_invalid_values_are_rejected_with_a_path(q3: dict[str, Any], path: str, value: Any) -> None:
    set_path(q3, path, value)
    report, problems = validate_report_data(q3)
    assert report is None
    assert any(str(p).startswith(path.rsplit(".", 1)[0]) or path in str(p) for p in problems), (
        problems
    )


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "report_id",
        "developer",
        "period",
        "published_at",
        "models",
        "specs",
        "compute",
    ],
)
def test_required_top_level_fields(q3: dict[str, Any], field: str) -> None:
    del_path(q3, field)
    problems = problems_of(q3)
    assert any(p.startswith(f"{field}: Field required") for p in problems)


@pytest.mark.parametrize("field", ["evaluations", "incidents", "qualitative_notes"])
def test_optional_sections_may_be_omitted(q3: dict[str, Any], field: str) -> None:
    del_path(q3, field)
    if field == "evaluations":
        # Without evaluations the spec-adherence section is simply empty; still valid.
        pass
    assert problems_of(q3) == []


def test_unknown_top_level_fields_are_rejected(q3: dict[str, Any]) -> None:
    q3["surprise"] = 1
    assert any("surprise" in p and "Extra inputs" in p for p in problems_of(q3))


def test_period_must_be_ordered(q3: dict[str, Any]) -> None:
    q3["period"] = {"start": "2026-09-30", "end": "2026-07-01"}
    assert any("period.end is before period.start" in p for p in problems_of(q3))


def test_non_object_input_is_reported() -> None:
    assert problems_of([1, 2]) != []
    assert problems_of(None) != []


def test_wire_form_omits_absent_optionals_and_round_trips(q3: dict[str, Any]) -> None:
    report = report_of(q3)
    wire = report.to_wire()
    assert "first_external_availability" not in wire["models"][1]
    assert wire["specs"][0]["url"].startswith("https://")
    assert TransparencyReport.model_validate(wire) == report
    assert canonicalize(wire) == canonicalize(TransparencyReport.model_validate(wire).to_wire())


def test_reports_are_immutable(q3: dict[str, Any]) -> None:
    report = report_of(q3)
    with pytest.raises(ValidationError):
        report.report_id = "other"  # type: ignore[misc]


def test_gap_days(q3: dict[str, Any]) -> None:
    report = report_of(q3)
    end = report.period.end_date
    assert report.models[0].gap_days(end) == 69  # shipped 2026-02-10 -> 2026-04-20
    assert report.models[1].gap_days(end) == 56  # internal-only: measured up to the period end
    q3["models"][1]["status"] = "retired"
    assert report_of(q3).models[1].gap_days(end) is None


def test_date_helpers() -> None:
    assert parse_date("2026-09-30") == dt.date(2026, 9, 30)
    assert parse_timestamp("2026-10-15T09:00:00Z") == dt.datetime(2026, 10, 15, 9)
    for bad in ("2026-9-30", "2026-02-30", "1999-01-01"):
        with pytest.raises(ValueError):
            parse_date(bad)
    for bad in ("2026-10-15", "2026-10-15T24:00:00Z", "1999-10-15T09:00:00Z"):
        with pytest.raises(ValueError):
            parse_timestamp(bad)


def test_text_validation_collects_json_errors() -> None:
    report, problems = validate_report_text("{")
    assert report is None and problems[0].path == "(json)"
    report, problems = validate_report_text('{"a": 1.5}')
    assert report is None and "floating" in problems[0].message
    report, problems = validate_report_text(b'{"schema_version": "trs/1"}')
    assert report is None and len(problems) >= 7
