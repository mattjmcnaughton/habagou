from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "workflow_id",
    [
        pytest.param("WF-02", marks=pytest.mark.workflow("WF-02")),
        pytest.param("WF-03", marks=pytest.mark.workflow("WF-03")),
        pytest.param("WF-04", marks=pytest.mark.workflow("WF-04")),
        pytest.param("WF-05", marks=pytest.mark.workflow("WF-05")),
        pytest.param("WF-06", marks=pytest.mark.workflow("WF-06")),
        pytest.param("WF-07", marks=pytest.mark.workflow("WF-07")),
        pytest.param("WF-08", marks=pytest.mark.workflow("WF-08")),
        pytest.param("WF-10", marks=pytest.mark.workflow("WF-10")),
    ],
)
def test_workflow_e2e_traceability_placeholder(workflow_id: str) -> None:
    """Temporary e2e traceability anchor until HAB-042 adds browser journeys."""
    assert workflow_id.startswith("WF-")
