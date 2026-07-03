from __future__ import annotations

import pytest

from habagou.models import ActivityType
from habagou.routers.v1.progress import _workflow_for_activity


@pytest.mark.workflow("WF-03")
def test_trace_activity_maps_to_trace_workflow() -> None:
    assert _workflow_for_activity(ActivityType.TRACE) == "WF-03"


@pytest.mark.workflow("WF-04")
def test_match_activity_maps_to_match_workflow() -> None:
    assert _workflow_for_activity(ActivityType.MATCH) == "WF-04"


@pytest.mark.workflow("WF-05")
def test_sentence_activity_maps_to_sentence_workflow() -> None:
    assert _workflow_for_activity(ActivityType.SENTENCE) == "WF-05"
