from __future__ import annotations

from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from transparency_report_schema import (
    AI_RD_CATEGORIES,
    INTERNAL_DEPLOYMENT_CATEGORIES,
    Compute,
    ComputeAllocation,
    exceeds_bps,
    format_bps,
    share,
    share_bps,
)
from transparency_report_schema.compute import category_hours, hours_in
from transparency_report_schema.types import CATEGORIES


def make(hours: dict[str, int]) -> Compute:
    return Compute(
        total_gpu_hours=sum(hours.values()),
        breakdown=[ComputeAllocation(category=c, gpu_hours=h) for c, h in hours.items()],  # type: ignore[arg-type]
    )


def test_shares_of_a_simple_breakdown() -> None:
    c = make({"pretraining": 25, "post_training": 25, "external_inference": 50})
    assert share(c, ["pretraining"]) == Fraction(1, 4)
    assert share_bps(c, ["pretraining"]) == 2500
    assert share_bps(c, ["pretraining", "post_training"]) == 5000
    assert share_bps(c, ["safety_research"]) == 0  # absent categories count as zero
    assert share_bps(c, list(CATEGORIES)) == 10_000


def test_rounding_is_half_up_in_exact_integer_arithmetic() -> None:
    # 1/3 of the compute: 3333.33.. bps -> 3333; 2/3: 6666.67 -> 6667
    c = make({"pretraining": 1, "other": 2})
    assert share_bps(c, ["pretraining"]) == 3333
    assert share_bps(c, ["other"]) == 6667
    # exact halves: 0.5 bps -> 1, 1.5 bps -> 2, 2.5 bps -> 3
    big = make({"pretraining": 1, "post_training": 3, "ai_rd_experiments": 5, "other": 19_991})
    assert share_bps(big, ["pretraining"]) == 1
    assert share_bps(big, ["post_training"]) == 2
    assert share_bps(big, ["ai_rd_experiments"]) == 3


def test_duplicate_and_unknown_categories_are_counted_once_or_ignored() -> None:
    c = make({"pretraining": 40, "other": 60})
    assert hours_in(c, ["pretraining", "pretraining"]) == 40
    assert hours_in(c, ["no-such-category"]) == 0
    assert category_hours(c) == {"pretraining": 40, "other": 60}


def test_ai_rd_and_internal_deployment_groupings() -> None:
    assert set(AI_RD_CATEGORIES) == {
        "pretraining",
        "post_training",
        "ai_rd_experiments",
        "internal_inference_ai_rd",
    }
    assert set(INTERNAL_DEPLOYMENT_CATEGORIES) == {
        "internal_inference_ai_rd",
        "internal_inference_other",
    }


@pytest.mark.parametrize(
    "bps,text", [(0, "0.00%"), (5, "0.05%"), (100, "1.00%"), (1234, "12.34%"), (10_000, "100.00%")]
)
def test_format_bps(bps: int, text: str) -> None:
    assert format_bps(bps) == text


def test_exceeds_is_exact_at_the_boundary_and_never_rounds() -> None:
    c = make({"pretraining": 30, "other": 70})
    assert not exceeds_bps(c, ["pretraining"], 3000)  # exactly at the cap
    assert exceeds_bps(c, ["pretraining"], 2999)
    # 1/3 is 3333.33 bps, which *rounds* to 3333 but strictly exceeds a 3333 cap
    third = make({"pretraining": 1, "other": 2})
    assert share_bps(third, ["pretraining"]) == 3333
    assert exceeds_bps(third, ["pretraining"], 3333)
    assert not exceeds_bps(third, ["pretraining"], 3334)


hours_strategy = st.dictionaries(
    st.sampled_from(CATEGORIES), st.integers(0, 10**9), min_size=1
).filter(lambda d: sum(d.values()) > 0)


@given(hours_strategy)
def test_exact_shares_partition_the_total(hours: dict[str, int]) -> None:
    c = make(hours)
    assert sum(share(c, [cat]) for cat in hours) == 1
    total_bps = sum(share_bps(c, [cat]) for cat in hours)
    assert abs(total_bps - 10_000) <= len(hours)  # each share is within half a basis point


@given(hours_strategy, st.integers(0, 10_000))
def test_exceeds_matches_a_fraction_reference(hours: dict[str, int], cap: int) -> None:
    c = make(hours)
    chosen = sorted(hours)[: max(1, len(hours) // 2)]
    assert exceeds_bps(c, chosen, cap) == (share(c, chosen) * 10_000 > cap)


@given(hours_strategy)
def test_share_bps_is_the_rounded_exact_share(hours: dict[str, int]) -> None:
    c = make(hours)
    for cat in hours:
        exact = share(c, [cat]) * 10_000
        assert abs(share_bps(c, [cat]) - exact) <= Fraction(1, 2)
