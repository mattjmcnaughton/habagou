"""Utilities for validating Hanzi path parameters."""

from __future__ import annotations


def is_single_grapheme(value: str) -> bool:
    """Return whether a route parameter contains exactly one Unicode scalar."""
    return len(value) == 1
