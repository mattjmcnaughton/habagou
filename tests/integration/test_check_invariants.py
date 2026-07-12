from __future__ import annotations

import pytest
from sqlalchemy import delete, text

from habagou import db
from habagou.models import (
    ActivityCompletion,
    ActivityType,
    Character,
    CompletionSource,
    PackStatus,
    PathItem,
    PathItemKind,
)
from habagou.repositories import PackRepository
from scripts import check_invariants
from tests.integration.conftest import create_user


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


@pytest.mark.anyio
async def test_path_source_completion_missing_item_is_detected(
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
        user = await create_user(session)
        pack = await PackRepository(session).get_by_slug("greetings")
        assert pack is not None
        # The DB-level check constraint normally forbids this row; drop it so
        # the test can exercise the invariant script's own detection.
        await session.execute(
            text(
                "ALTER TABLE activity_completions "
                "DROP CONSTRAINT ck_activity_completions_path_source"
            )
        )
        await session.commit()
        session.add(
            ActivityCompletion(
                user_id=user.id,
                pack_id=pack.id,
                activity=ActivityType.TRACE,
                duration_ms=1000,
                source=CompletionSource.PATH,
                path_item_id=None,
            )
        )
        await session.commit()

    exit_code = await check_invariants.run(_dsn())

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "path_completion_missing_item" in captured.err
    assert events[0][0] == "invariant_check"
    assert events[0][1]["outcome"] == "error"
    assert events[0][1]["issue_count"] == 1


@pytest.mark.anyio
async def test_path_item_referencing_unpublished_pack_is_detected(
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
        user = await create_user(session)
        pack_repository = PackRepository(session)
        pack = await pack_repository.get_by_slug("greetings")
        assert pack is not None
        session.add(
            PathItem(
                user_id=user.id,
                position=1,
                activity=ActivityType.TRACE,
                kind=PathItemKind.NEW,
                pack_id=pack.id,
                content={
                    "unit_label": None,
                    "pack_slug": "greetings",
                    "activity_content": {},
                    "units": [],
                },
            )
        )
        await session.commit()

        await pack_repository.set_status("greetings", PackStatus.DRAFT)
        await session.commit()

    exit_code = await check_invariants.run(_dsn())

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "path_item_unpublished_pack" in captured.err
    assert events[0][0] == "invariant_check"
    assert events[0][1]["outcome"] == "error"
    assert events[0][1]["issue_count"] == 1


def _dsn() -> str:
    return db.engine.url.render_as_string(hide_password=False)
