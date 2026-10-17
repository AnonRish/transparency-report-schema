from __future__ import annotations

from typing import Any

import pytest
from conftest import del_path, report_of, set_path
from pydantic import ValidationError

from transparency_report_schema import Policy, check_policy


def codes(report: Any, **limits: Any) -> list[tuple[str, str]]:
    policy = Policy(**limits)
    return [(f.code, f.subject) for f in check_policy(report, policy)]


def test_the_default_policy_only_requires_an_adherence_evaluation_per_model(
    q3: dict[str, Any],
) -> None:
    assert codes(report_of(q3)) == []
    del q3["evaluations"][1]  # drop the evaluation of alpha-3-preview
    assert codes(report_of(q3)) == [("MODEL_WITHOUT_ADHERENCE_EVALUATION", "alpha-3-preview")]


def test_ai_rd_share_cap_is_exact_at_the_boundary(q3: dict[str, Any]) -> None:
    report = report_of(q3)  # exactly 60.00%
    assert codes(report, max_ai_rd_share_bps=6000) == []
    assert codes(report, max_ai_rd_share_bps=5999) == [("AI_RD_SHARE_EXCEEDS_CAP", "compute")]
    only_pretraining = ["pretraining"]  # 25.00%
    assert codes(report, max_ai_rd_share_bps=2500, ai_rd_categories=only_pretraining) == []
    assert codes(report, max_ai_rd_share_bps=2499, ai_rd_categories=only_pretraining) != []


def test_internal_deployment_share_cap(q3: dict[str, Any]) -> None:
    report = report_of(q3)  # 12.50%
    assert codes(report, max_internal_deployment_share_bps=1250) == []
    assert codes(report, max_internal_deployment_share_bps=1249) == [
        ("INTERNAL_DEPLOYMENT_SHARE_EXCEEDS_CAP", "compute")
    ]


def test_internal_external_gap_cap_including_models_not_yet_released(q3: dict[str, Any]) -> None:
    report = report_of(q3)  # alpha-2: 69 days; alpha-3-preview: 56 days so far, still internal
    assert codes(report, max_internal_external_gap_days=69) == []
    assert codes(report, max_internal_external_gap_days=68) == [
        ("INTERNAL_EXTERNAL_GAP_EXCEEDS_CAP", "alpha-2")
    ]
    assert [s for _, s in codes(report, max_internal_external_gap_days=55)] == [
        "alpha-2",
        "alpha-3-preview",
    ]


def test_minimum_trials(q3: dict[str, Any]) -> None:
    report = report_of(q3)  # 12000 and 800 trials
    assert codes(report, min_trials_per_evaluation=800) == []
    assert codes(report, min_trials_per_evaluation=801) == [
        ("EVALUATION_TOO_SMALL", "eval-redteam-1")
    ]


def test_violation_rate_cap_is_exact(q3: dict[str, Any]) -> None:
    report = report_of(q3)  # 36/12000 = 30 bps; 12/800 = 150 bps
    assert codes(report, max_violation_rate_bps=150) == []
    assert codes(report, max_violation_rate_bps=149) == [
        ("VIOLATION_RATE_ABOVE_THRESHOLD", "eval-redteam-1")
    ]
    assert [s for _, s in codes(report, max_violation_rate_bps=29)] == [
        "eval-instr-1",
        "eval-redteam-1",
    ]


def test_retired_models_need_no_evaluation_and_the_check_can_be_disabled(
    q3: dict[str, Any],
) -> None:
    set_path(q3, "models.1.status", "retired")
    del_path(q3, "evaluations.1")
    assert codes(report_of(q3)) == []
    del q3["evaluations"]
    assert codes(report_of(q3)) == [("MODEL_WITHOUT_ADHERENCE_EVALUATION", "alpha-2")]
    assert codes(report_of(q3), require_adherence_evaluation_per_model=False) == []


def test_findings_carry_readable_messages(q3: dict[str, Any]) -> None:
    findings = check_policy(
        report_of(q3), Policy(max_ai_rd_share_bps=5000, max_violation_rate_bps=100)
    )
    messages = {f.code: f.message for f in findings}
    assert messages["AI_RD_SHARE_EXCEEDS_CAP"] == "AI R&D share 60.00% exceeds the cap of 50.00%"
    assert messages["VIOLATION_RATE_ABOVE_THRESHOLD"] == "violation rate 1.50% exceeds 1.00%"


@pytest.mark.parametrize(
    "bad",
    [
        {"max_ai_rd_share_bps": 10_001},
        {"max_ai_rd_share_bps": -1},
        {"max_ai_rd_share_bps": 1.5},
        {"ai_rd_categories": []},
        {"ai_rd_categories": ["mining"]},
        {"max_internal_external_gap_days": -1},
        {"unknown_limit": 1},
    ],
)
def test_invalid_policies_are_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Policy(**bad)
