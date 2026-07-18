"""Agent definitions: prompts, tools, validators, and assembly.

Each module here builds a complete pydantic-ai agent for one feature —
currently pack generation (:mod:`habagou.agents.generation`) and the
conversational practice tutor (:mod:`habagou.agents.practice`). Agents are
assembled WITHOUT a bound model and depend only on their declared deps
protocols, so this package imports with no FastAPI, no configuration, no
database, and no network. That purity is the point: the same factories serve
the production run path (wired up in ``services/``) and offline evaluation
harnesses (see ``docs/evals.md``), which bring their own model and deps.

Layering: routers -> services -> (agents, repositories). Application concerns —
config gating, model resolution, run logging, persistence, and the HTTP
message-history round trip — stay in ``services/``; nothing in this package may
import from ``services/``, ``routers/``, ``config``, or the database layer
(``db``, ``repositories``).
"""
