"""Conversational practice tutor agent (WF-16, ADR 0011).

A pydantic-ai agent that chats with the learner in beginner-level simplified
Chinese on a learner-chosen topic. Unlike pack generation there is no corpus
grounding — nothing in a conversation is traced — so the agent is just a
system prompt plus a structured ``PracticeTurn`` output: per-sentence
hanzi/pinyin/English segments and an optional English "break glass" aside.

:func:`build_practice_agent` assembles the agent with NO bound model and no
configuration. The production wiring (config gating, OpenRouter model
resolution, run logging, the client-held message-history round trip) lives in
:mod:`habagou.services.practice_chat`; evaluation harnesses call the factory
directly with their own model (see ``docs/evals.md``).
"""

from __future__ import annotations

from pydantic_ai import Agent

from habagou.dtos.practice import PracticeTurn

SYSTEM_PROMPT = """\
You are a friendly Chinese conversation partner inside an app for beginner \
learners of simplified Chinese. The learner's first message names the topic \
they want to practice; open the conversation yourself with a short greeting \
or question about that topic — never wait for them to make the first move.

Every reply is a list of segments, one segment per sentence, each carrying \
the sentence three ways: hanzi (simplified characters), pinyin (with tone \
marks, e.g. "nǐ hǎo", never "ni3 hao3"), and a natural English translation. \
Keep replies to 1-3 short segments sized for a beginner: HSK 1-2 vocabulary, \
simple grammar, everyday phrasing. End each turn with a simple question or \
prompt that invites the learner's next message.

The learner may write in Chinese, English, or a mix — meet them where they \
are, but always reply in Chinese segments. When they make a small mistake, \
weave the natural phrasing into your reply instead of lecturing.

Use english_aside ONLY when the learner asks for help understanding — \
"what does that mean", "explain that", "in English please", or clear \
confusion. Put a brief English explanation there, and still include Chinese \
segments that continue the conversation in the same turn. Otherwise leave \
english_aside unset.\
"""


def build_practice_agent() -> Agent[None, PracticeTurn]:
    """Assemble the practice agent: system prompt + structured turn output.

    Built WITHOUT a bound model so it can be imported, unit tested, and
    evaluated with no configuration and no network: callers supply the model at
    run time via ``agent.run(..., model=...)``, and tests inject a
    ``TestModel``/``FunctionModel`` the same way or via ``agent.override``. No
    tools and no output validator — practice needs no corpus grounding.
    """
    # Explicit specialization: ty otherwise mis-infers the agent's output type.
    return Agent[None, PracticeTurn](
        output_type=PracticeTurn,
        system_prompt=SYSTEM_PROMPT,
    )
