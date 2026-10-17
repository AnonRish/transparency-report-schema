from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, settings

settings.register_profile(
    "ci",
    derandomize=True,
    deadline=None,
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def load_example(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / name).read_text())
    return data


@pytest.fixture
def q3() -> dict[str, Any]:
    """A fresh, mutable copy of the (fictional) Q3 example report data."""
    return copy.deepcopy(load_example("example-report-2026-q3.json"))


@pytest.fixture
def q4() -> dict[str, Any]:
    return copy.deepcopy(load_example("example-report-2026-q4.json"))


def set_path(data: Any, path: str, value: Any) -> None:
    """Set ``data[a][b]...`` for a dotted path (integers index lists)."""
    parts = path.split(".")
    for part in parts[:-1]:
        data = data[int(part)] if isinstance(data, list) else data[part]
    last = parts[-1]
    if isinstance(data, list):
        data[int(last)] = value
    else:
        data[last] = value


def del_path(data: Any, path: str) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        data = data[int(part)] if isinstance(data, list) else data[part]
    last = parts[-1]
    if isinstance(data, list):
        del data[int(last)]
    else:
        del data[last]


def problems_of(data: Any) -> list[str]:
    from transparency_report_schema import validate_report_data

    _, problems = validate_report_data(data)
    return [str(p) for p in problems]


def report_of(data: Any) -> Any:
    from transparency_report_schema import validate_report_data

    report, problems = validate_report_data(data)
    assert report is not None, problems
    return report
