from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev_env.py"


def _run_json(**env: str) -> dict[str, str]:
    subprocess_env = os.environ.copy()
    for key in (
        "OIDC_PROVIDER",
        "OIDC_SCOPES",
        "HABAGOU_KEYCLOAK_PORT",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "OIDC_ISSUER",
        "SESSION_SECRET_KEY",
    ):
        subprocess_env.pop(key, None)
    subprocess_env.update(env)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "json"],
        check=True,
        capture_output=True,
        env=subprocess_env,
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
    assert first["HABAGOU_KEYCLOAK_PORT"] == "12345"
    assert first["OIDC_PROVIDER"] == "keycloak"
    assert first["OIDC_ISSUER"] == "http://127.0.0.1:12345/realms/habagou"
    assert first["OIDC_CLIENT_ID"] == "habagou"
    assert first["SESSION_SECRET_KEY"] == "habagou-dev-session-habagou"


def test_overrides_win() -> None:
    values = _run_json(
        DATABASE_URL="postgresql+asyncpg://example/test",
        DEVENV_STATE="/tmp/habagou-state",
        HABAGOU_INSTANCE="manual",
        HABAGOU_KEYCLOAK_PORT="9999",
        HABAGOU_PORT="8100",
        OIDC_PROVIDER="auth0",
        OIDC_ISSUER="http://issuer.example/realms/habagou",
        PGHOST="/tmp/habagou-pg",
        SESSION_SECRET_KEY="manual-secret",
        VITE_PORT="5100",
    )

    assert values["DATABASE_URL"] == "postgresql+asyncpg://example/test"
    assert values["DEVENV_STATE"] == "/tmp/habagou-state"
    assert values["HABAGOU_KEYCLOAK_PORT"] == "9999"
    assert values["HABAGOU_PORT"] == "8100"
    assert values["OIDC_PROVIDER"] == "auth0"
    assert values["OIDC_ISSUER"] == "http://issuer.example/realms/habagou"
    assert values["PGHOST"] == "/tmp/habagou-pg"
    assert values["SESSION_SECRET_KEY"] == "manual-secret"
    assert values["VITE_PORT"] == "5100"
    assert values["VITE_API_PROXY_TARGET"] == "http://127.0.0.1:8100"
