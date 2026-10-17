"""Compute-share arithmetic in exact integers (basis points; 10,000 bps = 100%)."""

from __future__ import annotations

from collections.abc import Iterable
from fractions import Fraction

from .models import Compute

AI_RD_CATEGORIES: tuple[str, ...] = (
    "pretraining",
    "post_training",
    "ai_rd_experiments",
    "internal_inference_ai_rd",
)
INTERNAL_DEPLOYMENT_CATEGORIES: tuple[str, ...] = (
    "internal_inference_ai_rd",
    "internal_inference_other",
)


def category_hours(compute: Compute) -> dict[str, int]:
    """GPU-hours per category (categories absent from the breakdown count as 0)."""
    return {a.category: a.gpu_hours for a in compute.breakdown}


def hours_in(compute: Compute, categories: Iterable[str]) -> int:
    """Total GPU-hours across ``categories``."""
    hours = category_hours(compute)
    return sum(hours.get(c, 0) for c in set(categories))


def share(compute: Compute, categories: Iterable[str]) -> Fraction:
    """Exact fraction of total compute spent in ``categories``."""
    return Fraction(hours_in(compute, categories), compute.total_gpu_hours)


def share_bps(compute: Compute, categories: Iterable[str]) -> int:
    """Share in basis points, rounded half up (exact integer arithmetic)."""
    numerator = hours_in(compute, categories)
    return (20_000 * numerator + compute.total_gpu_hours) // (2 * compute.total_gpu_hours)


def exceeds_bps(compute: Compute, categories: Iterable[str], cap_bps: int) -> bool:
    """True iff the *exact* share is strictly greater than ``cap_bps`` (no rounding)."""
    return hours_in(compute, categories) * 10_000 > cap_bps * compute.total_gpu_hours


def format_bps(bps: int) -> str:
    """``1234`` -> ``'12.34%'``."""
    return f"{bps // 100}.{bps % 100:02d}%"
