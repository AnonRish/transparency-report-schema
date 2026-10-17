"""Sign and verify reports.

A signature covers the **normalised canonical JSON** of the report (absent optional fields
omitted, keys sorted, no whitespace), so two textual encodings of the same report share a
digest. The signed message is ``"TRS-REPORT-v1\\0" || SHA-256(canonical report)``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .canonical import canonicalize
from .crypto import CryptoError, KeyPair, PublicKey, b64decode_strict, b64encode, sha256_hex
from .models import TransparencyReport
from .validate import validate_report_data

SIG_DOMAIN = b"TRS-REPORT-v1\x00"
_ENVELOPE_KEYS = {"report", "report_sha256", "signatures"}
_SIGNATURE_KEYS = {"key_id", "sig"}


@dataclass(frozen=True)
class Signature:
    key_id: str
    sig: str  # base64

    def to_json(self) -> dict[str, str]:
        return {"key_id": self.key_id, "sig": self.sig}


def canonical_bytes(report: TransparencyReport) -> bytes:
    """The canonical encoding that is hashed."""
    return canonicalize(report.to_wire())


def report_digest(report: TransparencyReport) -> str:
    """Hex SHA-256 of the canonical encoding."""
    return sha256_hex(canonical_bytes(report))


def _message(digest_hex: str) -> bytes:
    return SIG_DOMAIN + bytes.fromhex(digest_hex)


def sign_report(report: TransparencyReport, key: KeyPair) -> Signature:
    """Sign ``report`` with ``key``."""
    signature = key.sign(_message(report_digest(report)))
    return Signature(key.public.key_id, b64encode(signature))


def make_envelope(report: TransparencyReport, signatures: Sequence[Signature]) -> dict[str, Any]:
    """A self-describing signed document."""
    return {
        "report": report.to_wire(),
        "report_sha256": report_digest(report),
        "signatures": [s.to_json() for s in signatures],
    }


@dataclass(frozen=True)
class EnvelopeResult:
    """Outcome of :func:`verify_envelope`."""

    ok: bool
    problems: tuple[str, ...]
    signers: tuple[str, ...] = ()
    report: TransparencyReport | None = None
    warnings: tuple[str, ...] = field(default=())


def verify_envelope(
    envelope: Any, pinned: Mapping[str, PublicKey], min_signatures: int = 1
) -> EnvelopeResult:
    """Verify a signed envelope against keys the caller trusts. Never raises on bad input."""
    if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_KEYS:
        return EnvelopeResult(
            False, ("envelope must have exactly report, report_sha256, signatures",)
        )
    report, problems = validate_report_data(envelope["report"])
    if report is None:
        return EnvelopeResult(False, tuple(f"report invalid: {p}" for p in problems))
    digest = report_digest(report)
    if envelope["report_sha256"] != digest:
        return EnvelopeResult(False, ("report_sha256 does not match the report",), report=report)
    signatures = envelope["signatures"]
    if not isinstance(signatures, list):
        return EnvelopeResult(False, ("signatures must be a list",), report=report)
    failures: list[str] = []
    warnings: list[str] = []
    signers: list[str] = []
    for item in signatures:
        if not isinstance(item, dict) or set(item) != _SIGNATURE_KEYS:
            failures.append("each signature must have exactly key_id and sig")
            continue
        key = pinned.get(item["key_id"]) if isinstance(item["key_id"], str) else None
        if key is None:
            warnings.append(f"ignored signature from unpinned key {item['key_id']!r}")
            continue
        try:
            raw = b64decode_strict(item["sig"])
        except CryptoError:
            failures.append(f"signature by {item['key_id']} is not canonical base64")
            continue
        if not key.verify(_message(digest), raw):
            failures.append(f"invalid signature by {item['key_id']}")
        elif item["key_id"] in signers:
            warnings.append(f"duplicate signature by {item['key_id']} counted once")
        else:
            signers.append(item["key_id"])
    if len(signers) < min_signatures:
        failures.append(f"{len(signers)} valid signature(s); {min_signatures} required")
    return EnvelopeResult(not failures, tuple(failures), tuple(signers), report, tuple(warnings))
