"""Placeholder stroke-corpus import command.

HAB-012 replaces this with the real hanzi-writer-data importer. Keeping the
command now lets `just bootstrap` exercise the intended lifecycle without
claiming corpus import is implemented.
"""

from __future__ import annotations


def main() -> None:
    print("stroke corpus import skipped: HAB-012 will implement this command")


if __name__ == "__main__":
    main()
