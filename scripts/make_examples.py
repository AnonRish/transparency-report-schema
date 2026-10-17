#!/usr/bin/env python3
"""Regenerate examples/*.json and schema/transparency-report.schema.json.

All example data is FICTIONAL: an invented developer, invented numbers, ".invalid" URLs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from transparency_report_schema import TransparencyReport, validate_report_data

ROOT = Path(__file__).resolve().parent.parent


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def q3() -> dict[str, Any]:
    return {
        "schema_version": "trs/1",
        "report_id": "exampleai-2026-q3",
        "developer": {"name": "ExampleAI Labs (FICTIONAL)", "identifier": "exampleai.invalid"},
        "period": {"start": "2026-07-01", "end": "2026-09-30"},
        "published_at": "2026-10-15T09:00:00Z",
        "models": [
            {
                "model_id": "alpha-2",
                "name": "Alpha",
                "version": "2.0",
                "status": "generally_available",
                "first_internal_use": "2026-02-10",
                "first_external_availability": "2026-04-20",
            },
            {
                "model_id": "alpha-3-preview",
                "name": "Alpha",
                "version": "3.0-preview",
                "status": "internal_only",
                "first_internal_use": "2026-08-05",
            },
        ],
        "specs": [
            {
                "spec_id": "alpha-spec",
                "title": "Alpha model specification",
                "version": "4",
                "applies_to": ["alpha-2", "alpha-3-preview"],
                "effective_date": "2026-06-15",
                "sha256": sha("alpha-spec text, version 4"),
                "url": "https://exampleai.invalid/specs/alpha-v4",
                "summary": "Goals, values and priorities the Alpha models are trained to follow.",
            }
        ],
        "evaluations": [
            {
                "evaluation_id": "eval-instr-1",
                "model_id": "alpha-2",
                "spec_id": "alpha-spec",
                "method": "automated_eval",
                "description": "Held-out instruction-following suite.",
                "n_trials": 12000,
                "n_violations": 36,
                "severity_breakdown": {"low": 30, "medium": 6},
            },
            {
                "evaluation_id": "eval-redteam-1",
                "model_id": "alpha-3-preview",
                "spec_id": "alpha-spec",
                "method": "red_team",
                "description": "Internal red-team of the preview model against the spec.",
                "n_trials": 800,
                "n_violations": 12,
                "severity_breakdown": {"medium": 8, "high": 4},
                "notes": "High-severity cases were reviewed individually.",
            },
        ],
        "incidents": [
            {
                "incident_id": "INC-2026-07",
                "model_id": "alpha-3-preview",
                "severity": "medium",
                "summary": "The preview model skipped a required logging step in an internal job.",
                "evidence": [
                    {
                        "kind": "ledger_bundle",
                        "sha256": sha("example evidence bundle INC-2026-07"),
                        "uri": "https://exampleai.invalid/incidents/INC-2026-07",
                    }
                ],
            }
        ],
        "compute": {
            "total_gpu_hours": 80_000_000,
            "breakdown": [
                {"category": "pretraining", "gpu_hours": 20_000_000},
                {"category": "post_training", "gpu_hours": 6_000_000},
                {"category": "ai_rd_experiments", "gpu_hours": 14_000_000},
                {"category": "safety_research", "gpu_hours": 4_000_000},
                {"category": "external_inference", "gpu_hours": 24_000_000},
                {"category": "internal_inference_ai_rd", "gpu_hours": 8_000_000},
                {"category": "internal_inference_other", "gpu_hours": 2_000_000},
                {"category": "other", "gpu_hours": 2_000_000},
            ],
        },
        "qualitative_notes": [
            {
                "note_id": "note-1",
                "noted_on": "2026-08-20",
                "topic": "ai_rd_automation",
                "text": "Internal agents now draft and launch most routine ablation experiments; "
                "researchers mostly review results rather than write the code.",
            },
            {
                "note_id": "note-2",
                "noted_on": "2026-09-12",
                "topic": "oversight",
                "text": "Human review of agent actions is concentrated on the small share of "
                "actions that touch production credentials.",
            },
        ],
    }


def q4() -> dict[str, Any]:
    report = q3()
    report["report_id"] = "exampleai-2026-q4"
    report["period"] = {"start": "2026-10-01", "end": "2026-12-31"}
    report["published_at"] = "2027-01-15T09:00:00Z"
    models = report["models"]
    models[1]["status"] = "limited_external"
    models[1]["first_external_availability"] = "2026-11-10"
    models.append(
        {
            "model_id": "beta-1",
            "name": "Beta",
            "version": "1.0",
            "status": "internal_only",
            "first_internal_use": "2026-12-01",
        }
    )
    spec = report["specs"][0]
    spec["version"] = "5"
    spec["sha256"] = sha("alpha-spec text, version 5")
    spec["effective_date"] = "2026-11-01"
    spec["applies_to"] = ["alpha-2", "alpha-3-preview", "beta-1"]
    report["evaluations"] = [
        {
            "evaluation_id": "eval-instr-1",
            "model_id": "alpha-2",
            "spec_id": "alpha-spec",
            "method": "automated_eval",
            "description": "Held-out instruction-following suite.",
            "n_trials": 12000,
            "n_violations": 60,
            "severity_breakdown": {"low": 48, "medium": 12},
        }
    ]
    report["incidents"] = []
    report["compute"] = {
        "total_gpu_hours": 100_000_000,
        "breakdown": [
            {"category": "pretraining", "gpu_hours": 22_000_000},
            {"category": "post_training", "gpu_hours": 9_000_000},
            {"category": "ai_rd_experiments", "gpu_hours": 17_000_000},
            {"category": "safety_research", "gpu_hours": 5_000_000},
            {"category": "external_inference", "gpu_hours": 25_000_000},
            {"category": "internal_inference_ai_rd", "gpu_hours": 15_000_000},
            {"category": "internal_inference_other", "gpu_hours": 5_000_000},
            {"category": "other", "gpu_hours": 2_000_000},
        ],
    }
    report["qualitative_notes"] = [
        {
            "note_id": "note-3",
            "noted_on": "2026-11-18",
            "topic": "ai_rd_automation",
            "text": "Internal agents now propose and run follow-up experiments without a human "
            "choosing the next step in most routine cases.",
        }
    ]
    return report


POLICY = {
    "max_ai_rd_share_bps": 5000,
    "max_internal_deployment_share_bps": 1500,
    "max_internal_external_gap_days": 60,
    "require_adherence_evaluation_per_model": True,
    "min_trials_per_evaluation": 1000,
    "max_violation_rate_bps": 100,
}


def dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main() -> None:
    (ROOT / "examples").mkdir(exist_ok=True)
    (ROOT / "schema").mkdir(exist_ok=True)
    for name, data in (
        ("example-report-2026-q3.json", q3()),
        ("example-report-2026-q4.json", q4()),
    ):
        report, problems = validate_report_data(data)
        assert report is not None, problems
        dump(ROOT / "examples" / name, data)
    dump(ROOT / "examples" / "example-policy.json", POLICY)
    dump(
        ROOT / "schema" / "transparency-report.schema.json", TransparencyReport.model_json_schema()
    )
    print("wrote examples and schema")


if __name__ == "__main__":
    main()
