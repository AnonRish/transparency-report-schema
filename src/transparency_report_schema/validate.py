"""Validate raw JSON data into a report, collecting every problem with a path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .canonical import CanonicalError, loads_strict
from .models import TransparencyReport

_PREFIX = "Value error, "


@dataclass(frozen=True)
class Problem:
    """One reason a report is invalid. ``path`` is dotted (``models.0.status``)."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def validate_report_data(data: Any) -> tuple[TransparencyReport | None, list[Problem]]:
    """Return ``(report, [])`` if ``data`` is a valid report, else ``(None, problems)``."""
    try:
        return TransparencyReport.model_validate(data), []
    except ValidationError as exc:
        problems: list[Problem] = []
        for error in exc.errors():
            path = ".".join(str(part) for part in error["loc"]) or "(report)"
            message = error["msg"].removeprefix(_PREFIX)
            if error["type"] == "value_error":
                problems.extend(Problem(path, line) for line in message.split("\n"))
            else:
                problems.append(Problem(path, message))
        return None, problems


def validate_report_text(text: str | bytes) -> tuple[TransparencyReport | None, list[Problem]]:
    """Strictly parse JSON (no floats, no duplicate keys) and validate it."""
    try:
        data = loads_strict(text)
    except CanonicalError as exc:
        return None, [Problem("(json)", str(exc))]
    return validate_report_data(data)
