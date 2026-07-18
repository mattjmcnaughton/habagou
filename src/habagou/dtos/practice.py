"""DTOs for the conversational practice tutor (WF-16).

``PracticeTurn`` is the agent's ``output_type``: every tutor reply is a list of
per-sentence segments, each carrying the sentence three ways (hanzi, pinyin,
English), plus an optional English aside used only when the learner asks for
help. Structuring the turn makes the UI's tap-for-translation free (the English
is generated with the turn and merely hidden client-side) and makes
"break glass" a field rather than a conversational mode to track. All glosses
are model-supplied and unverified — the same trade-off pack generation accepts,
contained here to a single ephemeral reply.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field

# Size bounds keep hand-crafted payloads from amplifying into oversized
# (billed) model calls, while staying generous enough that a well-behaved
# model never trips them into a needless retry.
SegmentTextStr = Annotated[str, Field(min_length=1, max_length=500)]


class PracticeSegment(BaseModel):
    """One sentence of a tutor reply, carried three ways.

    ``english`` is generated with every segment even though the UI hides it
    behind a tap — a few dozen output tokens buys instant reveal with no second
    model call.
    """

    hanzi: SegmentTextStr
    pinyin: SegmentTextStr
    english: SegmentTextStr


class PracticeTurn(BaseModel):
    """Structured output the practice agent returns for one tutor reply.

    ``english_aside`` is the "break glass" channel: filled only when the
    learner asked for help in English, and rendered as a distinct helper
    bubble while ``segments`` continue the conversation in Chinese.
    """

    segments: Annotated[list[PracticeSegment], Field(min_length=1, max_length=8)]
    english_aside: Annotated[str, Field(min_length=1, max_length=2000)] | None = None


class PracticeTurnRequestDTO(BaseModel):
    """Request for one practice turn.

    On the first turn of a conversation ``message`` is the learner's chosen
    topic (the system prompt tells the tutor to open the conversation from
    it) and ``history`` is ``None``. On later turns ``message`` is the
    learner's chat input — English, Chinese, or mixed — and ``history`` is the
    opaque JSON message history a prior turn returned (see
    :class:`PracticeTurnResponseDTO`); replaying it keeps the model's context
    with no server-side conversation store.
    """

    message: Annotated[str, Field(min_length=1, max_length=2000)]
    # Each turn appends ~3 messages (request, response, and the output-tool
    # return), so this bounds a conversation to ~130 turns — far past any real
    # practice session — while still capping hand-crafted payload
    # amplification.
    history: Annotated[list[Any], Field(max_length=400)] | None = None


class PracticeTurnResponseDTO(BaseModel):
    """A tutor reply plus the updated conversation history to hold client-side.

    The client keeps ``history`` between turns and passes it back on the next
    :class:`PracticeTurnRequestDTO`. Conversations are ephemeral by design:
    discarding the history is how a conversation ends.
    """

    turn: PracticeTurn
    history: list[Any]


class PracticeStatusDTO(BaseModel):
    """Whether conversational practice is available, for entry-point gating.

    ``enabled`` mirrors :attr:`habagou.config.Settings.practice_configured`.
    The Practice tab renders regardless (hiding a tab on an async fetch would
    shift the app shell); the practice screen itself shows an unavailable
    state when this reports ``False``, so a user is never routed into a flow
    the ``/turn`` endpoint can only 503.
    """

    enabled: bool
