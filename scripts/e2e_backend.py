"""Test-only backend entrypoint for the frontend Playwright e2e suite.

This module exists solely so the Playwright suite can drive the real Habagou
API — real routers, services, repositories, the seeded corpus, and the real
pack-generation agent (its ``find_characters`` tool and corpus output
validator) — with the *model* replaced by a deterministic stub. It performs
NO LLM/provider network I/O.

It is NEVER a production entrypoint: production serves ``habagou.app:app``.
This file lives under ``scripts/`` (not ``src/habagou/``) and is deliberately
excluded from the shipped wheel (``[tool.hatch.build.targets.wheel] packages =
["src/habagou"]``), so it can never be imported by the deployed application.

Launch it with uvicorn's factory mode. Importing the module does not mutate
settings or enter the model override — those happen only inside
``create_stub_app`` — so the unit test in ``tests/unit/test_e2e_backend.py`` can
import the stub pieces without disabling the rate cap or forcing the stub model.
(Importing does pull in ``habagou.app``, whose module-scope ``create_app()``
requires ``SESSION_SECRET_KEY`` and runs telemetry setup; those are import-time
costs of the app package, not this module's own doing.) ::

    uv run uvicorn scripts.e2e_backend:create_stub_app --factory \
        --host 127.0.0.1 --port 8000

``create_stub_app`` sets ``openrouter_api_key`` so ``generation_configured`` is
True (the ``/status`` probe reports enabled and the "Create a pack" entry point
shows; ``_build_model`` constructs its OpenRouter model without network), pins
the per-user rate limit to 0 (disabled) so the two Playwright projects sharing
one backend and one Keycloak user never trip the cap, then enters an
``Agent.override(model=...)`` for the process lifetime — which beats the
run-time ``model=`` argument ``generate_pack_draft`` passes.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from habagou.app import create_app
from habagou.config import settings
from habagou.services.pack_generation import get_generation_agent
from habagou.services.practice_chat import get_practice_agent

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastapi import FastAPI
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

# --- Deterministic drafts -----------------------------------------------------
#
# Both drafts use only characters that live in the seeded packs
# (scripts.seed.SEED_PACKS) and are therefore guaranteed present in the full
# hanzi-writer corpus imported by ``just bootstrap`` in CI, so the agent's
# corpus output validator accepts them without a retry. Each sentence is
# composed only of characters that are also in the draft.
#
# The coverage note follows the canonical "Found N of M — ..." shape the UI
# bolds (its leading clause up to the first ; , or .), matching the system
# prompt's example wording.

# First turn: a compact 4-character draft with one sentence.
FIRST_DRAFT: dict[str, object] = {
    "title": "Ordering Food",
    "characters": [
        {"hanzi": "你", "pinyin": "nǐ", "meaning": "you"},
        {"hanzi": "好", "pinyin": "hǎo", "meaning": "good"},
        {"hanzi": "我", "pinyin": "wǒ", "meaning": "I, me"},
        {"hanzi": "谢", "pinyin": "xiè", "meaning": "thanks"},
    ],
    "sentences": [
        {"hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "Hello"},
    ],
    "coverage_note": "Found 4 of 4 requested characters; all are traceable.",
}

# Refinement turn ("make it harder"): the same pack grown by two characters, so
# the preview is visibly different (6 characters and a "Draft 2" badge).
REFINED_DRAFT: dict[str, object] = {
    "title": "Ordering Food",
    "characters": [
        {"hanzi": "你", "pinyin": "nǐ", "meaning": "you"},
        {"hanzi": "好", "pinyin": "hǎo", "meaning": "good"},
        {"hanzi": "我", "pinyin": "wǒ", "meaning": "I, me"},
        {"hanzi": "谢", "pinyin": "xiè", "meaning": "thanks"},
        {"hanzi": "水", "pinyin": "shuǐ", "meaning": "water"},
        {"hanzi": "茶", "pinyin": "chá", "meaning": "tea"},
    ],
    "sentences": [
        {"hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "Hello"},
    ],
    "coverage_note": "Found 6 of 6 requested characters; added two harder ones.",
}


def _count_user_prompts(messages: Sequence[ModelMessage]) -> int:
    """Number of user-authored prompts across a run's message history.

    The first draft turn carries exactly one user prompt; a refinement turn
    replays the prior conversation plus the new prompt, so it carries two or
    more. Retry prompts from the output validator are ``RetryPromptPart``, not
    ``UserPromptPart``, so they never inflate this count.
    """
    return sum(
        1
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    )


def _stub_model_response(
    messages: Sequence[ModelMessage], info: AgentInfo
) -> ModelResponse:
    """Deterministic ``FunctionModel`` callback: draft on turn 1, refine after.

    Returns the draft directly via the agent's output tool (no ``find_characters``
    round trip needed — the drafts are already corpus-grounded), mirroring the
    integration suite's ``_Responder``. Turn selection is driven purely by the
    user-prompt count, so the same topic always yields the same draft.
    """
    draft = REFINED_DRAFT if _count_user_prompts(messages) >= 2 else FIRST_DRAFT
    return ModelResponse(
        parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=draft)]
    )


def stub_generation_model() -> FunctionModel:
    """The deterministic, network-free model the e2e backend runs the agent on."""
    return FunctionModel(_stub_model_response)


# --- Deterministic practice turns (WF-16) --------------------------------------
#
# The practice agent has no corpus grounding, so these turns only need to be
# stable and visibly distinct across the first and follow-up turns. The
# follow-up carries an english_aside so the e2e suite can exercise the
# "break glass" rendering deterministically.

PRACTICE_OPENER: dict[str, object] = {
    "segments": [
        {"hanzi": "你好", "pinyin": "nǐ hǎo", "english": "Hello!"},
        {
            "hanzi": "你想吃什么",
            "pinyin": "nǐ xiǎng chī shénme",
            "english": "What do you want to eat?",
        },
    ],
}

PRACTICE_FOLLOW_UP: dict[str, object] = {
    "segments": [
        {"hanzi": "好的", "pinyin": "hǎo de", "english": "Okay!"},
        {
            "hanzi": "你要喝什么",
            "pinyin": "nǐ yào hē shénme",
            "english": "What do you want to drink?",
        },
    ],
    "english_aside": "喝 (hē) means 'to drink' — you'll hear it in drink questions.",
}


def _stub_practice_response(
    messages: Sequence[ModelMessage], info: AgentInfo
) -> ModelResponse:
    """Deterministic ``FunctionModel`` callback: opener on turn 1, reply after.

    Turn selection is driven purely by the user-prompt count (mirroring
    :func:`_stub_model_response`), so the same conversation always renders the
    same transcript.
    """
    turn = PRACTICE_FOLLOW_UP if _count_user_prompts(messages) >= 2 else PRACTICE_OPENER
    return ModelResponse(
        parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=turn)]
    )


def stub_practice_model() -> FunctionModel:
    """The deterministic, network-free model for the practice agent."""
    return FunctionModel(_stub_practice_response)


# Holds the process-lifetime ``Agent.override`` context open. Module-global so it
# is never garbage-collected (and thus never exited) for the life of the server.
_override_stack = ExitStack()


def create_stub_app() -> FastAPI:
    """Build the e2e app: real API, seeded corpus, stubbed generation model.

    uvicorn factory entrypoint (``--factory``). Configures generation to be
    "enabled" without any provider network, disables the per-user rate cap, and
    forces the generation agent onto :func:`stub_generation_model` for the whole
    process.
    """
    # Make generation "configured": /status reports enabled (so the frontend
    # shows the entry point) and _build_model() constructs an OpenRouter model
    # without network — the override below means it is never actually called.
    settings.openrouter_api_key = "e2e-stub"
    # Belt-and-suspenders with GENERATION_RATE_LIMIT_PER_HOUR=0 in the Playwright
    # webServer env: two projects share one backend and one Keycloak user, so the
    # cap must be off. create_app() reads this to build the limiter, so pin it
    # BEFORE constructing the app. Same for the practice cap.
    settings.generation_rate_limit_per_hour = 0
    settings.practice_rate_limit_per_hour = 0

    app = create_app()

    agent = get_generation_agent()
    # Enter the overrides for the process lifetime (never exited): the stubbed
    # models beat the run-time model= arguments the services pass. No
    # dependency_overrides entries are needed — the get_*_agent dependencies
    # already return these same module-level agents, so the overrides alone
    # stub them.
    _override_stack.enter_context(agent.override(model=stub_generation_model()))
    _override_stack.enter_context(
        get_practice_agent().override(model=stub_practice_model())
    )

    return app
