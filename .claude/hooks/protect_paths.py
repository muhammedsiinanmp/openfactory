#!/usr/bin/env python3
import json
import sys
from pathlib import PurePosixPath

PROTECTED_PREFIXES = ("docs/spec/", "docs/generated/", ".git/")
PROTECTED_FILES = {".env", ".claude/settings.json"}

data = json.load(sys.stdin)
path = data.get("tool_input", {}).get("file_path", "")
root = data.get("cwd", "")

rel = path[len(root):].lstrip("/") if root and path.startswith(root) else path
rel = str(PurePosixPath(rel))

if rel in PROTECTED_FILES or rel.startswith(PROTECTED_PREFIXES):
    print(
        f"BLOCKED: {rel} is protected. Spec and generated docs are changed only by "
        "the human or by scripts. If you think it needs to change, stop and ask.",
        file=sys.stderr,
    )
    sys.exit(2)
sys.exit(0)