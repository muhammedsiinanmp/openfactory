#!/usr/bin/env python3
import json
import subprocess
import sys

data = json.load(sys.stdin)
if data.get("stop_hook_active"):
    sys.exit(0)  # already retried once; avoid an infinite loop

checks = [
    ("ruff-check", ["uv", "run", "ruff", "check", "."]),
    ("ruff-format", ["uv", "run", "ruff", "format", "--check", "."]),
    ("pytest", ["uv", "run", "pytest", "-q", "-x"]),
    ("docs", ["uv", "run", "python", "scripts/check_docs.py"]),
]
failures = []
for name, cmd in checks:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if name == "pytest" and r.returncode == 5:  # no tests collected yet
        continue
    if r.returncode != 0:
        failures.append(f"--- {name} failed ---\n{(r.stdout + r.stderr)[-3000:]}")

if failures:
    print("Not done. Fix these before finishing:\n" + "\n".join(failures), file=sys.stderr)
    sys.exit(2)
sys.exit(0)
