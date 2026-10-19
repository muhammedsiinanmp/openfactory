"""The `openfactory_req` pytest plugin, loaded by the `pytest` gate into the target repo.

See "The pytest gate and `req` markers" under "Gates and remediation" in
docs/spec/phase1-spec.md and ADR-015. It registers the `req` marker and, when collection
finishes, writes one JSON line per collected test to the file named by
`OPENFACTORY_REQ_OUT`. It imports only pytest and the standard library, so it loads in
the target repo's environment; OpenFactory's own code does not import it.
"""

import json
import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "req(*ids): the requirement ids this test covers")


def pytest_collection_finish(session: pytest.Session) -> None:
    out = os.environ.get("OPENFACTORY_REQ_OUT")
    if not out:
        return
    # The gate starts pytest in the worktree root, so paths are relative to the repo.
    base = session.config.invocation_params.dir
    with open(out, "w", encoding="utf-8") as file:
        for item in session.items:
            req = [arg for marker in item.iter_markers("req") for arg in marker.args]
            line = {"file": item.path.relative_to(base).as_posix(), "req": req}
            file.write(json.dumps(line) + "\n")
