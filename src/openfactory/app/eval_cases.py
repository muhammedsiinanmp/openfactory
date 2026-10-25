"""Eval case labels: parses a case's `labels.yaml` text into `EvalLabels`.

See ADR-021 and "Evaluation plan" › Ground truth in docs/spec/phase1-spec.md. Pure: the
harness reads the file. A repeated key keeps its last value (`yaml.safe_load`).
"""

import yaml

from openfactory.domain.eval_scoring import EvalLabels


def parse_eval_labels(text: str) -> EvalLabels:
    """Raises `ValueError` (a Pydantic `ValidationError` among them) for anything but the format."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"labels are not YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("labels are not a mapping")
    return EvalLabels.model_validate(data)
