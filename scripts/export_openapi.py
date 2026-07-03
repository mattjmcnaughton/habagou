"""Export or check the versioned OpenAPI artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from habagou.app import app

DEFAULT_OUTPUT = Path("docs/api/openapi-v1.json")


def _document() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    document = _document()
    if args.check:
        if not args.output.exists():
            print(f"{args.output} does not exist; run export first", file=sys.stderr)
            raise SystemExit(1)
        existing = args.output.read_text(encoding="utf-8")
        if existing != document:
            print(
                f"{args.output} is stale; run `just openapi-export`",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
