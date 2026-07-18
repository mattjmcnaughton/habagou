"""Generation-agent evals: deterministic evaluators, dataset, and task.

Everything here scores a :class:`~habagou.dtos.generation.PackDraft` with
plain Python — no LLM judge, so a run costs only the generation calls
themselves. The dataset lives in ``generation_dataset.yaml``; the evaluators
are registered there by class name and resolved via
:data:`GENERATION_EVALUATORS` when the dataset is loaded.

Exactly one evaluator is a hard floor (see docs/evals.md):
:class:`CorpusMembership`. The agent's output validator already enforces
membership per request, so a violation surviving to the report means the
retry budget was exhausted — the unmissable "this prompt/model combination
does not hold the constraint" signal. Everything else is a tracked score.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_evals import Dataset, increment_eval_metric
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from evals.corpus import corpus_hanzi, snapshot_corpus
from habagou.agents.generation import GenerationDeps, build_generation_agent
from habagou.dtos.generation import PackDraft

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic_ai.models import Model

DATASET_PATH = Path(__file__).resolve().parent / "generation_dataset.yaml"

# Per-case metadata: optional "min_size"/"max_size" overrides for PackSize.
GenMeta = dict[str, int]

# Default pack-size band, from the system prompt's "roughly 5-12 characters
# unless the user asks for a different size".
_DEFAULT_MIN_SIZE = 5
_DEFAULT_MAX_SIZE = 12

# The hard-floor evaluator name the CLI checks when deciding the exit code.
HARD_FLOOR_EVALUATOR = "CorpusMembership"


def _drafted_glyphs(draft: PackDraft) -> set[str]:
    """Every glyph the draft would trace: members plus each sentence glyph."""
    glyphs = {character.hanzi for character in draft.characters}
    for sentence in draft.sentences:
        glyphs.update(char for char in sentence.hanzi if char.strip())
    return glyphs


def _all_pinyin(draft: PackDraft) -> list[str]:
    """Every pinyin gloss in the draft: per-character and per-sentence."""
    return [character.pinyin for character in draft.characters] + [
        sentence.pinyin for sentence in draft.sentences
    ]


@dataclass(repr=False)
class CorpusMembership(Evaluator[str, PackDraft, GenMeta]):
    """HARD FLOOR: every drafted glyph must exist in the corpus snapshot."""

    def evaluate(
        self, ctx: EvaluatorContext[str, PackDraft, GenMeta]
    ) -> EvaluationReason:
        missing = sorted(_drafted_glyphs(ctx.output) - corpus_hanzi())
        if missing:
            return EvaluationReason(
                value=False, reason=f"non-corpus glyphs drafted: {''.join(missing)}"
            )
        return EvaluationReason(value=True, reason="all drafted glyphs in corpus")


@dataclass(repr=False)
class PinyinToneMarks(Evaluator[str, PackDraft, GenMeta]):
    """Pinyin uses tone marks, never tone digits ("nǐ", not "ni3")."""

    def evaluate(
        self, ctx: EvaluatorContext[str, PackDraft, GenMeta]
    ) -> EvaluationReason:
        offenders = [
            pinyin
            for pinyin in _all_pinyin(ctx.output)
            if any(char.isascii() and char.isdigit() for char in pinyin)
        ]
        if offenders:
            return EvaluationReason(
                value=False, reason=f"tone digits in: {', '.join(offenders[:5])}"
            )
        return EvaluationReason(value=True, reason="no tone digits")


@dataclass(repr=False)
class PunctuationFreeSentences(Evaluator[str, PackDraft, GenMeta]):
    """Sentences carry no punctuation (the corpus has none to trace)."""

    def evaluate(
        self, ctx: EvaluatorContext[str, PackDraft, GenMeta]
    ) -> EvaluationReason:
        offenders = sorted(
            {
                char
                for sentence in ctx.output.sentences
                for char in sentence.hanzi
                if unicodedata.category(char).startswith("P")
            }
        )
        if offenders:
            return EvaluationReason(
                value=False, reason=f"punctuation in sentences: {''.join(offenders)}"
            )
        return EvaluationReason(value=True, reason="sentences punctuation-free")


@dataclass(repr=False)
class PackSize(Evaluator[str, PackDraft, GenMeta]):
    """Pack size within the requested band (default 5-12 characters)."""

    def evaluate(
        self, ctx: EvaluatorContext[str, PackDraft, GenMeta]
    ) -> EvaluationReason:
        metadata = ctx.metadata or {}
        min_size = metadata.get("min_size", _DEFAULT_MIN_SIZE)
        max_size = metadata.get("max_size", _DEFAULT_MAX_SIZE)
        size = len(ctx.output.characters)
        return EvaluationReason(
            value=min_size <= size <= max_size,
            reason=f"{size} characters (band {min_size}-{max_size})",
        )


GENERATION_EVALUATORS: tuple[type[Evaluator[str, PackDraft, GenMeta]], ...] = (
    CorpusMembership,
    PinyinToneMarks,
    PunctuationFreeSentences,
    PackSize,
)


def load_generation_dataset() -> Dataset[str, PackDraft, GenMeta]:
    """Load the generation dataset with the custom evaluators registered."""
    return Dataset[str, PackDraft, GenMeta].from_file(
        DATASET_PATH, custom_evaluator_types=GENERATION_EVALUATORS
    )


def build_generation_task(model: Model) -> Callable[[str], Awaitable[PackDraft]]:
    """Bind the real generation agent to ``model`` over the frozen corpus.

    ``model_requests`` is recorded as an eval metric per case — the same
    round-trip count the service logs as ``model_requests``. With the corpus
    riding in the system prompt, an efficient run finishes in 1 request;
    higher means the model burned ``find_characters`` calls or ModelRetry
    round trips to hold the corpus constraint.
    """
    agent = build_generation_agent()
    deps = GenerationDeps(characters=snapshot_corpus())

    async def run_generation(topic: str) -> PackDraft:
        result = await agent.run(topic, deps=deps, model=model)
        increment_eval_metric("model_requests", result.usage.requests)
        return result.output

    return run_generation


def smoke_model() -> Model:
    """An offline stand-in model for plumbing checks (no key, no network).

    ``TestModel`` calls ``find_characters`` once with generated arguments and
    then returns this fixed draft, which the output validator accepts because
    every glyph is in the snapshot. ``--smoke`` runs and the unit tests use it
    to prove the dataset, evaluators, and reporting work end to end.
    """
    from pydantic_ai.models.test import TestModel

    return TestModel(
        custom_output_args={
            "title": "Smoke pack",
            "characters": [
                {"hanzi": "你", "pinyin": "nǐ", "meaning": "you"},
                {"hanzi": "好", "pinyin": "hǎo", "meaning": "good"},
                {"hanzi": "我", "pinyin": "wǒ", "meaning": "I, me"},
                {"hanzi": "人", "pinyin": "rén", "meaning": "person"},
                {"hanzi": "大", "pinyin": "dà", "meaning": "big"},
            ],
            "sentences": [
                {"hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "hello"}
            ],
        }
    )
