"""
Black-box tests for the logsum CLI, derived exclusively from spec.md.
src/logsum.py is never imported; every test drives the program as a subprocess.

Spec sections under test
  §1 / §3  Grouping and output metrics
  §2       Normalisation
  §4       Missing level → UNKNOWN
  §5       Malformed timestamp skipping + per-row stderr warnings
  §6       Empty input
  §7       CLI flags and exit codes
"""
import csv
import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PROJ_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def run(*args, stdin_text: str | None = None):
    """Invoke ``python -m src.logsum`` with extra *args* and return CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "src.logsum", *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJ_ROOT),
    )


def parse_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def write_input(tmp_path):
    """Factory: write *content* to *tmp_path/<name>* and return its Path."""
    def _factory(content: str, name: str = "events.csv") -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p
    return _factory


@pytest.fixture()
def out(tmp_path) -> Path:
    return tmp_path / "summary.csv"


# ---------------------------------------------------------------------------
# Inline CSV test data (mirrors tests/fixtures/)
# ---------------------------------------------------------------------------

BASIC = """\
timestamp,level,service,message
2026-01-01T10:00:00,ERROR,auth,Login failed
2026-01-01T10:05:00,ERROR,auth,Token expired
2026-01-01T11:00:00,INFO,api,Request received
"""

MULTI_TS = """\
timestamp,level,service,message
2026-01-01T08:00:00,INFO,api,Early request
2026-01-01T12:00:00,INFO,api,Late request
2026-01-01T09:00:00,ERROR,db,Crash
"""

NORMALISE_LEVEL = """\
timestamp,level,service,message
2026-01-01T10:00:00,error,auth,Login failed
2026-01-01T10:05:00, warn ,api,Something
"""

NORMALISE_SERVICE = """\
timestamp,level,service,message
2026-01-01T10:00:00,INFO, Auth ,Login ok
"""

MISSING_LEVEL = """\
timestamp,level,service,message
2026-01-01T10:00:00,,auth,Empty level
2026-01-01T10:05:00,   ,auth,Whitespace level
"""

MALFORMED_TS = """\
timestamp,level,service,message
not-a-timestamp,ERROR,auth,Bad row
2026-01-01T10:05:00,ERROR,auth,Good row
"""

ALL_MALFORMED = """\
timestamp,level,service,message
not-a-timestamp,ERROR,auth,Bad row one
also-bad,INFO,api,Bad row two
"""

EMPTY = "timestamp,level,service,message\n"


# ===========================================================================
# §1 / §3  Grouping and output metrics
# ===========================================================================

class TestGrouping:
    def test_same_key_collapses_to_one_output_row(self, write_input, out):
        p = write_input(BASIC)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        auth = [r for r in rows if r["level"] == "ERROR" and r["service"] == "auth"]
        assert len(auth) == 1

    def test_distinct_keys_produce_separate_rows(self, write_input, out):
        p = write_input(BASIC)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        keys = {(r["level"], r["service"]) for r in rows}
        assert ("ERROR", "auth") in keys
        assert ("INFO", "api") in keys

    def test_count_equals_number_of_input_rows_in_group(self, write_input, out):
        p = write_input(BASIC)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        auth = next(r for r in rows if r["level"] == "ERROR" and r["service"] == "auth")
        assert auth["count"] == "2"

    def test_single_row_group_has_count_one(self, write_input, out):
        p = write_input(BASIC)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        api = next(r for r in rows if r["service"] == "api")
        assert api["count"] == "1"

    def test_first_seen_is_earliest_timestamp_in_group(self, write_input, out):
        p = write_input(MULTI_TS)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        api = next(r for r in rows if r["service"] == "api")
        assert api["first_seen"] == "2026-01-01T08:00:00"

    def test_last_seen_is_latest_timestamp_in_group(self, write_input, out):
        p = write_input(MULTI_TS)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        api = next(r for r in rows if r["service"] == "api")
        assert api["last_seen"] == "2026-01-01T12:00:00"

    def test_single_row_group_has_equal_first_and_last_seen(self, write_input, out):
        p = write_input(MULTI_TS)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        db = next(r for r in rows if r["service"] == "db")
        assert db["first_seen"] == db["last_seen"] == "2026-01-01T09:00:00"

    def test_timestamp_stored_as_is_without_reformatting(self, write_input, out):
        csv_text = (
            "timestamp,level,service,message\n"
            "2026-06-15T09:30:00Z,INFO,api,With Z suffix\n"
        )
        p = write_input(csv_text)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        assert rows[0]["first_seen"] == "2026-06-15T09:30:00Z"

    def test_output_column_order(self, write_input, out):
        p = write_input(BASIC)
        run("-i", str(p), "-o", str(out))
        header = out.read_text().splitlines()[0]
        assert header == "level,service,count,first_seen,last_seen"

    def test_message_column_not_in_output(self, write_input, out):
        p = write_input(BASIC)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        assert "message" not in rows[0]


# ===========================================================================
# §2  Normalisation
# ===========================================================================

class TestNormalisation:
    def test_level_lowercase_uppercased(self, write_input, out):
        p = write_input(NORMALISE_LEVEL)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        levels = {r["level"] for r in rows}
        assert "error" not in levels
        assert "ERROR" in levels

    def test_level_leading_trailing_whitespace_stripped(self, write_input, out):
        p = write_input(NORMALISE_LEVEL)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        levels = {r["level"] for r in rows}
        # " warn " → "WARN" (stripped then uppercased)
        assert "WARN" in levels

    def test_service_whitespace_stripped(self, write_input, out):
        p = write_input(NORMALISE_SERVICE)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        services = {r["service"] for r in rows}
        assert " Auth " not in services
        assert "Auth" in services

    def test_service_case_preserved(self, write_input, out):
        p = write_input(NORMALISE_SERVICE)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        services = {r["service"] for r in rows}
        # Case must not be changed — neither lowercased nor uppercased
        assert "auth" not in services
        assert "AUTH" not in services
        assert "Auth" in services

    def test_different_case_levels_normalise_to_same_group(self, write_input, out):
        csv_text = (
            "timestamp,level,service,message\n"
            "2026-01-01T10:00:00,error,auth,a\n"
            "2026-01-01T10:05:00,ERROR,auth,b\n"
        )
        p = write_input(csv_text)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        auth_rows = [r for r in rows if r["service"] == "auth"]
        assert len(auth_rows) == 1
        assert auth_rows[0]["count"] == "2"

    def test_padded_service_names_normalise_to_same_group(self, write_input, out):
        csv_text = (
            "timestamp,level,service,message\n"
            "2026-01-01T10:00:00,INFO, auth ,a\n"
            "2026-01-01T10:05:00,INFO,auth,b\n"
        )
        p = write_input(csv_text)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        auth_rows = [r for r in rows if r["service"] == "auth"]
        assert len(auth_rows) == 1
        assert auth_rows[0]["count"] == "2"


# ===========================================================================
# §4  Missing level → UNKNOWN
# ===========================================================================

class TestMissingLevel:
    def test_empty_level_field_mapped_to_unknown(self, write_input, out):
        p = write_input(MISSING_LEVEL)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        levels = {r["level"] for r in rows}
        assert "UNKNOWN" in levels
        assert "" not in levels

    def test_whitespace_only_level_mapped_to_unknown(self, write_input, out):
        p = write_input(MISSING_LEVEL)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        unknown_rows = [r for r in rows if r["level"] == "UNKNOWN"]
        # Both rows (empty and whitespace-only) group under the same UNKNOWN key
        assert len(unknown_rows) == 1
        assert unknown_rows[0]["count"] == "2"

    def test_missing_level_row_is_not_silently_dropped(self, write_input, out):
        p = write_input(MISSING_LEVEL)
        result = run("-i", str(p), "-o", str(out))
        assert result.returncode == 0
        rows = parse_csv(out.read_text())
        # One UNKNOWN/auth group must appear
        assert any(r["level"] == "UNKNOWN" for r in rows)

    def test_unknown_level_participates_in_first_last_seen(self, write_input, out):
        p = write_input(MISSING_LEVEL)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        unknown = next(r for r in rows if r["level"] == "UNKNOWN")
        assert unknown["first_seen"] == "2026-01-01T10:00:00"
        assert unknown["last_seen"] == "2026-01-01T10:05:00"


# ===========================================================================
# §5  Malformed timestamp
# ===========================================================================

class TestMalformedTimestamp:
    def test_malformed_row_excluded_from_output(self, write_input, out):
        p = write_input(MALFORMED_TS)
        run("-i", str(p), "-o", str(out))
        rows = parse_csv(out.read_text())
        # Only the valid row contributes; count must be 1, not 2
        assert len(rows) == 1
        assert rows[0]["count"] == "1"

    def test_warning_written_to_stderr(self, write_input, out):
        p = write_input(MALFORMED_TS)
        result = run("-i", str(p), "-o", str(out))
        assert "WARNING" in result.stderr

    def test_warning_mentions_unparseable_timestamp_and_skipped(self, write_input, out):
        p = write_input(MALFORMED_TS)
        result = run("-i", str(p), "-o", str(out))
        assert "unparseable timestamp" in result.stderr
        assert "skipped" in result.stderr

    def test_warning_uses_spec_format_with_em_dash(self, write_input, out):
        # Spec format: WARNING: row <n> — unparseable timestamp, skipped
        p = write_input(MALFORMED_TS)
        result = run("-i", str(p), "-o", str(out))
        assert "—" in result.stderr  # em dash U+2014

    def test_warning_includes_row_number(self, write_input, out):
        p = write_input(MALFORMED_TS)
        result = run("-i", str(p), "-o", str(out))
        assert re.search(r"row\s+\d+", result.stderr) is not None

    def test_one_warning_per_skipped_row(self, write_input, out):
        p = write_input(ALL_MALFORMED)
        result = run("-i", str(p), "-o", str(out))
        assert result.stderr.count("WARNING") == 2

    def test_row_numbers_differ_between_warnings(self, write_input, out):
        p = write_input(ALL_MALFORMED)
        result = run("-i", str(p), "-o", str(out))
        numbers = re.findall(r"row\s+(\d+)", result.stderr)
        assert len(numbers) == 2
        assert numbers[0] != numbers[1]

    def test_valid_rows_alongside_malformed_exit_0(self, write_input, out):
        p = write_input(MALFORMED_TS)
        result = run("-i", str(p), "-o", str(out))
        assert result.returncode == 0

    def test_all_rows_malformed_exit_1(self, write_input, out):
        p = write_input(ALL_MALFORMED)
        result = run("-i", str(p), "-o", str(out))
        assert result.returncode == 1

    def test_all_rows_malformed_still_emits_warnings(self, write_input, out):
        p = write_input(ALL_MALFORMED)
        result = run("-i", str(p), "-o", str(out))
        assert "WARNING" in result.stderr


# ===========================================================================
# §6  Empty input
# ===========================================================================

class TestEmptyInput:
    def test_header_only_input_produces_header_only_output(self, write_input, out):
        p = write_input(EMPTY)
        run("-i", str(p), "-o", str(out))
        non_blank = [ln for ln in out.read_text().splitlines() if ln]
        assert len(non_blank) == 1
        assert non_blank[0] == "level,service,count,first_seen,last_seen"

    def test_empty_input_writes_note_to_stderr(self, write_input, out):
        p = write_input(EMPTY)
        result = run("-i", str(p), "-o", str(out))
        assert "NOTE" in result.stderr
        assert "empty" in result.stderr.lower()

    def test_empty_input_note_format(self, write_input, out):
        # Spec exact text: NOTE: input was empty
        p = write_input(EMPTY)
        result = run("-i", str(p), "-o", str(out))
        assert "NOTE: input was empty" in result.stderr

    def test_empty_input_exit_0(self, write_input, out):
        p = write_input(EMPTY)
        result = run("-i", str(p), "-o", str(out))
        assert result.returncode == 0

    def test_completely_empty_file_also_treated_as_empty(self, write_input, out):
        # The spec says "only a header row (or zero rows)"
        p = write_input("", name="events.csv")
        result = run("-i", str(p), "-o", str(out))
        assert result.returncode == 0


# ===========================================================================
# §7  CLI flags and exit codes
# ===========================================================================

class TestCLIFlags:
    def test_long_input_flag(self, write_input, out):
        p = write_input(BASIC)
        result = run("--input", str(p), "--output", str(out))
        assert result.returncode == 0
        assert out.exists()

    def test_short_input_flag(self, write_input, out):
        p = write_input(BASIC)
        result = run("-i", str(p), "-o", str(out))
        assert result.returncode == 0
        assert out.exists()

    def test_long_output_flag_writes_file_with_data(self, write_input, out):
        p = write_input(BASIC)
        run("--input", str(p), "--output", str(out))
        rows = parse_csv(out.read_text())
        assert len(rows) > 0

    def test_short_output_flag_writes_file(self, write_input, out):
        p = write_input(BASIC)
        run("-i", str(p), "-o", str(out))
        assert out.exists()

    def test_no_output_flag_writes_to_stdout(self, write_input):
        p = write_input(BASIC)
        result = run("-i", str(p))
        assert result.returncode == 0
        assert "level,service,count,first_seen,last_seen" in result.stdout

    def test_stdout_output_contains_data_rows(self, write_input):
        p = write_input(BASIC)
        result = run("-i", str(p))
        rows = parse_csv(result.stdout)
        assert len(rows) > 0

    def test_no_input_flag_reads_from_stdin(self, tmp_path, out):
        result = run("-o", str(out), stdin_text=BASIC)
        assert result.returncode == 0
        assert out.exists()
        rows = parse_csv(out.read_text())
        assert len(rows) > 0

    def test_unknown_flag_exit_2(self, write_input):
        p = write_input(BASIC)
        result = run("-i", str(p), "--unknown-flag")
        assert result.returncode == 2

    def test_nonexistent_input_file_exit_1(self, tmp_path, out):
        missing = tmp_path / "no_such_file.csv"
        result = run("-i", str(missing), "-o", str(out))
        assert result.returncode == 1

    def test_unwritable_output_path_exit_1(self, write_input, tmp_path):
        p = write_input(BASIC)
        deep_missing = tmp_path / "no_such_dir" / "summary.csv"
        result = run("-i", str(p), "-o", str(deep_missing))
        assert result.returncode == 1
