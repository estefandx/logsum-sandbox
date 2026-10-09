# logsum-sandbox

## Project context
Tiny CLI that summarises synthetic `events.csv` logs. Reads CSV, aggregates
event counts/durations, and prints a human-readable summary to stdout.

## Conventions
- Source code: `src/`
- Tests: `tests/`
- Data files: `data/`
- Entry point: `src/logsum.py`

## Utilities to prefer
- Python 3.11 standard library (no third-party runtime deps)
- `ruff` for linting and formatting
- `pytest` for all tests

## Escalation gates
- **Stop before adding dependencies** — confirm with the user first.
- **Synthetic data only** — never use or reference real log data.
- **spec.md is frozen after sign-off** — do not overwrite it without asking.
