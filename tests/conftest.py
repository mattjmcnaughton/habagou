from __future__ import annotations

import os

os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret")
# Scrub live provider credentials before application settings are imported. The
# quarantined external contract test opts in explicitly through the justfile.
if os.environ.get("HABAGOU_ALLOW_EXTERNAL_MODEL_REQUESTS") != "1":
    os.environ["OPENROUTER_API_KEY"] = ""
# Never export test telemetry, even when a developer's local ``.env`` contains
# a production-capable write token.
os.environ["LOGFIRE_TOKEN"] = ""

import pydantic_ai.models  # noqa: E402

from habagou.config import settings  # noqa: E402

settings.session_secret_key = os.environ["SESSION_SECRET_KEY"]

# Forbid real model requests for the whole suite: any accidental network call to
# a live model raises instead of hitting the provider. Tests must stub with
# ``TestModel``/``FunctionModel`` (via ``Agent.override``). A later external test
# re-enables requests locally with ``models.override_allow_model_requests``.
pydantic_ai.models.ALLOW_MODEL_REQUESTS = False
