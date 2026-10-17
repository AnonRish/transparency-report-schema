"""transparency-report-schema: a strict schema and toolkit for frontier-AI transparency reports."""

from __future__ import annotations

__version__ = "0.1.0"

from .canonical import CanonicalError, canonicalize, loads_strict
from .compute import (
    AI_RD_CATEGORIES,
    INTERNAL_DEPLOYMENT_CATEGORIES,
    exceeds_bps,
    format_bps,
    share,
    share_bps,
)
from .consistency import consistency_problems
from .crypto import KeyPair, PublicKey
from .diff import Change, diff_reports
from .models import (
    Compute,
    ComputeAllocation,
    Developer,
    Evaluation,
    EvidenceRef,
    IncidentRef,
    ModelEntry,
    QualitativeNote,
    ReportingPeriod,
    SpecDocument,
    TransparencyReport,
)
from .policy import Finding, Policy, check_policy
from .signing import (
    EnvelopeResult,
    Signature,
    make_envelope,
    report_digest,
    sign_report,
    verify_envelope,
)
from .summary import summarize
from .validate import Problem, validate_report_data, validate_report_text

__all__ = [
    "AI_RD_CATEGORIES",
    "INTERNAL_DEPLOYMENT_CATEGORIES",
    "CanonicalError",
    "Change",
    "Compute",
    "ComputeAllocation",
    "Developer",
    "EnvelopeResult",
    "Evaluation",
    "EvidenceRef",
    "Finding",
    "IncidentRef",
    "KeyPair",
    "ModelEntry",
    "Policy",
    "Problem",
    "PublicKey",
    "QualitativeNote",
    "ReportingPeriod",
    "Signature",
    "SpecDocument",
    "TransparencyReport",
    "__version__",
    "canonicalize",
    "check_policy",
    "consistency_problems",
    "diff_reports",
    "exceeds_bps",
    "format_bps",
    "loads_strict",
    "make_envelope",
    "report_digest",
    "share",
    "share_bps",
    "sign_report",
    "summarize",
    "validate_report_data",
    "validate_report_text",
    "verify_envelope",
]
