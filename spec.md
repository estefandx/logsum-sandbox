# logsum — CLI Specification

## Goal

Read `events.csv`, group rows by `(level, service)`, and write one aggregated
row per group to `summary.csv` with count, first_seen, and last_seen.

## Inputs

Input file: `events.csv` — comma-separated, UTF-8, with a header row.

| Column | Type | Constraints |
|---|---|---|
| `timestamp` | ISO 8601 string | Required; malformed rows are skipped with a stderr warning |
| `level` | string | Optional; blank is treated as `UNKNOWN` |
| `service` | string | Required; must be non-empty after whitespace strip |
| `message` | string | Optional; not used in output |

## 1. Group key

Output rows are grouped by the composite key `(level, service)`.  
`timestamp` and `message` are not part of the key.

## 2. Normalisation rules

| Field | Rule |
|---|---|
| `level` | Strip leading/trailing whitespace, then uppercase. `"error"` → `"ERROR"` |
| `service` | Strip leading/trailing whitespace only. Case is preserved. `" auth "` → `"auth"` |
| `timestamp` | Must be ISO 8601. Stored as-is; no reformatting applied. |
| `message` | Not used in output. |

## 3. Output metrics

Each output row carries three metrics:

| Column | Type | Meaning |
|---|---|---|
| `count` | integer | Number of input rows in the group |
| `first_seen` | ISO 8601 string | Earliest timestamp in the group |
| `last_seen` | ISO 8601 string | Latest timestamp in the group |

Output column order: `level, service, count, first_seen, last_seen`.

## 4. Missing level behaviour

A row with an empty or whitespace-only `level` field is counted under the
literal value `UNKNOWN`. No row is silently dropped due to a missing level.

## 5. Malformed timestamp behaviour

A row whose `timestamp` cannot be parsed as ISO 8601 is **skipped**.  
One warning line is written to stderr per skipped row:

```
WARNING: row <n> — unparseable timestamp, skipped
```

If at least one valid row exists the exit code is still `0`.  
If every row is skipped due to malformed timestamps, exit code is `1`.

## 6. Empty input behaviour

An input file that contains only a header row (or zero rows) produces a
`summary.csv` with the header line only and no data rows.  
One note is written to stderr:

```
NOTE: input was empty
```

Exit code is `0`.

## 7. CLI flags and exit codes

### Flags

| Flag | Short | Default | Description |
|---|---|---|---|
| `--input PATH` | `-i` | stdin | Path to the input `events.csv` |
| `--output PATH` | `-o` | stdout | Path to the output `summary.csv` |
| `--min-count N` | `-n` | *(unset)* | Omit groups whose count is below N |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (including empty-input case) |
| `1` | I/O or data error — unreadable input, unwritable output, or all rows skipped |
| `2` | Bad arguments — unknown flag, missing required value |

When `--min-count` filters all groups to empty, the output is header-only and exit is `0` (intentional filter, not an error).

## 8. Out of scope

The following are explicitly **not** implemented:

- Filtering by level or severity threshold
- Filtering by time range
- Streaming / tail mode
- Multi-file or glob input
- JSON, Markdown, or any non-CSV output format
- Deduplication on message content
- Log rotation handling
- Message text analysis or pattern matching

## Signed off

CC — 2026-10-09

## Implementation notes

`src/__init__.py` was added by the agent — required for `python -m src.logsum`
but not mentioned in the spec. Output rows are sorted alphabetically by
`(level, service)`; sort order is not specified in the spec.
