"""Command-line interface (``trs``)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import __version__
from .canonical import CanonicalError, canonicalize, loads_strict
from .crypto import CryptoError, KeyPair, PublicKey
from .diff import diff_reports, worst
from .models import TransparencyReport
from .policy import Policy, check_policy
from .signing import (
    Signature,
    canonical_bytes,
    make_envelope,
    report_digest,
    sign_report,
    verify_envelope,
)
from .summary import summarize
from .validate import Problem, validate_report_data


class CliError(ValueError):
    """A user-facing error."""


def _read(path: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise CliError(f"cannot read {path}: {exc.strerror}") from exc


def _read_json(path: str) -> Any:
    try:
        return loads_strict(_read(path))
    except CanonicalError as exc:
        raise CliError(f"{path}: {exc}") from exc


def _load_report(path: str) -> tuple[TransparencyReport | None, list[Problem]]:
    try:
        data = loads_strict(_read(path))
    except CanonicalError as exc:
        return None, [Problem("(json)", str(exc))]
    return validate_report_data(data)


def _report_or_fail(path: str) -> TransparencyReport:
    report, problems = _load_report(path)
    if report is None:
        details = "\n".join(f"  {p}" for p in problems)
        raise CliError(f"{path} is not a valid report:\n{details}")
    return report


def _write_private(path: str, pem: bytes, force: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise CliError(f"{path} already exists (use --force to overwrite)") from exc
    with os.fdopen(fd, "wb") as handle:
        handle.write(pem)


def _load_pub(path: str) -> PublicKey:
    data = _read_json(path)
    if not isinstance(data, dict) or set(data) != {"key_id", "public_key"}:
        raise CliError(f"{path}: not a public key file")
    key = PublicKey.from_b64(data["public_key"])
    if key.key_id != data["key_id"]:
        raise CliError(f"{path}: key_id does not match the public key")
    return key


def _cmd_validate(args: argparse.Namespace) -> int:
    report, problems = _load_report(args.report)
    if report is None:
        print(f"INVALID: {args.report}")
        for problem in problems:
            print(f"  {problem}")
        return 1
    models, evaluations = len(report.models), len(report.evaluations)
    print(f"VALID: {report.report_id} ({models} model(s), {evaluations} evaluation(s))")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    print(summarize(_report_or_fail(args.report)))
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    report = _report_or_fail(args.report)
    policy = Policy.model_validate(_read_json(args.policy))
    findings = check_policy(report, policy)
    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2, sort_keys=True))
    elif findings:
        for finding in findings:
            print(f"VIOLATION {finding.code} [{finding.subject}]: {finding.message}")
    else:
        print("OK: no policy violations")
    return 1 if findings else 0


def _cmd_diff(args: argparse.Namespace) -> int:
    changes = diff_reports(
        _report_or_fail(args.old), _report_or_fail(args.new), notice_bps=args.notice_bps
    )
    if args.json:
        print(json.dumps([c.__dict__ for c in changes], indent=2, sort_keys=True))
    elif changes:
        for change in changes:
            print(f"{change.severity.upper():<8}{change.kind} [{change.subject}]: {change.detail}")
    else:
        print("no differences")
    threshold = {"none": 99, "notice": 1, "warning": 2}[args.fail_on]
    return 1 if worst(changes) >= threshold else 0


def _cmd_schema(args: argparse.Namespace) -> int:
    text = json.dumps(TransparencyReport.model_json_schema(), indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text, end="")
    return 0


def _cmd_canonical(args: argparse.Namespace) -> int:
    report = _report_or_fail(args.report)
    if args.print:
        print(canonical_bytes(report).decode())
    print(f"sha256 {report_digest(report)}")
    return 0


def _cmd_keygen(args: argparse.Namespace) -> int:
    key = KeyPair.generate()
    _write_private(args.out, key.to_pem(), args.force)
    if args.pub_out:
        record = {"key_id": key.public.key_id, "public_key": key.public.to_b64()}
        Path(args.pub_out).write_bytes(canonicalize(record) + b"\n")
    print(key.public.key_id)
    return 0


def _cmd_sign(args: argparse.Namespace) -> int:
    report = _report_or_fail(args.report)
    try:
        key = KeyPair.from_pem(_read(args.key))
    except CryptoError as exc:
        raise CliError(str(exc)) from exc
    signatures: list[Signature] = []
    if args.envelope_in:
        existing = _read_json(args.envelope_in)
        if not isinstance(existing, dict) or existing.get("report_sha256") != report_digest(report):
            raise CliError("the existing envelope does not contain this report")
        signatures = [Signature(s["key_id"], s["sig"]) for s in existing["signatures"]]
    signatures.append(sign_report(report, key))
    Path(args.out).write_bytes(canonicalize(make_envelope(report, signatures)) + b"\n")
    print(f"signed by {key.public.key_id} ({len(signatures)} signature(s) in {args.out})")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    pinned = {k.key_id: k for k in (_load_pub(p) for p in args.key)}
    result = verify_envelope(_read_json(args.envelope), pinned, args.min_signatures)
    for problem in result.problems:
        print(f"FAIL  {problem}")
    for warning in result.warnings:
        print(f"WARN  {warning}")
    if result.ok:
        print(
            f"VERIFIED: {len(result.signers)} valid signature(s) from {', '.join(result.signers)}"
        )
    else:
        print("NOT VERIFIED")
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trs", description="Transparency report tools.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate a report (structure and consistency)")
    v.add_argument("report")
    v.set_defaults(func=_cmd_validate)

    s = sub.add_parser("summary", help="print the headline numbers")
    s.add_argument("report")
    s.set_defaults(func=_cmd_summary)

    c = sub.add_parser("check", help="check a report against a policy file")
    c.add_argument("report")
    c.add_argument("--policy", required=True)
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=_cmd_check)

    d = sub.add_parser("diff", help="compare two consecutive reports")
    d.add_argument("old")
    d.add_argument("new")
    d.add_argument("--notice-bps", type=int, default=1000)
    d.add_argument("--fail-on", choices=("none", "notice", "warning"), default="none")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=_cmd_diff)

    sc = sub.add_parser("schema", help="emit the JSON Schema")
    sc.add_argument("--out")
    sc.set_defaults(func=_cmd_schema)

    ca = sub.add_parser("canonical", help="print the SHA-256 of the canonical report")
    ca.add_argument("report")
    ca.add_argument("--print", action="store_true", help="also print the canonical JSON")
    ca.set_defaults(func=_cmd_canonical)

    kg = sub.add_parser("keygen", help="generate an Ed25519 signing key")
    kg.add_argument("--out", required=True)
    kg.add_argument("--pub-out")
    kg.add_argument("--force", action="store_true")
    kg.set_defaults(func=_cmd_keygen)

    sg = sub.add_parser(
        "sign", help="sign a report (adds to an existing envelope with --envelope-in)"
    )
    sg.add_argument("report")
    sg.add_argument("--key", required=True)
    sg.add_argument("--out", required=True)
    sg.add_argument("--envelope-in")
    sg.set_defaults(func=_cmd_sign)

    vf = sub.add_parser("verify", help="verify a signed envelope against trusted public keys")
    vf.add_argument("envelope")
    vf.add_argument("--key", action="append", required=True, help="public key file (repeatable)")
    vf.add_argument("--min-signatures", type=int, default=1)
    vf.set_defaults(func=_cmd_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: 0 ok, 1 a check failed, 2 usage or input error."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (CliError, CryptoError, CanonicalError, ValidationError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
