"""Deterministic JSON for hashing and signing.

The encoding follows the structure of RFC 8785 (JSON Canonicalization Scheme) for the
subset of JSON this project uses: objects with string keys sorted by UTF-16 code unit,
no insignificant whitespace, minimal string escaping, UTF-8 output.

**Floating-point numbers are rejected.** Their canonical text form is a classic source of
cross-implementation disagreement, and a signature scheme must not depend on it. Store
quantities as integers (for example basis points) or strings. Integers must lie within
the I-JSON safe range of +/- (2**53 - 1) so every implementation reads them identically.
"""

from __future__ import annotations

import json
from typing import Any

MAX_SAFE_INT = 2**53 - 1

_ESCAPES = {
    0x22: '\\"',
    0x5C: "\\\\",
    0x08: "\\b",
    0x0C: "\\f",
    0x0A: "\\n",
    0x0D: "\\r",
    0x09: "\\t",
}


class CanonicalError(ValueError):
    """The value cannot be represented in canonical form."""


def _escape(text: str) -> str:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanonicalError("strings must be valid Unicode (no lone surrogates)") from exc
    parts = ['"']
    for char in text:
        code = ord(char)
        if code in _ESCAPES:
            parts.append(_ESCAPES[code])
        elif code < 0x20:
            parts.append(f"\\u{code:04x}")
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def _emit(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif isinstance(value, bool):
        out.append("true" if value else "false")
    elif isinstance(value, int):
        if abs(value) > MAX_SAFE_INT:
            raise CanonicalError(f"integer {value} is outside the interoperable range")
        out.append(str(value))
    elif isinstance(value, float):
        raise CanonicalError("floating-point numbers are not allowed; use integers or strings")
    elif isinstance(value, str):
        out.append(_escape(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _emit(item, out)
        out.append("]")
    elif isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalError(f"object keys must be strings, got {type(key).__name__}")
        out.append("{")
        for index, key in enumerate(sorted(value, key=_utf16_key)):
            if index:
                out.append(",")
            out.append(_escape(key))
            out.append(":")
            _emit(value[key], out)
        out.append("}")
    else:
        raise CanonicalError(f"unsupported type {type(value).__name__}")


def _utf16_key(key: str) -> bytes:
    try:
        return key.encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise CanonicalError("keys must be valid Unicode (no lone surrogates)") from exc


def canonicalize(value: Any) -> bytes:
    """Return the canonical UTF-8 encoding of ``value``."""
    out: list[str] = []
    try:
        _emit(value, out)
    except RecursionError as exc:
        raise CanonicalError("value is nested too deeply") from exc
    return "".join(out).encode("utf-8")


def _reject_float(text: str) -> Any:
    raise CanonicalError(f"floating-point number {text!r} is not allowed")


def _reject_constant(text: str) -> Any:
    raise CanonicalError(f"{text} is not allowed")


def _parse_int(text: str) -> int:
    value = int(text)
    if abs(value) > MAX_SAFE_INT:
        raise CanonicalError(f"integer {text} is outside the interoperable range")
    return value


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def loads_strict(data: str | bytes) -> Any:
    """Parse JSON, rejecting floats, NaN/Infinity, duplicate keys and non-UTF-8 input."""
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CanonicalError("input is not valid UTF-8") from exc
    try:
        return json.loads(
            data,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_constant,
            object_pairs_hook=_no_duplicates,
        )
    except json.JSONDecodeError as exc:
        raise CanonicalError(f"invalid JSON: {exc}") from exc
    except RecursionError as exc:
        raise CanonicalError("JSON is nested too deeply") from exc
