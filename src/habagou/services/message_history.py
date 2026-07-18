"""Client-held message-history (de)serialization shared by agent features.

Both agent chats (pack generation and conversational practice) keep the
conversation CLIENT-side: each turn returns the full pydantic-ai message
history as opaque JSON, and the client replays it on the next turn. These
helpers own that round trip, so the wire schema for the discriminated message
union lives in exactly one place (pydantic-ai's message-history type adapter).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic_ai.messages import ModelMessagesTypeAdapter

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage


def dump_message_history(messages: list[ModelMessage]) -> list[Any]:
    """Serialize a run's message history to JSON-able Python.

    The endpoints hold the conversation client-side between turns, so they need
    the pydantic-ai messages as plain JSON-serializable data (lists/dicts).
    Round trips with :func:`load_message_history`.
    """
    return ModelMessagesTypeAdapter.dump_python(messages, mode="json")


def load_message_history(data: list[Any]) -> list[ModelMessage]:
    """Rebuild a message history from :func:`dump_message_history` output.

    The inverse of :func:`dump_message_history`: turns the JSON-able payload the
    client sent back into ``list[ModelMessage]`` suitable for ``agent.run``'s
    ``message_history``. Raises ``pydantic.ValidationError`` on a corrupted or
    hand-crafted payload; callers surface that as the caller's error (422).
    """
    return ModelMessagesTypeAdapter.validate_python(data)
