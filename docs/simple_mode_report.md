# Simple extraction mode report

## Why simple mode was added

The full extraction mode is designed for auditable structured extraction. It asks
the model for nested objects, evidence, confidence, mapping status and
organization relationships, then performs deterministic evidence checks and
normalization. That is useful for review, but expensive for fast smoke tests and
large runs.

Simple mode is a lightweight keyword extraction path. It keeps the existing
Excel preprocessing, `mentor_id`, `record_hash`, checkpoint/resume,
`failed_rows.jsonl` and Excel export flow, but removes the heavy extraction
contract.

## Simple vs full

| Area | simple mode | full mode |
| --- | --- | --- |
| Server env | `EXTRACTION_MODE=simple` or unset | `EXTRACTION_MODE=full` |
| Model output | `SimpleMentorExtraction` only | `MentorExtraction` |
| Program result | `SimpleMentorResult` | `MentorResult` |
| Prompt | short rules + output template | full schema, taxonomy and guardrails |
| Evidence | not required | required and validated |
| Mapping | none | industry/company/skill normalization |
| Relationship | none | employer/client/project/partner/unknown |
| Review Excel | 3 sheets | 10 sheets |

## Simple result fields

`SimpleMentorExtraction` contains only flat keyword lists:

- `industries`
- `companies`
- `roles`
- `skills`
- `credentials`
- `education`
- `target_mentees`
- `highlights`
- `keywords`
- `summary`

All lists default to `[]`. `summary` may be `null`.

`SimpleMentorResult` wraps the extraction with:

- `schema_version = "simple-v1"`
- `prompt_version = "mentor-simple-v1"`
- `mentor_id`
- `record_hash`
- `source`
- `original_fields`
- `processing`

## Cleaning rules

Before Pydantic validation, `simple_extractor`:

- strips whitespace;
- removes empty strings;
- deduplicates each list;
- caps each list at 20 items;
- truncates keyword strings;
- truncates `summary`.

It does not run evidence matching, taxonomy mapping, company mapping, skill
normalization or relationship guardrails.

## Running the local service

The mode is read when `main.py` starts. Restart the service after changing it.

```powershell
conda activate tutor
$env:EXTRACTION_MODE="simple"
python main.py
```

For full mode:

```powershell
conda activate tutor
$env:EXTRACTION_MODE="full"
python main.py
```

If `EXTRACTION_MODE` is unset, the service defaults to `simple`.

## Running batch extraction

`batch_extract.py --mode` controls how the client parses checkpoint and response
schemas. It does not change the server; the server still uses
`EXTRACTION_MODE`.

Simple smoke:

```powershell
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3 `
  --force `
  --mode simple `
  --output-dir outputs/simple_smoke
```

Full smoke:

```powershell
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3 `
  --force `
  --mode full `
  --output-dir outputs/full_smoke
```

Use separate output directories for simple and full runs. A checkpoint line is
loaded only if it validates against the current mode schema. Mode mismatches are
warned and not used for resume.

## Review Excel

Simple mode writes:

1. `导师总览`
2. `关键词明细`
3. `处理失败`

Full mode keeps the existing 10-sheet review workbook.

## Benchmark helper

Structure-only request-size comparison:

```powershell
python scripts/benchmark_simple_vs_full.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3
```

If existing result JSONL files are available, pass them to include response
length and latency summaries:

```powershell
python scripts/benchmark_simple_vs_full.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3 `
  --simple-results-jsonl outputs/simple_smoke/mentor_results.jsonl `
  --full-results-jsonl outputs/full_smoke/mentor_results.jsonl
```

## Tests

Run:

```powershell
conda activate tutor
python -m pytest -q
```

The test suite covers fake simple extraction, cleaning, schema mismatch, simple
batch JSONL/export, and full/simple mode mismatch handling. Real model calls are
not part of pytest.

## Current limitations

- Simple mode is keyword-oriented and not evidence-auditable.
- It does not decide employer/client/project relationships.
- It does not normalize industries, companies or skills.
- It is best for fast candidate extraction, model comparison and first-pass
  full-dataset runs. Use full mode for final audit or difficult samples.

## Recommendation

Use simple mode as the default for speed. Keep full mode available for review,
quality audits and selected difficult records.
