"""Determinism guard for the Playwright e2e stub backend (issue #102, Step 6).

The frontend e2e suite runs against ``scripts.e2e_backend`` with a stubbed,
network-free generation model. If that stub ever drifts, the Playwright specs
would fail remotely with an opaque UI assertion. These tests pin the stub's
behaviour locally (no network, no database — a lightweight corpus stub stands in
for ``CharacterRepository``, mirroring ``test_pack_generation``) so drift is
caught in the fast unit gate instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic_ai.models.function import FunctionModel

from habagou.dtos.generation import PackDraft
from habagou.services import pack_generation
from habagou.services.pack_generation import GenerationDeps
from scripts.e2e_backend import stub_generation_model

if TYPE_CHECKING:
    from collections.abc import Iterable


class _AcceptingCorpus:
    """Corpus seam that treats every hanzi as present (the CI full-corpus case).

    The stub drafts only use characters guaranteed in the seeded corpus, so the
    agent's output validator would accept them against real Postgres in e2e;
    here we stand in for that without a database.
    """

    async def missing_hanzi(self, hanzi: Iterable[str]) -> set[str]:
        return set()

    async def stroke_counts(self, hanzi: Iterable[str]) -> dict[str, int]:
        return {char: 5 for char in set(hanzi)}


class _RejectFirstThenAcceptCorpus:
    """Corpus seam that fails the output validator once, then accepts everything.

    Forces the REAL agent's ``validate_corpus_membership`` to raise ``ModelRetry``
    on turn 1's first draft, re-invoking the model. The retry reaches the model as
    a ``RetryPromptPart`` — not a ``UserPromptPart`` — which is exactly the case
    ``_count_user_prompts`` must ignore so a retry never bumps the turn count.
    """

    def __init__(self) -> None:
        self.checks = 0

    async def missing_hanzi(self, hanzi: Iterable[str]) -> set[str]:
        self.checks += 1
        # Reject the whole first draft (one forced retry), then accept.
        return set(hanzi) if self.checks == 1 else set()

    async def stroke_counts(self, hanzi: Iterable[str]) -> dict[str, int]:
        return {char: 5 for char in set(hanzi)}


def _deps() -> GenerationDeps:
    return GenerationDeps(characters=_AcceptingCorpus())


@pytest.mark.anyio
async def test_first_turn_returns_the_starter_draft() -> None:
    agent = pack_generation.get_generation_agent()

    result = await agent.run(
        "Ordering at a restaurant", deps=_deps(), model=stub_generation_model()
    )

    draft = result.output
    assert isinstance(draft, PackDraft)
    assert draft.title == "Ordering Food"
    assert [c.hanzi for c in draft.characters] == ["你", "好", "我", "谢"]
    # The gloss the corpus can't supply is present for every character.
    assert all(c.pinyin and c.meaning for c in draft.characters)
    # One sentence, composed only of drafted characters.
    assert [s.hanzi for s in draft.sentences] == ["你好"]
    # Coverage note in the canonical "Found N of M — ..." shape the UI bolds.
    assert draft.coverage_note is not None
    assert draft.coverage_note.startswith("Found 4 of 4")


@pytest.mark.anyio
async def test_refinement_turn_returns_a_bigger_draft() -> None:
    agent = pack_generation.get_generation_agent()

    first = await agent.run(
        "Ordering at a restaurant", deps=_deps(), model=stub_generation_model()
    )
    second = await agent.run(
        "make it harder",
        deps=_deps(),
        model=stub_generation_model(),
        message_history=first.all_messages(),
    )

    draft = second.output
    # Visibly distinguishable from the first draft: two more characters (so the
    # preview shows a different count and a "Draft 2" badge).
    assert draft.title == "Ordering Food"
    assert [c.hanzi for c in draft.characters] == ["你", "好", "我", "谢", "水", "茶"]
    assert len(draft.characters) == len(first.output.characters) + 2
    assert draft.coverage_note is not None
    assert draft.coverage_note.startswith("Found 6 of 6")


@pytest.mark.anyio
async def test_validator_retry_does_not_advance_the_turn() -> None:
    # A RetryPromptPart from the output validator must NOT count as a user
    # prompt: after one forced retry on turn 1, the stub must still return the
    # FIRST draft (4 characters), never the 6-character refinement.
    agent = pack_generation.get_generation_agent()
    corpus = _RejectFirstThenAcceptCorpus()

    result = await agent.run(
        "Ordering at a restaurant",
        deps=GenerationDeps(characters=corpus),
        model=stub_generation_model(),
    )

    # The validator genuinely rejected once (proving a retry happened) ...
    assert corpus.checks == 2
    # ... yet the run still yielded the starter draft, not the refinement.
    draft = result.output
    assert isinstance(draft, PackDraft)
    assert draft.title == "Ordering Food"
    assert [c.hanzi for c in draft.characters] == ["你", "好", "我", "谢"]
    assert draft.coverage_note is not None
    assert draft.coverage_note.startswith("Found 4 of 4")


def test_stub_model_is_a_function_model_no_network() -> None:
    # The stub is a FunctionModel (pydantic-ai runs the callback in-process; it
    # is exempt from the suite-wide ALLOW_MODEL_REQUESTS guard and makes no
    # provider request).
    assert isinstance(stub_generation_model(), FunctionModel)
