#!/usr/bin/env python3
import json
import subprocess
import sys

data = json.load(sys.stdin)
path = data.get("tool_input", {}).get("file_path", "")
if not path.endswith(".py"):
    sys.exit(0)

subprocess.run(["uv", "run", "ruff", "format", path], capture_output=True)
result = subprocess.run(
    ["uv", "run", "ruff", "check", "--fix", path], capture_output=True, text=True
)
if result.returncode != 0:
    print(f"ruff found issues in {path}:\n{result.stdout}", file=sys.stderr)
    sys.exit(2)
sys.exit(0)