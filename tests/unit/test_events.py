from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import cast

import pytest

from habagou import events


def test_packaged_workflow_catalog_matches_docs_catalog() -> None:
    packaged = files("habagou").joinpath("workflows.yml").read_text(encoding="utf-8")
    docs = Path("docs/workflows.yml").read_text(encoding="utf-8")

    assert packaged == docs


def test_workflow_ids_load_from_catalog() -> None:
    assert "WF-01" in events.workflow_ids()
    assert "WF-10" in events.workflow_ids()


def test_emit_workflow_event_logs_and_records_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: dict[str, object] = {}
    counter_calls: list[tuple[int, dict[str, str]]] = []
    duration_calls: list[tuple[int, dict[str, str]]] = []

    class StubLogger:
        def info(self, event: str, **fields: object) -> None:
            emitted["event"] = event
            emitted.update(fields)

    class StubCounter:
        def add(self, value: int, attributes: dict[str, str]) -> None:
            counter_calls.append((value, attributes))

    class StubHistogram:
        def record(self, value: int, attributes: dict[str, str]) -> None:
            duration_calls.append((value, attributes))

    monkeypatch.setattr(events.structlog, "get_logger", lambda _name: StubLogger())
    monkeypatch.setattr(events, "_workflow_total", StubCounter())
    monkeypatch.setattr(events, "_workflow_duration_ms", StubHistogram())

    events.emit_workflow_event(
        "pack_served",
        workflow="WF-02",
        duration_ms=12,
        pack_slug="greetings",
    )

    assert emitted == {
        "event": "pack_served",
        "workflow": "WF-02",
        "outcome": "ok",
        "duration_ms": 12,
        "pack_slug": "greetings",
    }
    assert counter_calls == [(1, {"workflow": "WF-02", "outcome": "ok"})]
    assert duration_calls == [(12, {"workflow": "WF-02"})]


def test_emit_workflow_event_noops_without_metric_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubLogger:
        def info(self, _event: str, **_fields: object) -> None:
            return None

    monkeypatch.setattr(events.structlog, "get_logger", lambda _name: StubLogger())

    events.emit_workflow_event("pack_served", workflow="WF-02", duration_ms=1)


def test_emit_workflow_event_rejects_unknown_workflow() -> None:
    with pytest.raises(events.UnknownWorkflowError, match="WF-99"):
        events.emit_workflow_event("bad", workflow="WF-99")


def test_emit_workflow_event_rejects_unknown_outcome() -> None:
    with pytest.raises(events.InvalidOutcomeError, match="invalid"):
        events.emit_workflow_event(
            "bad",
            workflow="WF-01",
            outcome=cast("events.Outcome", "invalid"),
        )
