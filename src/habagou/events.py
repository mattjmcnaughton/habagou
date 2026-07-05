"""Workflow event logging."""

from __future__ import annotations

from typing import Literal

import structlog

Outcome = Literal["ok", "error"]


def emit_workflow_event(
    event: str,
    *,
    workflow: str,
    outcome: Outcome = "ok",
    duration_ms: int = 0,
    **fields: object,
) -> None:
    """Emit one structured workflow event."""
    structlog.get_logger("habagou.events").info(
        event,
        workflow=workflow,
        outcome=outcome,
        duration_ms=duration_ms,
        **fields,
    )
