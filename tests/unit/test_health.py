"""Unit tests for health endpoints."""

import pytest

from habagou.routers.health import healthz


@pytest.mark.anyio
async def test_healthz_reports_ok() -> None:
    """The liveness probe reports the process is healthy."""
    assert await healthz() == {"status": "ok"}
