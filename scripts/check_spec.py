#!/usr/bin/env python3
"""Fails if the spec has open placeholders (TBD, TODO, ??) outside code blocks,
mentions an ADR that is missing or not accepted, has a malformed version line, or has a
"Version history" table with no row for the current version."""

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "spec" / "phase1-spec.md"
ADR_DIR = ROOT / "docs" / "adr"

PLACEHOLDER = re.compile(r"\bTBD\b|\bTODO\b|\?\?")
VERSION_LINE = re.compile(r"^Version (\d+\.\d+) · (\d{4}-\d{2}-\d{2}) · Owner: \S.*$")
HISTORY_HEADING = re.compile(r"^#+\s+Version history\s*$")


def prose_lines(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line outside fenced code blocks."""
    lines: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            lines.append((number, line))
    return lines


def adr_statuses(adr_dir: Path) -> dict[str, str]:
    """ADR id -> status, read from each ADR's "- Status:" line."""
    statuses: dict[str, str] = {}
    for path in adr_dir.glob("ADR-*.md"):
        if m := re.match(r"ADR-\d{3}", path.name):
            status = re.search(r"^- Status:[ \t]*(.*?)[ \t]*$", path.read_text(), flags=re.M)
            statuses[m.group(0)] = status.group(1) if status else ""
    return statuses


def check(text: str, adrs: dict[str, str]) -> list[str]:
    errors: list[str] = []
    lines = prose_lines(text)

    # 1. No open placeholders
    for number, line in lines:
        for found in PLACEHOLDER.findall(line):
            errors.append(f"line {number}: placeholder '{found}'")

    # 2. ADR references must exist and be accepted (inline code is an example, not a reference)
    for number, line in lines:
        for ref in sorted(set(re.findall(r"\bADR-\d{3}\b", re.sub(r"`[^`]*`", "", line)))):
            if ref not in adrs:
                errors.append(f"line {number}: references missing {ref}")
            elif adrs[ref] != "accepted":
                errors.append(f"line {number}: references {ref}, which is '{adrs[ref]}'")

    # 3. Exactly one well-formed version line
    version: str | None = None
    version_lines = [(n, line) for n, line in lines if re.match(r"Version\b", line)]
    if len(version_lines) != 1:
        errors.append(f"expected one line starting with 'Version', found {len(version_lines)}")
    for number, line in version_lines:
        m = VERSION_LINE.match(line)
        try:
            if m:
                date.fromisoformat(m.group(2))
        except ValueError:
            m = None
        if m is None:
            errors.append(
                f"line {number}: malformed version line, expected "
                "'Version <major>.<minor> · <YYYY-MM-DD> · Owner: <name>'"
            )
        else:
            version = m.group(1)

    # 4. Once there is a "Version history" table, it has a row for the current version
    start = next((i for i, (_, line) in enumerate(lines) if HISTORY_HEADING.match(line)), None)
    if start is not None and version is not None:
        rows: set[str] = set()
        for _, line in lines[start + 1 :]:
            if line.startswith("#"):
                break
            if line.startswith("|"):
                rows.add(line.split("|")[1].strip().removeprefix("v"))
        if version not in rows:
            errors.append(f"'Version history' has no row for the current version {version}")

    return errors


def main() -> int:
    spec = Path(sys.argv[1]) if len(sys.argv) > 1 else SPEC
    errors = check(spec.read_text(), adr_statuses(ADR_DIR))
    if errors:
        print(f"Spec check failed ({spec}):\n" + "\n".join(f"  - {e}" for e in errors))
        return 1
    print("Spec check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
