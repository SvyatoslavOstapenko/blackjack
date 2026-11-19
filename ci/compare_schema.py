import argparse
import difflib
import hashlib
import os
import re
from pathlib import Path


GUARD = re.compile(r"^\\(un)?restrict ([A-Za-z0-9]+)$")
HEADER = (
    "-- Dumped from database version ",
    "-- Dumped by pg_dump version ",
)
LEGACY_CHECKS = (
    "    CONSTRAINT ck_hands_owner CHECK ",
    "    CONSTRAINT ck_rounds_status CHECK ",
)
TEXT_ARRAY = re.compile(
    r"ARRAY\[(\('[a-z_]+'::character varying\)::text"
    r"(?:, \('[a-z_]+'::character varying\)::text)*)\]"
)


def normalize_legacy_checks(line):
    # Reloading a PostgreSQL 16 dump can move this cast across the array.
    # Keep the constraint expression and all its literal values in the comparison.
    if not line.startswith(LEGACY_CHECKS):
        return line
    return TEXT_ARRAY.sub(
        lambda match: "(ARRAY[" + ", ".join(
            f"'{value}'::character varying"
            for value in re.findall(r"'([a-z_]+)'", match[1])
        ) + "])::text[]",
        line,
    )


def normalize(path):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if lines[:3] != ["--", "-- PostgreSQL database dump", "--"]:
        raise ValueError(f"{path}: expected a plain PostgreSQL schema dump")
    markers = [GUARD.fullmatch(line) for line in lines]
    guards = [marker.groups() for marker in markers if marker]
    if guards and (
        len(guards) != 2 or guards[0][0] is not None
        or guards[1] != ("un", guards[0][1])
    ):
        raise ValueError(f"{path}: malformed pg_dump restrict guard")
    if guards:
        first = next(index for index, marker in enumerate(markers) if marker)
        last = len(markers) - 1 - next(
            index for index, marker in enumerate(reversed(markers)) if marker
        )
        if first != 4 or any(lines[last + 1:]):
            raise ValueError(f"{path}: unexpected psql guard placement")
    return [
        normalize_legacy_checks(line) + "\n"
        for line, marker in zip(lines, markers)
        if not marker and not line.startswith(HEADER)
    ]


def main():
    cli = argparse.ArgumentParser(description="Compare PostgreSQL schema-only dumps")
    cli.add_argument("expected", type=Path)
    cli.add_argument("actual", type=Path)
    args = cli.parse_args()
    try:
        expected, actual = normalize(args.expected), normalize(args.actual)
    except (OSError, ValueError) as error:
        cli.exit(2, f"{error}\n")
    for label, lines in (("expected", expected), ("actual", actual)):
        digest = hashlib.sha256("".join(lines).encode()).hexdigest()
        print(f"{label.upper()}_SCHEMA_SHA256={digest}")
    if expected == actual:
        print("SCHEMA_MATCH")
        return 0
    print("".join(difflib.unified_diff(
        expected, actual,
        fromfile=os.fspath(args.expected), tofile=os.fspath(args.actual),
    )), end="")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
