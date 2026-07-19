from __future__ import annotations

from scripts.seed import SeedResult, format_bootstrap_completed


def test_format_bootstrap_completed_event() -> None:
    assert (
        format_bootstrap_completed(SeedResult(chars=24, packs=4, categories=10))
        == "bootstrap_completed chars=24 packs=4 categories=10"
    )
