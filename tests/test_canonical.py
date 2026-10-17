from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from transparency_report_schema.canonical import (
    MAX_SAFE_INT,
    CanonicalError,
    canonicalize,
    loads_strict,
)

json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-MAX_SAFE_INT, max_value=MAX_SAFE_INT)
    | st.text(alphabet=st.characters(blacklist_categories=("Cs",))),
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(
            st.text(alphabet=st.characters(blacklist_categories=("Cs",))), children, max_size=4
        )
    ),
    max_leaves=12,
)


def test_golden_bytes() -> None:
    value = {"b": [1, -2, True, None], "a": "x", "c": {"z": 0, "y": ""}}
    assert canonicalize(value) == b'{"a":"x","b":[1,-2,true,null],"c":{"y":"","z":0}}'


def test_keys_sort_by_utf16_code_unit_not_code_point() -> None:
    keys = ["\r", "1", "\u0080", "\u00f6", "\u20ac", "\U0001f600", "\ufb33"]
    ordered = list(json.loads(canonicalize(dict.fromkeys(reversed(keys), 0))))
    # The emoji (surrogates D83D DE00) sorts before U+FB33 in UTF-16 order, although its
    # code point is larger. This is the case that distinguishes RFC 8785 from naive sorting.
    assert ordered == keys
    assert "\U0001f600" > "\ufb33"  # code-point order would put them the other way round


def test_string_escaping() -> None:
    assert canonicalize('q"\\') == b'"q\\"\\\\"'
    assert canonicalize("\b\f\n\r\t") == b'"\\b\\f\\n\\r\\t"'
    assert canonicalize("\x00\x1f") == b'"\\u0000\\u001f"'
    assert canonicalize("\x7f\u00e9\u20ac\U0001f600") == '"\x7f\u00e9\u20ac\U0001f600"'.encode()


def test_booleans_are_not_integers_and_tuples_are_lists() -> None:
    assert canonicalize([True, False, 1, 0]) == b"[true,false,1,0]"
    assert canonicalize((1, 2)) == b"[1,2]"


@pytest.mark.parametrize(
    "value",
    [
        1.5,
        float("nan"),
        float("inf"),
        MAX_SAFE_INT + 1,
        -MAX_SAFE_INT - 1,
        {1: "int key"},
        "lone \ud800 surrogate",
        {"lone \ud800": 1},
        b"bytes",
        {1, 2},
    ],
)
def test_unrepresentable_values_are_rejected(value: Any) -> None:
    with pytest.raises(CanonicalError):
        canonicalize(value)


def test_extreme_safe_integers_are_accepted() -> None:
    assert canonicalize([MAX_SAFE_INT, -MAX_SAFE_INT]) == b"[9007199254740991,-9007199254740991]"


def test_excessive_nesting_is_an_error_not_a_crash() -> None:
    value: Any = []
    for _ in range(100_000):
        value = [value]
    with pytest.raises(CanonicalError, match="nested"):
        canonicalize(value)


@given(json_values)
def test_round_trip_and_idempotence(value: Any) -> None:
    encoded = canonicalize(value)
    assert loads_strict(encoded) == value
    assert canonicalize(loads_strict(encoded)) == encoded


@given(json_values)
def test_canonical_form_is_independent_of_key_insertion_order(value: Any) -> None:
    def reverse(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: reverse(v[k]) for k in reversed(list(v))}
        if isinstance(v, list):
            return [reverse(x) for x in v]
        return v

    assert canonicalize(reverse(value)) == canonicalize(value)


@pytest.mark.parametrize(
    "text",
    [
        "1.5",
        "1e3",
        "[1.0]",
        "NaN",
        "Infinity",
        "-Infinity",
        '{"a":1,"a":2}',
        "9007199254740992",
        "{",
        "",
    ],
)
def test_strict_parser_rejects(text: str) -> None:
    with pytest.raises(CanonicalError):
        loads_strict(text)


def test_strict_parser_handles_bytes_and_encoding() -> None:
    assert loads_strict(b'{"a":[1,"\xc3\xa9"]}') == {"a": [1, "é"]}
    with pytest.raises(CanonicalError, match="UTF-8"):
        loads_strict(b"\xff\xfe")
    with pytest.raises(CanonicalError):
        loads_strict(b'\xef\xbb\xbf{"a":1}')  # a BOM is not valid JSON


def test_strict_parser_rejects_pathological_nesting() -> None:
    with pytest.raises(CanonicalError, match="deeply"):
        loads_strict("[" * 200_000 + "]" * 200_000)
