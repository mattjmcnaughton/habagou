"""Derive per-checkout development environment settings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
from pathlib import Path
from urllib.parse import quote

DEV_OIDC_CLIENT_SECRET = "habagou-dev-secret"


def _repo_root() -> Path:
    if root := os.environ.get("HABAGOU_ROOT"):
        return Path(root).resolve()
    return Path(__file__).resolve().parents[1]


def _port(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return 8000 + (int(digest[:8], 16) % 500)


def derive() -> dict[str, str]:
    root = _repo_root()
    instance = os.environ.get("HABAGOU_INSTANCE", root.name)
    default_backend_port = _port(instance)
    backend_port = os.environ.get("HABAGOU_PORT", str(default_backend_port))
    frontend_port = os.environ.get("VITE_PORT", str(int(backend_port) + 3000))
    keycloak_port = os.environ.get("HABAGOU_KEYCLOAK_PORT", "12345")
    devenv_state = Path(os.environ.get("DEVENV_STATE", root / ".devenv" / "state"))
    postgres_socket_dir = os.environ.get(
        "PGHOST",
        str(devenv_state / "postgres"),
    )
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://habagou@/habagou"
        f"?host={quote(postgres_socket_dir, safe='/')}",
    )

    return {
        "HABAGOU_INSTANCE": instance,
        "HABAGOU_PORT": backend_port,
        "VITE_PORT": frontend_port,
        "HABAGOU_KEYCLOAK_PORT": keycloak_port,
        "DEVENV_STATE": str(devenv_state),
        "PGHOST": postgres_socket_dir,
        "DATABASE_URL": database_url,
        "SESSION_SECRET_KEY": os.environ.get(
            "SESSION_SECRET_KEY", f"habagou-dev-session-{instance}"
        ),
        "OIDC_ISSUER": os.environ.get(
            "OIDC_ISSUER", f"http://127.0.0.1:{keycloak_port}/realms/habagou"
        ),
        "OIDC_CLIENT_ID": os.environ.get("OIDC_CLIENT_ID", "habagou"),
        "OIDC_CLIENT_SECRET": os.environ.get(
            "OIDC_CLIENT_SECRET", DEV_OIDC_CLIENT_SECRET
        ),
        "KEYCLOAK_REALM_FILE": os.environ.get(
            "KEYCLOAK_REALM_FILE",
            str(devenv_state / "keycloak" / "habagou-realm.json"),
        ),
        "VITE_API_PROXY_TARGET": os.environ.get(
            "VITE_API_PROXY_TARGET",
            f"http://127.0.0.1:{backend_port}",
        ),
    }


def _print_exports(values: dict[str, str]) -> None:
    for key, value in values.items():
        print(f"export {key}={shlex.quote(value)}")


def _print_info(values: dict[str, str]) -> None:
    print(f"Instance:     {values['HABAGOU_INSTANCE']}")
    print(f"Backend:      http://127.0.0.1:{values['HABAGOU_PORT']}")
    print(f"Frontend:     http://127.0.0.1:{values['VITE_PORT']}")
    print(f"Keycloak:     http://127.0.0.1:{values['HABAGOU_KEYCLOAK_PORT']}")
    print(f"Postgres:     {values['PGHOST']}")
    print(f"DATABASE_URL: {values['DATABASE_URL']}")
    print(f"OIDC_ISSUER:  {values['OIDC_ISSUER']}")


def render_keycloak_realm(values: dict[str, str]) -> Path:
    root = _repo_root()
    template = root / "docker" / "keycloak" / "habagou-realm.template.json"
    destination = Path(values["KEYCLOAK_REALM_FILE"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = template.read_text(encoding="utf-8")
    replacements = {
        "__HABAGOU_PORT__": values["HABAGOU_PORT"],
        "__VITE_PORT__": values["VITE_PORT"],
        "__OIDC_CLIENT_SECRET__": values["OIDC_CLIENT_SECRET"],
    }
    for key, value in replacements.items():
        content = content.replace(key, value)
    destination.write_text(content, encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "format",
        choices=["env", "info", "json", "render-keycloak-realm"],
        nargs="?",
        default="info",
    )
    args = parser.parse_args()

    values = derive()
    if args.format == "env":
        _print_exports(values)
    elif args.format == "json":
        print(json.dumps(values, indent=2, sort_keys=True))
    elif args.format == "render-keycloak-realm":
        print(render_keycloak_realm(values))
    else:
        _print_info(values)


if __name__ == "__main__":
    main()
