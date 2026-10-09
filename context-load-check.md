# Context Load Check — K 5.W.1

Verified that the agent loads `CLAUDE.md` before touching the repo.

## CLAUDE.md summary (by section)

**Project context** — A tiny CLI that reads `events.csv`, aggregates event counts/durations, and prints a summary to stdout.

**Conventions** — Source in `src/`, tests in `tests/`, data in `data/`, entry point is `src/logsum.py`.

**Utilities to prefer** — Python 3.11 stdlib only (no third-party runtime deps), `ruff` for linting/formatting, `pytest` for tests.

**Escalation gates** — Three hard stops: confirm before adding dependencies, use only synthetic data, and don't overwrite `spec.md` after sign-off without asking.

## Result

K 5.W.1 — **done**. The workspace has rules that the agent loads before touching the repo.
