from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(autouse=True)
def record_workflow_markers(
    request: pytest.FixtureRequest,
    record_property: Callable[[str, object], None],
) -> None:
    """Expose workflow markers in pytest JUnit reports for traceability."""
    markers = list(request.node.iter_markers("workflow"))
    if not markers:
        return

    record_property("layer", _layer_for_path(Path(str(request.node.path))))
    for marker in markers:
        if marker.args:
            record_property("workflow", marker.args[0])


def _layer_for_path(path: Path) -> str:
    parts = set(path.parts)
    if "unit" in parts:
        return "unit"
    if "integration" in parts:
        return "integration"
    if "e2e" in parts:
        return "e2e"
    return "unknown"
