"""Summarise events.csv by (level, service) and write summary.csv."""

import argparse
import csv
import sys
from datetime import datetime

OUTPUT_COLS = ["level", "service", "count", "first_seen", "last_seen"]


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _normalise(row: dict) -> tuple[str, str]:
    level = (row.get("level") or "").strip().upper() or "UNKNOWN"
    service = (row.get("service") or "").strip()
    return level, service


def _open_input(path):
    if path is None:
        return sys.stdin
    try:
        return open(path, newline="", encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def _open_output(path):
    if path is None:
        return sys.stdout
    try:
        return open(path, "w", newline="", encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def summarise(reader):
    """Return (warnings, groups, total_rows).

    groups maps (level, service) -> {count, first_seen, last_seen}.
    total_rows counts data rows (excludes the header).
    """
    groups: dict[tuple, dict] = {}
    warnings: list[str] = []
    total_rows = 0

    for row_num, row in enumerate(reader, start=2):
        total_rows += 1
        ts_raw = (row.get("timestamp") or "").strip()
        try:
            ts = _parse_ts(ts_raw)
        except (ValueError, TypeError):
            warnings.append(
                f"WARNING: row {row_num} — unparseable timestamp, skipped"
            )
            continue

        level, service = _normalise(row)
        key = (level, service)
        if key not in groups:
            groups[key] = {"count": 0, "first_seen": ts, "last_seen": ts}
        g = groups[key]
        g["count"] += 1
        g["first_seen"] = min(g["first_seen"], ts)
        g["last_seen"] = max(g["last_seen"], ts)

    return warnings, groups, total_rows


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="logsum",
        description="Summarise events.csv by (level, service).",
    )
    parser.add_argument(
        "input_pos", nargs="?", default=None, metavar="INPUT",
        help="Path to events.csv (default: stdin)",
    )
    parser.add_argument(
        "output_pos", nargs="?", default=None, metavar="OUTPUT",
        help="Path to summary.csv (default: stdout)",
    )
    parser.add_argument("-i", "--input", dest="input_named", metavar="PATH")
    parser.add_argument("-o", "--output", dest="output_named", metavar="PATH")

    args = parser.parse_args(argv)
    input_path = args.input_named or args.input_pos
    output_path = args.output_named or args.output_pos

    in_fh = _open_input(input_path)
    out_fh = _open_output(output_path)
    exit_code = 0
    try:
        reader = csv.DictReader(in_fh)
        warnings, groups, total_rows = summarise(reader)

        for w in warnings:
            print(w, file=sys.stderr)

        writer = csv.DictWriter(out_fh, fieldnames=OUTPUT_COLS)
        writer.writeheader()

        if total_rows == 0:
            print("NOTE: input was empty", file=sys.stderr)
        elif not groups:
            exit_code = 1
        else:
            for (level, service), g in sorted(groups.items()):
                writer.writerow({
                    "level": level,
                    "service": service,
                    "count": g["count"],
                    "first_seen": g["first_seen"].isoformat(),
                    "last_seen": g["last_seen"].isoformat(),
                })
    finally:
        if input_path:
            in_fh.close()
        if output_path:
            out_fh.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
