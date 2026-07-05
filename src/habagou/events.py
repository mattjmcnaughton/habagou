"""Workflow event logging."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import structlog

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

Outcome = Literal["ok", "error"]


@dataclass
class WorkflowEvent:
    """Mutable workflow event payload built inside a timed block."""

    event: str
    workflow: str
    started_at: float
    outcome: Outcome = "ok"
    duration_ms: int | None = None
    fields: dict[str, object] = field(default_factory=dict)

    def elapsed_ms(self) -> int:
        return round((time.perf_counter() - self.started_at) * 1000)


@asynccontextmanager
async def workflow_event(
    event: str, *, workflow: str, **fields: object
) -> AsyncIterator[WorkflowEvent]:
    """Times the block and emits one workflow event on exit."""
    context = WorkflowEvent(
        event=event,
        workflow=workflow,
        started_at=time.perf_counter(),
        fields=fields,
    )
    try:
        yield context
    except BaseException:
        if context.outcome == "error":
            _emit_context(context)
        raise
    else:
        _emit_context(context)


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


def _emit_context(context: WorkflowEvent) -> None:
    emit_workflow_event(
        context.event,
        workflow=context.workflow,
        outcome=context.outcome,
        duration_ms=(
            context.duration_ms
            if context.duration_ms is not None
            else context.elapsed_ms()
        ),
        **context.fields,
    )
