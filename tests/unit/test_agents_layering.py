"""Guard the agents-package layering rule (docs/architecture.md).

``habagou.agents`` modules assemble pydantic-ai agents with no bound model and
must stay importable with no FastAPI, configuration, or database anywhere in
their import graph — that purity is what lets evaluation harnesses import them
directly (see ``docs/evals.md``). The rule is otherwise enforced only by
docstrings, so this test would catch a future convenience import silently
regressing it.

The probe runs in a fresh interpreter: importing anything inside the pytest
process would see modules pre-loaded by conftest/other tests and prove nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys

# Module prefixes the agents package must never pull in: the application layers
# above/beside it, plus the frameworks those layers are built on.
_FORBIDDEN_PREFIXES = (
    "habagou.services",
    "habagou.routers",
    "habagou.config",
    "habagou.repositories",
    "habagou.models",
    "habagou.db",
    "fastapi",
    "sqlalchemy",
)

_PROBE = f"""\
import json
import sys

import habagou.agents.generation
import habagou.agents.practice

prefixes = {_FORBIDDEN_PREFIXES!r}
loaded = sorted(name for name in sys.modules if name.startswith(prefixes))
print(json.dumps(loaded))
"""


def test_agents_package_imports_without_app_layers() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        check=True,
    )
    forbidden = json.loads(result.stdout)
    assert forbidden == [], (
        f"habagou.agents pulled in forbidden application-layer modules: {forbidden}"
    )
