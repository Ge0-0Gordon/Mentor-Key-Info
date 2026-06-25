# Simple batch mode report

## Why batch mode was added

Simple single-record extraction is much lighter than full mode, but online calls
still have a fixed request/response overhead. Simple batch mode lets the local
service send several `MentorInput` records to the model in one prompt, then the
program validates and writes each mentor result independently.

This only changes simple mode. Full mode keeps the previous one-record request
path.

## Batch request sent to the local service

`batch_extract.py` still uses the OpenAI-compatible endpoint:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "<JSON string>"
    }
  ],
  "stream": false
}
```

For simple batch, `content` is:

```json
{
  "task": "extract_mentor_keywords_batch_simple",
  "records": [
    {
      "task": "extract_mentor_key_info",
      "input_schema_version": "1.0",
      "mentor_id": "service_mentor:1",
      "record_hash": "...",
      "source_file": "...",
      "source_sheet": "服务导师",
      "source_row": 2,
      "original_fields": {}
    }
  ]
}
```

The model itself is asked to output only:

```json
{
  "results": [
    {
      "mentor_id": "service_mentor:1",
      "extraction": {
        "industries": [],
        "companies": [],
        "roles": [],
        "skills": [],
        "credentials": [],
        "education": [],
        "target_mentees": [],
        "highlights": [],
        "keywords": [],
        "summary": null
      }
    }
  ]
}
```

The program then assembles each `SimpleMentorResult`.

## Service response

For a simple batch request, `main.py` returns this JSON string in
`choices[0].message.content`:

```json
{
  "schema_version": "simple-batch-v1",
  "results": [
    {
      "schema_version": "simple-v1",
      "prompt_version": "mentor-simple-v1",
      "mentor_id": "service_mentor:1",
      "record_hash": "...",
      "source": {},
      "original_fields": {},
      "extraction": {},
      "processing": {}
    }
  ]
}
```

Full mode does not support the batch request and rejects it clearly.

## `--batch-size`

`batch_extract.py` now accepts:

```powershell
--batch-size 10
```

Default: `10`.

Rules:

- applies only when `--mode simple`;
- `--batch-size 1` uses the existing single-record request path;
- `--batch-size > 1` groups pending, non-resumed records into simple batch
  requests;
- full mode keeps the original single-record behavior.

Example:

```powershell
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3 `
  --force `
  --mode simple `
  --batch-size 3 `
  --output-dir outputs/simple_batch_smoke_20260625_1100
```

Use timestamped output directories for online tests so runs are easy to compare.

## Fallback

If a simple batch request fails as a whole, including:

- HTTP error;
- invalid OpenAI-compatible response shape;
- empty or non-JSON content;
- invalid `simple-batch-v1` schema;
- missing, extra or duplicate `mentor_id`;
- mismatched `mentor_id + record_hash`;

then `batch_extract.py` falls back to single-record requests for that group.
Only records that still fail in the single-record fallback are written to
`failed_rows.jsonl`.

Each successful record is still appended immediately to
`checkpoints/success_rows.jsonl`.

## Resume

Resume remains per mentor:

- key: `mentor_id + record_hash`;
- checkpoint schema must match the current mode;
- already successful records are skipped before grouping;
- skipped records are not sent in a batch request;
- final `mentor_results.jsonl` remains one mentor per line.

## Recommended online rollout

1. Compare single simple mode:

```powershell
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3 `
  --force `
  --mode simple `
  --batch-size 1 `
  --output-dir outputs/simple_single_20260625_1100
```

2. Test batch size 3:

```powershell
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3 `
  --force `
  --mode simple `
  --batch-size 3 `
  --output-dir outputs/simple_batch3_20260625_1100
```

3. If quality is stable, test 5, then 10.

Do not jump straight to full 121 records until the batch output quality is
manually checked.

## Current limitations

- A batch response is accepted only if the returned `mentor_id` set exactly
  matches the requested records.
- Per-record partial success inside a malformed batch response is not trusted;
  the group falls back to single-record requests.
- Larger batch sizes may reduce latency but can also increase cross-record
  confusion risk. Keep spot-checking keywords and summaries.

## Recommendation

Default `--batch-size=10` is reasonable for simple full-dataset runs after
3/5/10-record smoke tests pass. If the model shows cross-record mixing or
quality drift, use `--batch-size 3` or `--batch-size 5`.
