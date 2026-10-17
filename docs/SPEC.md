# Report format (`trs/1`)

All values are JSON strings, non-negative integers, booleans, objects and lists. There are no
floating-point numbers. Unknown fields are errors. The authoritative definition is the Pydantic
models in `src/transparency_report_schema/models.py`; the JSON Schema in `schema/` covers the
structural part only.

## Top level

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `"trs/1"` | |
| `report_id` | identifier | `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}` |
| `developer` | `{name, identifier}` | |
| `period` | `{start, end}` | `YYYY-MM-DD`; `end >= start` |
| `published_at` | timestamp | `YYYY-MM-DDTHH:MM:SSZ`; not before the period end |
| `models` | list (≥1) | see below |
| `specs` | list (≥1) | |
| `evaluations` | list | default empty |
| `incidents` | list | default empty |
| `compute` | object | |
| `qualitative_notes` | list | default empty |

## Sections

* **model**: `model_id`, `name`, `version`, `status` (`internal_only` / `limited_external` /
  `generally_available` / `retired`), `first_internal_use`, optional `first_external_availability`.
* **spec**: `spec_id`, `title`, `version`, `applies_to` (≥1 model ids), `effective_date`,
  `sha256` (hash of the spec document as published), optional `url` (https), `summary`.
* **evaluation**: `evaluation_id`, `model_id`, `spec_id`, `method` (`automated_eval` / `red_team` /
  `production_audit` / `human_review` / `other`), `description`, `n_trials` (≥1), `n_violations`,
  `severity_breakdown` (`low`/`medium`/`high`/`critical` → count), optional `notes`.
* **incident**: `incident_id`, `model_id`, `severity`, `summary`, `evidence` (list of
  `{kind, sha256, uri?}`, e.g. the hash of an evidence bundle).
* **compute**: `total_gpu_hours` (≥1) and a `breakdown` of `{category, gpu_hours}` with categories
  `pretraining`, `post_training`, `ai_rd_experiments`, `safety_research`, `external_inference`,
  `internal_inference_ai_rd`, `internal_inference_other`, `other`.
* **qualitative note**: `note_id`, `noted_on`, `topic`, `text`.

## Cross-field rules

1. `published_at` is not before the period end.
2. Ids are unique within their section (`model_id`, `spec_id`, `evaluation_id`, `incident_id`,
   `note_id`, compute `category`).
3. Model dates: first internal use and any external availability are not after the period end;
   external availability is not before internal use; `internal_only` has no external date;
   `limited_external` and `generally_available` require one.
4. Spec `effective_date` is not after the period end; `applies_to` names known models without
   duplicates; **every model is covered by at least one spec**.
5. Each evaluation names a known model and spec, the spec applies to that model,
   `n_violations <= n_trials`, and `severity_breakdown` sums to `n_violations`.
6. Each incident names a known model.
7. The compute breakdown sums exactly to `total_gpu_hours`.
8. Each note is dated within the reporting period.

## Derived quantities

* **Internal-to-external gap** (days): first external availability minus first internal use; for a
  model that is still `internal_only`, the days from first internal use to the period end;
  undefined for a retired model that never shipped.
* **Share** of a set of categories: exact `Fraction(hours, total)`; reported in basis points
  rounded half-up; cap comparisons use the exact value.
* **AI R&D share** (default grouping): `pretraining`, `post_training`, `ai_rd_experiments`,
  `internal_inference_ai_rd`. **Internal deployment share**: `internal_inference_ai_rd` +
  `internal_inference_other`.

## Signing

`signature = Ed25519(key, "TRS-REPORT-v1\0" || SHA-256(canonical report))`, where the canonical
report is RFC 8785-style canonical JSON of the normalised report (absent optional fields
omitted). A signed envelope is `{"report": ..., "report_sha256": ..., "signatures": [{"key_id",
"sig"}]}`; `key_id = "ed25519:" || first 32 hex characters of SHA-256(public key)`.
Verification trusts only the public keys the verifier supplies.
