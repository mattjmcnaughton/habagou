from __future__ import annotations

import pytest
from sqlalchemy import delete

from habagou import db
from habagou.models import Character
from scripts import check_invariants


@pytest.mark.anyio
async def test_seeded_database_passes_invariant_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        check_invariants,
        "emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    exit_code = await check_invariants.run(_dsn())

    assert exit_code == 0
    assert events == [
        (
            "invariant_check",
            {
                "workflow": "WF-10",
                "outcome": "ok",
                "duration_ms": events[0][1]["duration_ms"],
                "issue_count": 0,
            },
        )
    ]


@pytest.mark.anyio
async def test_missing_sentence_only_character_names_pack_and_character(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        check_invariants,
        "emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )
    async with db.async_session() as session:
        await session.execute(delete(Character).where(Character.hanzi == "很"))
        await session.commit()

    exit_code = await check_invariants.run(_dsn())

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing_sentence_character" in captured.err
    assert "pack=greetings" in captured.err
    assert "character=很" in captured.err
    assert events[0][0] == "invariant_check"
    assert events[0][1]["workflow"] == "WF-10"
    assert events[0][1]["outcome"] == "error"
    assert events[0][1]["issue_count"] == 1


def _dsn() -> str:
    return db.engine.url.render_as_string(hide_password=False)
