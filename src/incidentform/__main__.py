"""Command line entry: python -m incidentform template|validate|render."""

from __future__ import annotations

import argparse
import json
import sys

from .report import TEMPLATE, load_record, render, validate


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 1 when the record has problems, 2 on a missing or unreadable file."""
    parser = argparse.ArgumentParser(prog="incidentform", description="Incident report form to PDF")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("template", help="print a blank incident record as JSON")
    check = sub.add_parser("validate", help="check a record for missing or inconsistent fields")
    check.add_argument("file")
    draw = sub.add_parser("render", help="write the PDF form for a record")
    draw.add_argument("file")
    draw.add_argument("--out", required=True, help="output PDF path")
    draw.add_argument("--force", action="store_true", help="render even when validation finds problems")
    args = parser.parse_args(argv)

    if args.command == "template":
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    try:
        record = load_record(args.file)
    except FileNotFoundError:
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    problems = validate(record)
    for problem in problems:
        print(f"problem: {problem}")
    if args.command == "validate":
        print("record is complete" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if problems and not args.force:
        print("not rendered; fix the problems or use --force")
        return 1
    data = render(record)
    with open(args.out, "wb") as handle:
        handle.write(data)
    print(f"wrote {args.out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
