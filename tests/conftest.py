"""Fixtures shared by the whole suite."""

from collections.abc import Iterator

import pytest
import structlog


@pytest.fixture(autouse=True)
def reset_structlog() -> Iterator[None]:
    """Every CLI invocation configures structlog on a stream that is gone when it ends."""
    yield
    structlog.reset_defaults()
