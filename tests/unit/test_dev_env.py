from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev_env.py"


def _run_json(**env: str) -> dict[str, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "json"],
        check=True,
        capture_output=True,
        env={**os.environ, **env},
        text=True,
    )
    return json.loads(result.stdout)


def test_ports_are_deterministic_and_instance_scoped() -> None:
    first = _run_json(HABAGOU_INSTANCE="habagou")
    second = _run_json(HABAGOU_INSTANCE="habagou-feature")

    assert (
        first["HABAGOU_PORT"] == _run_json(HABAGOU_INSTANCE="habagou")["HABAGOU_PORT"]
    )
    assert first["HABAGOU_PORT"] != second["HABAGOU_PORT"]
    assert first["VITE_PORT"] == str(int(first["HABAGOU_PORT"]) + 3000)


def test_overrides_win() -> None:
    values = _run_json(
        DATABASE_URL="postgresql+asyncpg://example/test",
        DEVENV_STATE="/tmp/habagou-state",
        HABAGOU_INSTANCE="manual",
        HABAGOU_PORT="8100",
        PGHOST="/tmp/habagou-pg",
        VITE_PORT="5100",
    )

    assert values["DATABASE_URL"] == "postgresql+asyncpg://example/test"
    assert values["DEVENV_STATE"] == "/tmp/habagou-state"
    assert values["HABAGOU_PORT"] == "8100"
    assert values["PGHOST"] == "/tmp/habagou-pg"
    assert values["VITE_PORT"] == "5100"
    assert values["VITE_API_PROXY_TARGET"] == "http://127.0.0.1:8100"
