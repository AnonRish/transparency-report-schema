from __future__ import annotations

import copy
from typing import Any

import pytest
from conftest import report_of, set_path

from transparency_report_schema import (
    KeyPair,
    Signature,
    make_envelope,
    report_digest,
    sign_report,
    verify_envelope,
)
from transparency_report_schema.crypto import b64encode
from transparency_report_schema.signing import SIG_DOMAIN, canonical_bytes

KEY = KeyPair.from_seed(bytes([1]) * 32)
KEY2 = KeyPair.from_seed(bytes([2]) * 32)
PINNED = {KEY.public.key_id: KEY.public, KEY2.public.key_id: KEY2.public}


def signed(q3: dict[str, Any], *keys: KeyPair) -> dict[str, Any]:
    report = report_of(q3)
    return make_envelope(report, [sign_report(report, k) for k in keys])


def test_envelope_round_trip(q3: dict[str, Any]) -> None:
    envelope = signed(q3, KEY)
    result = verify_envelope(envelope, PINNED)
    assert result.ok and result.signers == (KEY.public.key_id,) and result.report is not None
    assert set(envelope) == {"report", "report_sha256", "signatures"}
    assert envelope["report_sha256"] == report_digest(report_of(q3))


def test_digest_ignores_key_order_and_explicit_nulls(q3: dict[str, Any]) -> None:
    base = report_digest(report_of(q3))
    reordered = dict(reversed(list(q3.items())))
    assert report_digest(report_of(reordered)) == base
    with_null = copy.deepcopy(q3)
    set_path(with_null, "models.1.first_external_availability", None)
    assert report_digest(report_of(with_null)) == base
    assert verify_envelope(
        {**signed(q3, KEY), "report": with_null}, PINNED
    ).ok  # the signature covers the normalised report, not the byte layout


def test_any_content_change_changes_the_digest(q3: dict[str, Any]) -> None:
    base = report_digest(report_of(q3))
    changed = copy.deepcopy(q3)
    set_path(changed, "developer.name", "ExampleAI Labs (FICTIONAL) ")
    assert report_digest(report_of(changed)) != base
    assert canonical_bytes(report_of(q3)).startswith(b'{"compute":')


def test_signature_uses_a_domain_separated_message(q3: dict[str, Any]) -> None:
    report = report_of(q3)
    digest = bytes.fromhex(report_digest(report))
    naked = Signature(KEY.public.key_id, b64encode(KEY.sign(digest)))
    envelope = make_envelope(report, [naked])
    assert not verify_envelope(envelope, PINNED).ok
    assert SIG_DOMAIN.endswith(b"\x00")


def test_threshold_duplicates_unpinned_and_invalid_signatures(q3: dict[str, Any]) -> None:
    both = signed(q3, KEY, KEY2)
    assert verify_envelope(both, PINNED, min_signatures=2).ok
    one = signed(q3, KEY)
    result = verify_envelope(one, PINNED, min_signatures=2)
    assert not result.ok and "1 valid signature(s); 2 required" in result.problems[0]
    dup = signed(q3, KEY, KEY)
    result = verify_envelope(dup, PINNED, min_signatures=2)
    assert not result.ok and any("duplicate" in w for w in result.warnings)
    stranger = KeyPair.from_seed(bytes([9]) * 32)
    unpinned = signed(q3, stranger)
    result = verify_envelope(unpinned, PINNED)
    assert not result.ok and any("unpinned" in w for w in result.warnings)
    # An invalid signature by a pinned key fails the envelope even if the threshold is met.
    bad = signed(q3, KEY, KEY2)
    bad["signatures"][1]["sig"] = b64encode(b"x" * 64)
    result = verify_envelope(bad, PINNED, min_signatures=1)
    assert not result.ok and any("invalid signature" in p for p in result.problems)
    bad["signatures"][1]["sig"] = "QR=="
    result = verify_envelope(bad, PINNED, min_signatures=1)
    assert not result.ok and any("canonical base64" in p for p in result.problems)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.pop("signatures"),
        lambda e: e.__setitem__("extra", 1),
        lambda e: e.__setitem__("report_sha256", "0" * 64),
        lambda e: e.__setitem__("signatures", "none"),
        lambda e: e.__setitem__("signatures", [1]),
        lambda e: e.__setitem__("signatures", [{"key_id": KEY.public.key_id}]),
        lambda e: e.__setitem__("signatures", [{"key_id": 5, "sig": "x"}]),
        lambda e: e["report"].__setitem__("schema_version", "trs/9"),
        lambda e: e["report"].pop("compute"),
    ],
)
def test_malformed_envelopes_fail_without_raising(q3: dict[str, Any], mutate: Any) -> None:
    envelope = signed(q3, KEY)
    mutate(envelope)
    assert not verify_envelope(envelope, PINNED).ok
    assert not verify_envelope([envelope], PINNED).ok
    assert not verify_envelope(None, PINNED).ok


def _leaf_paths(value: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _leaf_paths(v, (*prefix, k))]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _leaf_paths(v, (*prefix, i))]
    return [prefix]


def _mutated(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    return str(value) + "x"


def test_every_leaf_of_the_signed_report_is_protected(q3: dict[str, Any]) -> None:
    """Changing any single value either invalidates the report or breaks the signature."""
    envelope = signed(q3, KEY)
    paths = _leaf_paths(envelope["report"])
    assert len(paths) > 60
    for path in paths:
        tampered = copy.deepcopy(envelope)
        node = tampered["report"]
        for step in path[:-1]:
            node = node[step]
        node[path[-1]] = _mutated(node[path[-1]])
        result = verify_envelope(tampered, PINNED)
        assert not result.ok, f"change at {path} went undetected"


def test_removing_any_key_is_detected_unless_it_is_semantically_identical(
    q3: dict[str, Any],
) -> None:
    envelope = signed(q3, KEY)
    original = report_digest(report_of(q3))

    def dict_paths(value: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        found: list[tuple[Any, ...]] = []
        if isinstance(value, dict):
            for key, child in value.items():
                found.append((*prefix, key))
                found.extend(dict_paths(child, (*prefix, key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                found.extend(dict_paths(child, (*prefix, index)))
        return found

    for path in dict_paths(envelope["report"]):
        tampered = copy.deepcopy(envelope)
        node = tampered["report"]
        for step in path[:-1]:
            node = node[step]
        del node[path[-1]]
        result = verify_envelope(tampered, PINNED)
        assert not result.ok or (
            result.report is not None and report_digest(result.report) == original
        ), f"removal of {path} went undetected"


def test_signature_fields_cannot_be_altered(q3: dict[str, Any]) -> None:
    envelope = signed(q3, KEY)
    flipped = copy.deepcopy(envelope)
    sig = flipped["signatures"][0]["sig"]
    flipped["signatures"][0]["sig"] = ("A" if sig[0] != "A" else "B") + sig[1:]
    assert not verify_envelope(flipped, PINNED).ok
    swapped = copy.deepcopy(envelope)
    swapped["signatures"][0]["key_id"] = KEY2.public.key_id
    assert not verify_envelope(swapped, PINNED).ok
