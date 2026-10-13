"""The commit message of a passed task: subject, body and trailers.

See docs/spec/phase1-spec.md ("Traceability": "Commit trailers"; "Execution": "The
commit") and ADR-003. The subject is `<task id>: <objective>` cut to 72 characters, the
body is the run's summary without the whitespace around it, and the trailers are the last
paragraph. Paragraphs are separated by one empty line; a summary with no text gives no
body paragraph.
"""

from openfactory.domain.contracts import TaskContract


def build_commit_message(
    contract: TaskContract, summary: str, run_id: str, spec_version: str
) -> str:
    subject = f"{contract.task_id}: {contract.objective}"[:72]
    trailers = "\n".join(
        [
            f"Task: {contract.task_id}",
            f"Requirements: {', '.join(contract.requirements)}",
            f"Acceptance-Criteria: {', '.join(contract.acceptance_criteria)}",
            f"Agent-Run: {run_id}",
            f"Spec-Version: {spec_version}",
        ]
    )
    body = summary.strip()
    paragraphs = [subject, body, trailers] if body else [subject, trailers]
    return "\n\n".join(paragraphs) + "\n"
