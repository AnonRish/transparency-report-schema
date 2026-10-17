"""Constrained field types shared by the models (all strict: no silent coercion)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints

from .canonical import MAX_SAFE_INT

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MIN_YEAR = 2000


def parse_date(text: str) -> date:
    """Parse a canonical ``YYYY-MM-DD`` date or raise ``ValueError``."""
    if not _DATE_RE.match(text):
        raise ValueError("must be a date like 2026-09-30")
    try:
        value = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"not a real calendar date: {text}") from exc
    if value.year < MIN_YEAR:
        raise ValueError(f"year must be >= {MIN_YEAR}")
    return value


def parse_timestamp(text: str) -> datetime:
    """Parse a canonical ``YYYY-MM-DDTHH:MM:SSZ`` timestamp (naive UTC) or raise ``ValueError``."""
    if not _TIMESTAMP_RE.match(text):
        raise ValueError("must be a UTC timestamp like 2026-10-15T09:00:00Z")
    try:
        value = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"not a real timestamp: {text}") from exc
    if value.year < MIN_YEAR:
        raise ValueError(f"year must be >= {MIN_YEAR}")
    return value


def _check_date(text: str) -> str:
    parse_date(text)
    return text


def _check_timestamp(text: str) -> str:
    parse_timestamp(text)
    return text


Ident = Annotated[str, StringConstraints(pattern=ID_PATTERN)]
Hex64 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://[^\s/]+(/\S*)?$", max_length=2000)]
IsoDate = Annotated[
    str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"), AfterValidator(_check_date)
]
IsoTimestamp = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),
    AfterValidator(_check_timestamp),
]
NonNegInt = Annotated[int, Field(strict=True, ge=0, le=MAX_SAFE_INT)]
PosInt = Annotated[int, Field(strict=True, ge=1, le=MAX_SAFE_INT)]
Bps = Annotated[int, Field(strict=True, ge=0, le=10_000)]

Severity = Literal["low", "medium", "high", "critical"]
Category = Literal[
    "pretraining",
    "post_training",
    "ai_rd_experiments",
    "safety_research",
    "external_inference",
    "internal_inference_ai_rd",
    "internal_inference_other",
    "other",
]
CATEGORIES: tuple[str, ...] = (
    "pretraining",
    "post_training",
    "ai_rd_experiments",
    "safety_research",
    "external_inference",
    "internal_inference_ai_rd",
    "internal_inference_other",
    "other",
)
