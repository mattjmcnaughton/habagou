"""Agent eval harness (dev-only, never packaged) — see docs/evals.md.

Runs the agents in ``src/habagou/agents/`` against curated datasets and scores
the outputs. Everything here is development tooling: it is excluded from the
wheel (hatch packages only ``src/habagou``), its dependencies live in the
``evals`` dependency group, and nothing on the request path imports it.

Entry point: ``uv run python -m evals`` (or ``just evals``).
"""
