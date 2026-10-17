from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from conftest import EXAMPLES, ROOT, set_path

from transparency_report_schema import TransparencyReport, __version__
from transparency_report_schema.cli import main

Q3 = str(EXAMPLES / "example-report-2026-q3.json")
Q4 = str(EXAMPLES / "example-report-2026-q4.json")
POLICY = str(EXAMPLES / "example-policy.json")


class Cli:
    def __init__(self, tmp: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self.tmp, self.capsys = tmp, capsys

    def p(self, name: str) -> str:
        return str(self.tmp / name)

    def run(self, *argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        out = self.capsys.readouterr()
        return code, out.out, out.err


@pytest.fixture
def cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Cli:
    return Cli(tmp_path, capsys)


def test_version(cli: Cli) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0 and __version__ in cli.capsys.readouterr().out


def test_validate(cli: Cli, q3: dict[str, Any]) -> None:
    code, out, _ = cli.run("validate", Q3)
    assert code == 0 and out.startswith("VALID: exampleai-2026-q3 (2 model(s), 2 evaluation(s))")
    set_path(q3, "compute.total_gpu_hours", 5)
    Path(cli.p("bad.json")).write_text(json.dumps(q3))
    code, out, _ = cli.run("validate", cli.p("bad.json"))
    assert code == 1 and "INVALID" in out and "GPU-hours" in out
    # Structural problems are reported first; cross-field rules run once the structure is valid.
    set_path(q3, "evaluations.0.n_trials", 0)
    Path(cli.p("worse.json")).write_text(json.dumps(q3))
    code, out, _ = cli.run("validate", cli.p("worse.json"))
    assert code == 1 and "evaluations.0.n_trials" in out and "GPU-hours" not in out
    Path(cli.p("junk.json")).write_text("{")
    code, out, _ = cli.run("validate", cli.p("junk.json"))
    assert code == 1 and "(json)" in out
    code, _, err = cli.run("validate", cli.p("missing.json"))
    assert code == 2 and "cannot read" in err


def test_summary(cli: Cli) -> None:
    code, out, _ = cli.run("summary", Q3)
    assert code == 0
    assert "Compute (80,000,000 GPU-hours)" in out
    assert "AI R&D (total)" in out and "60.00%" in out
    assert "internal deployment" in out and "12.50%" in out
    assert "alpha-3-preview" in out and "56 days" in out and "69 days" in out
    assert "36/12000 violations (0.30%)" in out
    assert cli.run("summary", cli.p("nope.json"))[0] == 2


def test_summary_skips_categories_that_are_not_reported(cli: Cli, q3: dict[str, Any]) -> None:
    set_path(
        q3,
        "compute.breakdown",
        [
            {"category": "pretraining", "gpu_hours": 50_000_000},
            {"category": "external_inference", "gpu_hours": 20_000_000},
            {"category": "other", "gpu_hours": 10_000_000},
        ],
    )
    Path(cli.p("sparse.json")).write_text(json.dumps(q3))
    out = cli.run("summary", cli.p("sparse.json"))[1]
    assert "pretraining" in out and "62.50%" in out
    assert "safety_research" not in out and "post_training" not in out


def test_summary_marks_models_without_a_gap(cli: Cli, q3: dict[str, Any]) -> None:
    set_path(q3, "models.1.status", "retired")
    Path(cli.p("r.json")).write_text(json.dumps(q3))
    assert "gap: n/a" in cli.run("summary", cli.p("r.json"))[1]


def test_check_against_the_example_policy(cli: Cli) -> None:
    code, out, _ = cli.run("check", Q3, "--policy", POLICY)
    assert code == 1
    for expected in (
        "AI_RD_SHARE_EXCEEDS_CAP",
        "INTERNAL_EXTERNAL_GAP_EXCEEDS_CAP [alpha-2]",
        "EVALUATION_TOO_SMALL [eval-redteam-1]",
        "VIOLATION_RATE_ABOVE_THRESHOLD [eval-redteam-1]",
    ):
        assert expected in out
    code, out, _ = cli.run("check", Q3, "--policy", POLICY, "--json")
    assert code == 1 and {f["code"] for f in json.loads(out)} >= {"AI_RD_SHARE_EXCEEDS_CAP"}
    Path(cli.p("lenient.json")).write_text("{}")
    code, out, _ = cli.run("check", Q3, "--policy", cli.p("lenient.json"))
    assert code == 0 and "no policy violations" in out
    Path(cli.p("bad-policy.json")).write_text('{"max_ai_rd_share_bps": 99999}')
    code, _, err = cli.run("check", Q3, "--policy", cli.p("bad-policy.json"))
    assert code == 2 and "error" in err
    Path(cli.p("invalid.json")).write_text("{}")
    code, _, err = cli.run("check", cli.p("invalid.json"), "--policy", POLICY)
    assert code == 2 and "not a valid report" in err


def test_diff(cli: Cli) -> None:
    code, out, _ = cli.run("diff", Q3, Q4)
    assert code == 0
    assert "WARNING evaluation_removed [eval-redteam-1]" in out
    assert "NOTICE  spec_revised [alpha-spec]" in out
    assert cli.run("diff", Q3, Q4, "--fail-on", "warning")[0] == 1
    assert cli.run("diff", Q3, Q4, "--fail-on", "notice")[0] == 1
    code, out, _ = cli.run("diff", Q3, Q4, "--json")
    assert code == 0 and any(c["kind"] == "model_added" for c in json.loads(out))
    code, out, _ = cli.run("diff", Q3, Q3)
    assert "period_overlap" in out
    assert cli.run("diff", Q3, Q3, "--fail-on", "warning")[0] == 1


def test_diff_with_no_differences(cli: Cli, q3: dict[str, Any]) -> None:
    following = json.loads(json.dumps(q3))
    set_path(following, "period", {"start": "2026-10-01", "end": "2026-12-31"})
    set_path(following, "published_at", "2027-01-15T09:00:00Z")
    set_path(following, "qualitative_notes", [])
    Path(cli.p("next.json")).write_text(json.dumps(following))
    code, out, _ = cli.run("diff", Q3, cli.p("next.json"), "--fail-on", "notice")
    assert code == 0 and "no differences" in out


def test_schema_command(cli: Cli) -> None:
    code, out, _ = cli.run("schema")
    assert code == 0
    committed = (ROOT / "schema" / "transparency-report.schema.json").read_text()
    assert out == committed
    assert json.loads(out) == json.loads(json.dumps(TransparencyReport.model_json_schema()))
    cli.run("schema", "--out", cli.p("s.json"))
    assert Path(cli.p("s.json")).read_text() == committed


def test_canonical(cli: Cli) -> None:
    code, out, _ = cli.run("canonical", Q3)
    assert code == 0 and out.startswith("sha256 ") and len(out.split()[1]) == 64
    code, out2, _ = cli.run("canonical", Q3, "--print")
    assert out2.splitlines()[0].startswith('{"compute":') and out2.endswith(out)


def test_sign_and_verify_workflow(cli: Cli) -> None:
    for name in ("a", "b"):
        assert (
            cli.run(
                "keygen", "--out", cli.p(f"{name}.pem"), "--pub-out", cli.p(f"{name}.pub.json")
            )[0]
            == 0
        )
    assert stat.S_IMODE(os.stat(cli.p("a.pem")).st_mode) == 0o600
    assert "already exists" in cli.run("keygen", "--out", cli.p("a.pem"))[2]
    assert cli.run("keygen", "--out", cli.p("a.pem"), "--force")[0] == 0
    assert cli.run("keygen", "--out", cli.p("c.pem"))[0] == 0  # no public-key file requested
    # (a.pem was regenerated, so refresh its public key file)
    assert (
        cli.run("keygen", "--out", cli.p("a.pem"), "--pub-out", cli.p("a.pub.json"), "--force")[0]
        == 0
    )

    assert cli.run("sign", Q3, "--key", cli.p("a.pem"), "--out", cli.p("signed.json"))[0] == 0
    code, out, _ = cli.run("verify", cli.p("signed.json"), "--key", cli.p("a.pub.json"))
    assert code == 0 and "VERIFIED: 1 valid signature(s)" in out
    # a second party adds their signature to the same envelope
    code, out, _ = cli.run(
        "sign",
        Q3,
        "--key",
        cli.p("b.pem"),
        "--envelope-in",
        cli.p("signed.json"),
        "--out",
        cli.p("two.json"),
    )
    assert code == 0 and "2 signature(s)" in out
    keys = ["--key", cli.p("a.pub.json"), "--key", cli.p("b.pub.json")]
    assert cli.run("verify", cli.p("two.json"), *keys, "--min-signatures", "2")[0] == 0
    code, out, _ = cli.run("verify", cli.p("signed.json"), *keys, "--min-signatures", "2")
    assert code == 1 and "NOT VERIFIED" in out and "2 required" in out
    code, out, _ = cli.run("verify", cli.p("signed.json"), "--key", cli.p("b.pub.json"))
    assert code == 1 and "WARN" in out

    tampered = json.loads(Path(cli.p("signed.json")).read_text())
    tampered["report"]["developer"]["name"] = "Someone Else"
    Path(cli.p("tampered.json")).write_text(json.dumps(tampered))
    assert cli.run("verify", cli.p("tampered.json"), "--key", cli.p("a.pub.json"))[0] == 1


def test_sign_and_verify_errors(cli: Cli) -> None:
    cli.run("keygen", "--out", cli.p("k.pem"), "--pub-out", cli.p("k.pub.json"))
    cli.run("sign", Q3, "--key", cli.p("k.pem"), "--out", cli.p("s.json"))
    code, _, err = cli.run("sign", Q3, "--key", cli.p("missing.pem"), "--out", cli.p("x.json"))
    assert code == 2 and "cannot read" in err
    Path(cli.p("not-a-key.pem")).write_text("nope")
    code, _, err = cli.run("sign", Q3, "--key", cli.p("not-a-key.pem"), "--out", cli.p("x.json"))
    assert code == 2 and "cannot load private key" in err
    code, _, err = cli.run(
        "sign",
        Q4,
        "--key",
        cli.p("k.pem"),
        "--envelope-in",
        cli.p("s.json"),
        "--out",
        cli.p("x.json"),
    )
    assert code == 2 and "does not contain this report" in err
    Path(cli.p("list.json")).write_text("[1]")
    code, _, err = cli.run(
        "sign",
        Q3,
        "--key",
        cli.p("k.pem"),
        "--envelope-in",
        cli.p("list.json"),
        "--out",
        cli.p("x.json"),
    )
    assert code == 2
    code, _, err = cli.run("verify", cli.p("s.json"), "--key", cli.p("list.json"))
    assert code == 2 and "not a public key file" in err
    liar = {
        "key_id": "ed25519:" + "0" * 32,
        "public_key": json.loads(Path(cli.p("k.pub.json")).read_text())["public_key"],
    }
    Path(cli.p("liar.json")).write_text(json.dumps(liar))
    code, _, err = cli.run("verify", cli.p("s.json"), "--key", cli.p("liar.json"))
    assert code == 2 and "does not match" in err
    Path(cli.p("floaty.json")).write_text('{"a": 1.5}')
    code, _, err = cli.run("verify", cli.p("floaty.json"), "--key", cli.p("k.pub.json"))
    assert code == 2 and "floating" in err
