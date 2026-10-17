from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from conftest import ROOT, load_example, problems_of, set_path

from transparency_report_schema import TransparencyReport

SCHEMA_PATH = ROOT / "schema" / "transparency-report.schema.json"


def committed_schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SCHEMA_PATH.read_text())
    return data


def test_the_committed_schema_matches_the_models() -> None:
    generated = json.loads(json.dumps(TransparencyReport.model_json_schema()))
    assert committed_schema() == generated, "run scripts/make_examples.py to regenerate the schema"


def test_the_schema_forbids_unknown_fields() -> None:
    schema = committed_schema()
    assert schema["additionalProperties"] is False
    assert all(
        d.get("additionalProperties") is False
        for d in schema["$defs"].values()
        if d.get("type") == "object" and "properties" in d
    )


@pytest.mark.parametrize("name", ["example-report-2026-q3.json", "example-report-2026-q4.json"])
def test_examples_validate_against_the_json_schema(name: str) -> None:
    jsonschema.Draft202012Validator(committed_schema()).validate(load_example(name))


STRUCTURAL: list[tuple[str, Any]] = [
    ("schema_version", "trs/2"),
    ("report_id", "bad id"),
    ("specs.0.sha256", "A" * 64),
    ("specs.0.url", "http://example.com"),
    ("models.0.status", "bogus"),
    ("evaluations.0.n_trials", 1.5),
    ("evaluations.0.n_trials", "12000"),
    ("evaluations.0.n_trials", True),
    ("evaluations.0.n_trials", 0),
    ("evaluations.0.n_violations", -1),
    ("evaluations.0.n_violations", 2**53),
    ("evaluations.0.severity_breakdown", {"catastrophic": 1}),
    ("compute.breakdown", []),
    ("models", []),
    ("developer.extra", 1),
    ("specs.0.applies_to", []),
    ("period.start", "2026-9-30"),
    ("published_at", "2026-10-15"),
]


@pytest.mark.parametrize("path,value", STRUCTURAL, ids=[f"{p}={v!r}" for p, v in STRUCTURAL])
def test_the_json_schema_and_the_models_agree_on_structural_errors(
    q3: dict[str, Any], path: str, value: Any
) -> None:
    set_path(q3, path, value)
    assert problems_of(q3) != []
    assert not jsonschema.Draft202012Validator(committed_schema()).is_valid(q3)


def test_json_schema_is_structural_only_cross_field_rules_need_the_python_validator(
    q3: dict[str, Any],
) -> None:
    """Counts that do not add up, impossible dates and dangling references pass JSON Schema
    (it cannot express them) but are rejected by the Python validator."""
    for path, value in (
        ("compute.total_gpu_hours", 1),
        ("period.start", "2026-02-30"),
        ("evaluations.0.model_id", "ghost"),
    ):
        broken = json.loads(json.dumps(q3))
        set_path(broken, path, value)
        assert jsonschema.Draft202012Validator(committed_schema()).is_valid(broken)
        assert problems_of(broken) != []


def test_schema_file_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(committed_schema())
    assert Path(SCHEMA_PATH).read_text().endswith("\n")
