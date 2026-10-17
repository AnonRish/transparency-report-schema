# Assurance case

| # | Claim | Evidence |
|---|---|---|
| 1 | Reports are validated strictly: unknown fields, wrong types (`"5"`, `5.0`, `true` as integers), non-canonical dates/timestamps/hex/URLs, out-of-range integers, empty required lists and unknown enum values are rejected with a path. | `tests/test_models.py` (45 invalid-value cases, required-field cases). |
| 2 | Every cross-field rule fires on a report that violates it, all violations are reported together, and valid reports have none. | `tests/test_consistency.py` (25 rules/cases). |
| 3 | The committed JSON Schema equals the one generated from the models, is itself a valid schema, accepts the examples, and agrees with the models on 18 structural rejections; the tests also pin the documented gap (cross-field rules are Python-only). | `tests/test_schema.py` (uses `jsonschema`, independent). |
| 4 | Share arithmetic is exact: half-up rounding at exact halves; cap comparisons are strict and unrounded; shares partition the total; results match `Fraction` references. | `tests/test_compute.py` (Hypothesis against `fractions.Fraction`, independent). |
| 5 | Policy checks fire exactly at their documented boundaries (cap vs cap+1) and can each be disabled. | `tests/test_policy.py`. |
| 6 | Comparison reports additions, removals, status/date revisions, spec changes (including hash change without a version bump), compute-share shifts, evaluation changes and incident downgrades, and flags period gaps and overlaps. | `tests/test_diff.py`. |
| 7 | Signing covers the normalised canonical report; the digest ignores key order and explicit nulls but changes with any content change; signatures are domain-separated; multi-signer thresholds, duplicate and unpinned signers, and malformed envelopes are handled without raising. | `tests/test_signing.py`. |
| 8 | Every value of a signed report is protected: mutating any one of its 78 leaves, or deleting any key, makes verification fail unless the result is semantically identical. | `test_every_leaf_of_the_signed_report_is_protected`, `test_removing_any_key_...`. |
| 9 | Canonical JSON and Ed25519 usage are standard-conformant (RFC 8785 key ordering; RFC 8032 test vector 1). | `tests/test_canonical.py`, `tests/test_crypto.py` (independent). |
| 10 | The CLI behaves as documented (exit codes, outputs, errors) and the package installs from a wheel into a clean virtualenv and runs. | `tests/test_cli.py`; `scripts/verify.sh`. |

## What this does *not* establish

- That any reported number is true, complete or honestly measured.
- That the category groupings or example limits are the right ones for any real policy.
- Security against key compromise; there has been no independent audit.

## Reproduce

```bash
python -m pip install -e ".[dev]"
scripts/verify.sh "trs --version"
```
