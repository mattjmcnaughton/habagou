"""Unit tests for the agent eval harness plumbing (``evals/``, docs/evals.md).

Keyless and offline: the smoke model runs the REAL generation agent — system
prompt (with the corpus block), ``find_characters`` tool, and output validator
— against the frozen corpus snapshot, proving the dataset, evaluators, metric
recording, and hard-floor bookkeeping work end to end without a provider.
``TestModel`` performs no network I/O, so the suite-wide
``ALLOW_MODEL_REQUESTS = False`` guard is untouched.
"""

from __future__ import annotations

import pytest

from evals.corpus import corpus_hanzi, snapshot_corpus
from evals.generation import (
    GENERATION_EVALUATORS,
    HARD_FLOOR_EVALUATOR,
    build_generation_task,
    load_generation_dataset,
    smoke_model,
)


@pytest.mark.anyio
async def test_snapshot_corpus_satisfies_corpus_reader() -> None:
    corpus = snapshot_corpus()
    all_hanzi = await corpus.all_hanzi()
    # The committed snapshot is the full pinned hanzi-writer-data corpus, not a
    # test slice; a shrunken regeneration should fail loudly here.
    assert len(all_hanzi) > 9000
    assert list(all_hanzi) == sorted(all_hanzi)
    # Real stroke counts (same values the contract test's fixture hand-codes).
    assert await corpus.stroke_counts(["你", "好"]) == {"你": 7, "好": 6}
    assert await corpus.missing_hanzi(["你", "A"]) == {"A"}
    assert "你" in corpus_hanzi()


def test_generation_dataset_loads_with_all_evaluators() -> None:
    dataset = load_generation_dataset()
    assert len(dataset.cases) >= 5
    registered = {type(evaluator).__name__ for evaluator in dataset.evaluators}
    assert registered >= {cls.__name__ for cls in GENERATION_EVALUATORS}
    # The soft response-time budget (pydantic-evals built-in) rides along.
    assert "MaxDuration" in registered
    # The CLI's exit-code logic keys on this evaluator being present.
    assert HARD_FLOOR_EVALUATOR in registered


@pytest.mark.anyio
async def test_smoke_run_passes_every_assertion() -> None:
    dataset = load_generation_dataset()
    report = await dataset.evaluate(
        build_generation_task(smoke_model()), name="smoke-unit", progress=False
    )
    assert not report.failures
    assert len(report.cases) == len(dataset.cases)
    for case in report.cases:
        for name, result in case.assertions.items():
            assert result.value, f"{case.name} / {name}: {result.reason}"
        # TestModel always burns one tool round trip before its fixed output.
        assert case.metrics["model_requests"] >= 1
