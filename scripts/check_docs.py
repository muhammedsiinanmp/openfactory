#!/usr/bin/env python3
"""Fails if docs reference missing ADRs, have broken relative links,
or task records lack required sections."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
errors: list[str] = []

md_files = [p for p in ROOT.rglob("*.md") if ".venv" not in p.parts and ".git" not in p.parts]

def prose(path: Path) -> str:
    """File text with fenced code blocks and inline code removed."""
    text = re.sub(r"```.*?```", "", path.read_text(), flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)

# 1. ADR references must exist (code blocks and inline code are examples, not references)
existing_adrs = {m.group(0) for p in (DOCS / "adr").glob("ADR-*.md")
                 if (m := re.match(r"ADR-\d{3}", p.name))}
for f in md_files:
    if "template" in f.name:
        continue
    for ref in set(re.findall(r"\bADR-\d{3}\b", prose(f))):
        if ref != "ADR-000" and ref not in existing_adrs:
            errors.append(f"{f.relative_to(ROOT)}: references missing {ref}")

# 2. Relative links must resolve
for f in md_files:
    for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", prose(f)):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not (f.parent / target).resolve().exists():
            errors.append(f"{f.relative_to(ROOT)}: broken link -> {target}")

# 3. Task records must have required sections
required = ["## Objective", "## Acceptance criteria", "## Plan", "## Outcome"]
for t in (DOCS / "tasks").glob("*.md"):
    if "template" in t.name:
        continue
    text = t.read_text()
    errors += [f"{t.relative_to(ROOT)}: missing '{s}'" for s in required if s not in text]
    if "Status: done" in text and re.search(r"## Outcome\s*(<!--.*?-->)?\s*$", text, re.S):
        errors.append(f"{t.relative_to(ROOT)}: marked done but Outcome is empty")

if errors:
    print("Doc check failed:\n" + "\n".join(f"  - {e}" for e in errors))
    sys.exit(1)
print("Doc check passed.")