from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

from habagou import events

_WORKFLOW_ID = re.compile(r"^\s*-\s*id:\s*(WF-\d{2})\s*$")
_WORKFLOW_LITERAL = re.compile(r'workflow="(WF-\d{2})"')


def test_packaged_workflow_catalog_matches_docs_catalog() -> None:
    packaged = files("habagou").joinpath("workflows.yml").read_text(encoding="utf-8")
    docs = Path("docs/workflows.yml").read_text(encoding="utf-8")

    assert packaged == docs


def test_workflow_literals_are_declared_in_packaged_catalog() -> None:
    workflow_ids = _workflow_ids_from_catalog()
    emitted_ids = {
        match.group(1)
        for root in (Path("src/habagou"), Path("scripts"))
        for path in root.rglob("*.py")
        for match in _WORKFLOW_LITERAL.finditer(path.read_text(encoding="utf-8"))
    }

    assert emitted_ids
    assert emitted_ids <= workflow_ids


def test_emit_workflow_event_logs(monkeypatch) -> None:
    emitted: dict[str, object] = {}

    class StubLogger:
        def info(self, event: str, **fields: object) -> None:
            emitted["event"] = event
            emitted.update(fields)

    monkeypatch.setattr(events.structlog, "get_logger", lambda _name: StubLogger())

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


def test_emit_workflow_event_does_not_require_metric_exporter(monkeypatch) -> None:
    class StubLogger:
        def info(self, _event: str, **_fields: object) -> None:
            return None

    monkeypatch.setattr(events.structlog, "get_logger", lambda _name: StubLogger())

    events.emit_workflow_event("pack_served", workflow="WF-02", duration_ms=1)


def _workflow_ids_from_catalog() -> set[str]:
    catalog = files("habagou").joinpath("workflows.yml")
    return {
        match.group(1)
        for line in catalog.read_text(encoding="utf-8").splitlines()
        if (match := _WORKFLOW_ID.match(line))
    }
