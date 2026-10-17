"""The transparency-report data model (Pydantic v2, strict, no extra fields).

Everything on the wire is a string, a non-negative integer, a boolean, an object or a list:
no floating-point numbers (shares are expressed in basis points, i.e. 1/100 of a percent),
so reports have a single canonical encoding and can be hashed and signed.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .types import (
    Category,
    Hex64,
    HttpsUrl,
    Ident,
    IsoDate,
    IsoTimestamp,
    NonNegInt,
    PosInt,
    Severity,
    parse_date,
)

Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Summary = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=8000)]

ModelStatus = Literal["internal_only", "limited_external", "generally_available", "retired"]
EvaluationMethod = Literal[
    "automated_eval", "red_team", "production_audit", "human_review", "other"
]
NoteTopic = Literal["ai_rd_automation", "autonomy", "oversight", "surprises", "safety", "other"]


class Strict(BaseModel):
    """Base class: unknown fields are errors and instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Developer(Strict):
    name: Name
    identifier: Name


class ReportingPeriod(Strict):
    start: IsoDate
    end: IsoDate

    @model_validator(mode="after")
    def _ordered(self) -> ReportingPeriod:
        if parse_date(self.end) < parse_date(self.start):
            raise ValueError("period.end is before period.start")
        return self

    @property
    def start_date(self) -> dt.date:
        return parse_date(self.start)

    @property
    def end_date(self) -> dt.date:
        return parse_date(self.end)


class ModelEntry(Strict):
    model_id: Ident
    name: Name
    version: Name
    status: ModelStatus
    first_internal_use: IsoDate
    first_external_availability: IsoDate | None = None

    def gap_days(self, as_of: dt.date) -> int | None:
        """Days between first internal use and first external availability.

        For a model that is still internal-only the gap is measured up to ``as_of``.
        Retired models that never shipped have no meaningful gap (``None``).
        """
        internal = parse_date(self.first_internal_use)
        if self.first_external_availability is not None:
            return (parse_date(self.first_external_availability) - internal).days
        if self.status == "internal_only":
            return (as_of - internal).days
        return None


class SpecDocument(Strict):
    spec_id: Ident
    title: Name
    version: Name
    applies_to: Annotated[list[Ident], Field(min_length=1)]
    effective_date: IsoDate
    sha256: Hex64
    url: HttpsUrl | None = None
    summary: Summary | None = None


class EvidenceRef(Strict):
    kind: Literal["ledger_bundle", "report", "other"]
    sha256: Hex64
    uri: HttpsUrl | None = None


class Evaluation(Strict):
    evaluation_id: Ident
    model_id: Ident
    spec_id: Ident
    method: EvaluationMethod
    description: Summary
    n_trials: PosInt
    n_violations: NonNegInt
    severity_breakdown: dict[Severity, NonNegInt] = Field(default_factory=dict)
    notes: Summary | None = None


class IncidentRef(Strict):
    incident_id: Ident
    model_id: Ident
    severity: Severity
    summary: Summary
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ComputeAllocation(Strict):
    category: Category
    gpu_hours: NonNegInt


class Compute(Strict):
    total_gpu_hours: PosInt
    breakdown: Annotated[list[ComputeAllocation], Field(min_length=1)]


class QualitativeNote(Strict):
    note_id: Ident
    noted_on: IsoDate
    topic: NoteTopic
    text: LongText


class TransparencyReport(Strict):
    schema_version: Literal["trs/1"]
    report_id: Ident
    developer: Developer
    period: ReportingPeriod
    published_at: IsoTimestamp
    models: Annotated[list[ModelEntry], Field(min_length=1)]
    specs: Annotated[list[SpecDocument], Field(min_length=1)]
    evaluations: list[Evaluation] = Field(default_factory=list)
    incidents: list[IncidentRef] = Field(default_factory=list)
    compute: Compute
    qualitative_notes: list[QualitativeNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> TransparencyReport:
        from .consistency import consistency_problems

        problems = consistency_problems(self)
        if problems:
            raise ValueError("\n".join(problems))
        return self

    def to_wire(self) -> dict[str, Any]:
        """Normalised JSON-ready form (absent optional fields omitted): what gets hashed."""
        return self.model_dump(mode="json", exclude_none=True)
