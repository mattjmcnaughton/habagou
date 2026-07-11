from __future__ import annotations

import os

os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret")

from habagou.config import settings  # noqa: E402

settings.session_secret_key = os.environ["SESSION_SECRET_KEY"]
