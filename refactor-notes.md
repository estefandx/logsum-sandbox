## K 5.W.6 — Refactor notes

## Removed by AI in the refactor
- `exit_code = 0` from main() and the elif/else write block.
  AI reason: extracted to _write_summary() for clarity.
  My decision: keep removed — exit code is now the return value of
  _write_summary(), behaviour is identical, and tests confirm it.
