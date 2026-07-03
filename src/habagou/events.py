"""Workflow event logging and metrics."""

from __future__ import annotations

import re
from functools import cache
from importlib.resources import files
from typing import Literal

import structlog
from opentelemetry import metrics

Outcome = Literal["ok", "error"]
_WORKFLOW_ID = re.compile(r"^\s*-\s*id:\s*(WF-\d{2})\s*$")

_meter = metrics.get_meter("habagou")
_workflow_total = _meter.create_counter(
    "habagou_workflow_total",
    unit="1",
    description="Workflow outcomes emitted by Habagou.",
)
_workflow_duration_ms = _meter.create_histogram(
    "habagou_workflow_duration_ms",
    unit="ms",
    description="Workflow event durations emitted by Habagou.",
)


class UnknownWorkflowError(ValueError):
    """Raised when code emits an event for a workflow outside the catalog."""


class InvalidOutcomeError(ValueError):
    """Raised when code emits an event with an unsupported outcome."""


@cache
def workflow_ids() -> frozenset[str]:
    """Return workflow IDs declared in the packaged workflow catalog."""
    ids: set[str] = set()
    catalog = files("habagou").joinpath("workflows.yml")
    for line in catalog.read_text(encoding="utf-8").splitlines():
        match = _WORKFLOW_ID.match(line)
        if match:
            ids.add(match.group(1))
    if not ids:
        raise RuntimeError("no workflow IDs found in packaged workflow catalog")
    return frozenset(ids)


def emit_workflow_event(
    event: str,
    *,
    workflow: str,
    outcome: Outcome = "ok",
    duration_ms: int = 0,
    **fields: object,
) -> None:
    """Emit one structured workflow event and matching OTel metrics."""
    if workflow not in workflow_ids():
        raise UnknownWorkflowError(f"unknown workflow ID: {workflow}")
    if outcome not in {"ok", "error"}:
        raise InvalidOutcomeError(f"invalid workflow outcome: {outcome}")

    attributes = {"workflow": workflow, "outcome": outcome}
    _workflow_total.add(1, attributes)
    _workflow_duration_ms.record(duration_ms, {"workflow": workflow})
    structlog.get_logger("habagou.events").info(
        event,
        workflow=workflow,
        outcome=outcome,
        duration_ms=duration_ms,
        **fields,
    )
