# transparency-report-schema

A strict, machine-checkable format for the public **transparency reports** that the
[AI 2040 "Plan A" scenario](https://ai-2040.com/?choices=plan-a-root) proposes frontier AI
companies should publish — plus the tools to validate them, compare consecutive reports, check
them against limits a reviewer chooses, and sign them.

## Why

Plan A's list of incremental policies includes transparency: companies would publicly report
their **model specifications** (what goals and values they are trying to train in), information
on whether their models **follow those specifications and their instructions**, **internal usage
statistics** such as the fraction of compute spent on internal deployment, and **qualitative
impressions of internal use**. The same page notes that large developers spend roughly half
their compute on AI R&D, and lists limiting AI R&D budgets as another option.

A requirement like that only helps if reports are comparable, checkable and hard to quietly
rewrite. This package turns it into a concrete format:

- **Strict structure** (Pydantic v2 models + a committed JSON Schema for non-Python tools).
- **Cross-field consistency rules** that catch reports whose parts contradict each other
  (compute that does not add up, evaluations of models that do not exist, spec coverage gaps,
  impossible dates, …).
- **Exact arithmetic**: no floating point anywhere; shares are integer basis points.
- **Comparison**: what changed between consecutive reports, including things that quietly
  disappeared or were downgraded.
- **Policy checks**: evaluate a report against *parameters you choose* (this package takes no
  position on what the limits should be).
- **Signing**: Ed25519 signatures over a normalised canonical form, multi-signer.

This is a proposal for a *format*. It is independent of the scenario's authors, is not a legal
template, and the example data is entirely fictional.

## Install

```bash
pip install git+https://github.com/AnonRish/transparency-report-schema   # or: pip install -e .
trs --version
```

Python 3.10+. Runtime dependencies: `pydantic>=2.6`, `cryptography`.

## What a report contains

| Section | Plan A item | Key fields |
|---|---|---|
| `models` | what is deployed, and where | `status`, `first_internal_use`, `first_external_availability` (so the **internal-vs-external gap** is computed, not asserted) |
| `specs` | model specifications | `version`, `sha256` of the published document, `url`, `applies_to` models |
| `evaluations` | whether models follow their specs | `method`, `n_trials`, `n_violations`, `severity_breakdown` |
| `incidents` | notable failures | `severity`, `summary`, optional `evidence` references (hashes of evidence bundles) |
| `compute` | internal usage statistics | GPU-hours by category: pre-training, post-training, AI-R&D experiments, safety research, external inference, **internal inference** (AI R&D / other), other |
| `qualitative_notes` | qualitative impressions of internal use | dated, topic-tagged free text |

Field-by-field documentation and the rules are in [`docs/SPEC.md`](docs/SPEC.md); the JSON Schema
is [`schema/transparency-report.schema.json`](schema/transparency-report.schema.json).

## Quickstart

```text
$ trs validate examples/example-report-2026-q3.json
VALID: exampleai-2026-q3 (2 model(s), 2 evaluation(s))

$ trs summary examples/example-report-2026-q3.json
Report exampleai-2026-q3: ExampleAI Labs (FICTIONAL)
Period 2026-07-01 to 2026-09-30; published 2026-10-15T09:00:00Z

Compute (80,000,000 GPU-hours)
  pretraining                  25.00%
  post_training                 7.50%
  ai_rd_experiments            17.50%
  safety_research               5.00%
  external_inference           30.00%
  internal_inference_ai_rd     10.00%
  internal_inference_other      2.50%
  other                         2.50%
  AI R&D (total)               60.00%
  internal deployment          12.50%

Models (2)
  alpha-2                 generally_available   internal->external gap: 69 days
  alpha-3-preview         internal_only         internal->external gap: 56 days
...
```

**Policy check** against limits *you* supply (here an illustrative file, not a recommendation):

```text
$ trs check examples/example-report-2026-q3.json --policy examples/example-policy.json
VIOLATION AI_RD_SHARE_EXCEEDS_CAP [compute]: AI R&D share 60.00% exceeds the cap of 50.00%
VIOLATION INTERNAL_EXTERNAL_GAP_EXCEEDS_CAP [alpha-2]: internal-to-external gap of 69 days exceeds the cap of 60 days
VIOLATION EVALUATION_TOO_SMALL [eval-redteam-1]: 800 trials is below the minimum of 1000
VIOLATION VIOLATION_RATE_ABOVE_THRESHOLD [eval-redteam-1]: violation rate 1.50% exceeds 1.00%
```

Comparisons use exact integer arithmetic: a share is "over a cap" only if it is *strictly*
greater than the cap, with no rounding.

**Compare consecutive reports** — what changed, and what quietly vanished:

```text
$ trs diff examples/example-report-2026-q3.json examples/example-report-2026-q4.json
INFO    model_added [beta-1]: status internal_only
NOTICE  model_status_changed [alpha-3-preview]: internal_only -> limited_external
NOTICE  spec_revised [alpha-spec]: version 4 -> 5
...
INFO    compute_share_changed [internal_deployment_total]: 12.50% -> 20.00% (+7.50 points)
WARNING evaluation_removed [eval-redteam-1]: results are no longer reported although the model still is
```

`trs diff --fail-on warning` exits non-zero on warnings, for use in CI. Warnings are raised
for: models that vanish without being retired, retroactively revised dates, a spec whose
document hash changed *without a version bump* (or the reverse), evaluations dropped while
their model is still reported, incidents downgraded in severity, and gaps or overlaps between
reporting periods.

**Sign and verify** (several parties can sign the same report):

```bash
trs keygen --out lab.pem --pub-out lab.pub.json
trs sign examples/example-report-2026-q3.json --key lab.pem --out signed.json
trs verify signed.json --key lab.pub.json            # exit 0 only if every check passes
```

### Python

```python
from transparency_report_schema import validate_report_data, check_policy, Policy

report, problems = validate_report_data(data)   # data: parsed JSON
assert report is not None, [str(p) for p in problems]
print(check_policy(report, Policy(max_ai_rd_share_bps=5000)))
```

## Design decisions worth knowing

- **No floats.** Floating-point text is not canonical across languages, and a signed report
  must have exactly one encoding. Counts are integers; shares are basis points
  (1/100 of a percent); the parser rejects `1.5`, `NaN`, duplicate keys and out-of-range ints.
- **Strict types.** `"12000"`, `12000.0` and `true` are not integers; unknown fields are
  errors; dates are exactly `YYYY-MM-DD`, timestamps exactly `YYYY-MM-DDTHH:MM:SSZ`.
- **Structural errors first.** Cross-field rules run once the structure is valid, and then all
  violations are listed together.
- **Signatures cover the normalised report** (absent optional fields omitted, keys sorted),
  so two textual encodings of one report share a digest. The signed message is
  domain-separated (`"TRS-REPORT-v1\0" || SHA-256(canonical report)`).
- **Derived, not asserted:** the internal-to-external gap and every share are computed from
  dates and GPU-hours, so a report cannot contradict itself about them.
- **JSON Schema is structural only.** Rules such as "the breakdown sums to the total" cannot
  be expressed in JSON Schema; the Python validator is normative.

## How it is verified

[`docs/ASSURANCE.md`](docs/ASSURANCE.md) maps each claim to evidence;
[`docs/VERIFICATION_REPORT.md`](docs/VERIFICATION_REPORT.md) is the output of the last full run
(lint, strict type checking, tests with 100% line and branch coverage, wheel build, clean-venv
install and CLI smoke test, Python 3.10–3.13 matrix). Highlights: the committed JSON Schema is
checked against the models and used (via `jsonschema`) to validate the examples and to
cross-check structural rejections; every cross-field rule has a test that triggers it; every
leaf of a signed report is mutated and the change is detected; share arithmetic is checked
against exact `Fraction` references with Hypothesis. Reproduce with `scripts/verify.sh`.

## Limits

- A schema makes reports *comparable and checkable*; it cannot make them *honest*. Nothing here
  verifies that the numbers are true. Pair reports with audits, and use the `evidence`
  references to point at independently verifiable records.
- The category definitions (what counts as "AI R&D" or "internal deployment") are conventions
  chosen here; the policy file lets a reviewer substitute their own AI-R&D grouping.
- The fictional examples are for illustration only; the example policy limits are arbitrary.
- Research-grade software; no independent security audit.

## Development

```bash
python -m pip install -e ".[dev]"
scripts/verify.sh "trs --version"
python scripts/make_examples.py     # regenerate examples and the JSON Schema after model changes
```

## License

MIT — see [LICENSE](LICENSE).
