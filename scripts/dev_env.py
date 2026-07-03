"""Derive per-checkout development environment settings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
from pathlib import Path
from urllib.parse import quote


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
        "DEVENV_STATE": str(devenv_state),
        "PGHOST": postgres_socket_dir,
        "DATABASE_URL": database_url,
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
    print(f"Postgres:     {values['PGHOST']}")
    print(f"DATABASE_URL: {values['DATABASE_URL']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "format",
        choices=["env", "info", "json"],
        nargs="?",
        default="info",
    )
    args = parser.parse_args()

    values = derive()
    if args.format == "env":
        _print_exports(values)
    elif args.format == "json":
        print(json.dumps(values, indent=2, sort_keys=True))
    else:
        _print_info(values)


if __name__ == "__main__":
    main()
